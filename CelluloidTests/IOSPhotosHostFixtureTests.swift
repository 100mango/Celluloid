import XCTest
import Photos
import UIKit
import CryptoKit
@testable import CelluloidKit

/// Storage evidence around the real Photos application UI. These methods never
/// instantiate an editing controller or render/install an adjustment themselves.
@MainActor
final class IOSPhotosHostFixtureTests: XCTestCase {
    private typealias Object = [String: Any]

    override func setUpWithError() throws {
        try super.setUpWithError()
        try XCTSkipUnless(ProcessInfo.processInfo.environment["CELLULOID_IOS_PHOTOS_HOST"] == "1",
                          "Dedicated owned Photos-host diagnostic only")
        continueAfterFailure = false
        executionTimeAllowance = 120
    }

    func testPrepareSingleOwnedPhotosHostAlbum() throws {
        let context = try authorizedContext()
        let asset = try ownedAsset(context)
        let before = try integrity(asset)
        try need(before["adjustment_sha256"] == nil, "Only an unedited controlled fixture may enter the host probe")
        try need(before["original_sha256"] as? String == context["fixture_sha256"] as? String, "Original fixture bytes changed")
        let title = try string(context, "album_title")
        let options = PHFetchOptions(); options.predicate = NSPredicate(format: "title == %@", title)
        try need(PHAssetCollection.fetchAssetCollections(with: .album, subtype: .any, options: options).count == 0,
                 "Do not adopt or replace an existing album")
        let done = expectation(description: "Create one explicitly owned album")
        var identifier: String?, error: Error?, success = false
        PHPhotoLibrary.shared().performChanges({
            let request = PHAssetCollectionChangeRequest.creationRequestForAssetCollection(withTitle: title)
            request.addAssets([asset] as NSArray)
            identifier = request.placeholderForCreatedAssetCollection.localIdentifier
        }) { value, failure in
            DispatchQueue.main.async { success = value; error = failure; done.fulfill() }
        }
        guard XCTWaiter.wait(for: [done], timeout: 20) == .completed else { throw failure("Album creation timed out; never retry it") }
        if let error = error { throw error }
        XCTAssertTrue(success)
        var prepared = context
        prepared["album_identifier"] = try XCTUnwrap(identifier)
        prepared["before"] = before
        prepared["library_asset_ids"] = try libraryIDs()
        prepared["public_filename_unique_asset_id"] = asset.localIdentifier
        try verifyAlbum(prepared, asset: asset)
        try emit("prepared", prepared)
    }

    func testReadActualPhotosHostSavedEdit() throws {
        let context = try authorizedContext(), asset = try ownedAsset(context)
        try verifyAlbum(context, asset: asset)
        XCTAssertEqual(try libraryIDs(), context["library_asset_ids"] as? [String])
        let before = try XCTUnwrap(context["before"] as? Object)
        let saved = try integrity(asset)
        XCTAssertEqual(saved["original_sha256"] as? String, before["original_sha256"] as? String)
        XCTAssertEqual(saved["original_pixels_sha256"] as? String, before["original_pixels_sha256"] as? String)
        XCTAssertNotEqual(saved["current_pixels_sha256"] as? String, before["current_pixels_sha256"] as? String,
                          "Actual host save must change decoded pixels")
        let input = try editingInput(asset)
        let adjustment = try XCTUnwrap(input.adjustmentData)
        XCTAssertEqual(adjustment.formatIdentifier, AdjustmentData.formatIdentifier)
        XCTAssertEqual(adjustment.formatVersion, "1.0")
        let recipe = try AdjustmentData.decode(adjustment.data)
        XCTAssertEqual(recipe.filterType, .Sepia)
        XCTAssertEqual(recipe.bubbles.count, 1)
        XCTAssertEqual(recipe.bubbles.first?.content, context["saved_caption"] as? String)
        XCTAssertTrue(recipe.stickers.isEmpty)
        let canvas = try XCTUnwrap(recipe.referenceCanvasSize)
        XCTAssertGreaterThan(canvas.width, 0); XCTAssertGreaterThan(canvas.height, 0)
        var value = context; value["saved"] = saved
        try emit("saved", value)
    }

    func testReadActualPhotosHostCancelledEdit() throws {
        let context = try authorizedContext(), asset = try ownedAsset(context)
        try verifyAlbum(context, asset: asset)
        XCTAssertEqual(try libraryIDs(), context["library_asset_ids"] as? [String])
        let saved = try XCTUnwrap(context["saved"] as? Object)
        let cancelled = try integrity(asset)
        XCTAssertEqual(try canonical(cancelled), try canonical(saved),
                       "Cancel must retain the saved original, current resources, decoded pixels, and recipe bytes")
        let recipe = try AdjustmentData.decode(XCTUnwrap(try editingInput(asset).adjustmentData).data)
        XCTAssertEqual(recipe.filterType, .Sepia)
        XCTAssertEqual(recipe.bubbles.map(\.content), [try string(context, "saved_caption")])
        try emit("cancelled", ["source_sha": try string(context, "source_sha"),
            "device_id": try string(context, "device_id"), "context_token": try string(context, "context_token"),
            "asset_identifier": asset.localIdentifier, "unchanged_saved_integrity": cancelled])
    }

    private func authorizedContext() throws -> Object {
        #if targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        guard environment["CELLULOID_IOS_PHOTOS_HOST"] == "1",
              PHPhotoLibrary.authorizationStatus(for: .readWrite) == .authorized,
              let source = environment["CELLULOID_EXPECTED_SOURCE_SHA"], source.count == 40,
              source.allSatisfy({ "0123456789abcdef".contains($0) }),
              let text = environment["CELLULOID_IOS_PHOTOS_HOST_CONTEXT"], text.utf8.count <= 64_000,
              let value = try JSONSerialization.jsonObject(with: Data(text.utf8)) as? Object,
              value["schema"] as? String == "celluloid.ios.photos-host.v1",
              value["source_sha"] as? String == source,
              value["fixture_filename"] as? String == "celluloid-fixture-2.png",
              let title = value["album_title"] as? String, title.hasPrefix("Celluloid Host "),
              let serialized = environment["CELLULOID_FIXTURE_MANIFEST_JSON"],
              let manifest = try JSONSerialization.jsonObject(with: Data(serialized.utf8)) as? Object,
              manifest["source_sha"] as? String == source,
              manifest["device_id"] as? String == value["device_id"] as? String,
              manifest["authorization_read_write"] as? String == "authorized",
              let fixtures = manifest["fixtures"] as? [Object], fixtures.count == 6 else {
            throw failure("Owned simulator, real grant, source-bound fixture/context prerequisites are absent")
        }
        let matches = fixtures.filter { $0["filename"] as? String == value["fixture_filename"] as? String }
        try need(matches.count == 1, "Ambiguous controlled fixture")
        let fixture = try XCTUnwrap(matches.first)
        try need(fixture["identifier"] as? String == value["asset_identifier"] as? String, "Fixture ID differs")
        try need(fixture["sha256"] as? String == value["fixture_sha256"] as? String, "Fixture hash differs")
        return value
        #else
        throw failure("Actual Photos host probe is restricted to the owned simulator")
        #endif
    }
    private func ownedAsset(_ context: Object) throws -> PHAsset {
        let identifier = try string(context, "asset_identifier")
        let found = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
        try need(found.count == 1, "Owned asset missing or ambiguous")
        let asset = try XCTUnwrap(found.firstObject)
        try need(asset.localIdentifier == identifier && asset.pixelWidth == 640 && asset.pixelHeight == 480, "Owned asset identity/dimensions differ")
        let originals = PHAssetResource.assetResources(for: asset).filter { $0.type == .photo }
        try need(originals.count == 1, "Owned original resource missing or ambiguous")
        try need(originals.first?.originalFilename == string(context, "fixture_filename"), "Owned filename differs")
        try need(digest(bytes(XCTUnwrap(originals.first))) == string(context, "fixture_sha256"), "Owned original bytes differ")
        // Photos can restore its last single-photo screen. A public Info filename
        // is sufficient there only after proving uniqueness across the whole
        // actual image library, including the untouched stock assets.
        let expectedBase = (try string(context, "fixture_filename") as NSString).deletingPathExtension.lowercased()
        let all = PHAsset.fetchAssets(with: .image, options: nil)
        try need(all.count <= 128, "Unexpected library size before filename proof")
        var matchingIDs = Set<String>()
        all.enumerateObjects { item, _, _ in
            if PHAssetResource.assetResources(for: item).contains(where: {
                ($0.originalFilename as NSString).deletingPathExtension.lowercased() == expectedBase
            }) { matchingIDs.insert(item.localIdentifier) }
        }
        try need(matchingIDs == Set([identifier]), "Public filename could identify an unrelated image")
        return asset
    }
    private func verifyAlbum(_ context: Object, asset: PHAsset) throws {
        let albums = PHAssetCollection.fetchAssetCollections(withLocalIdentifiers: [try string(context, "album_identifier")], options: nil)
        XCTAssertEqual(albums.count, 1)
        let album = try XCTUnwrap(albums.firstObject)
        XCTAssertEqual(album.localizedTitle, try string(context, "album_title"))
        let members = PHAsset.fetchAssets(in: album, options: nil)
        XCTAssertEqual(members.count, 1)
        XCTAssertEqual(members.firstObject?.localIdentifier, asset.localIdentifier)
    }
    private func libraryIDs() throws -> [String] {
        let assets = PHAsset.fetchAssets(with: .image, options: nil)
        guard assets.count <= 128 else { throw failure("Unexpected library size") }
        var result: [String] = []; assets.enumerateObjects { asset, _, _ in result.append(asset.localIdentifier) }
        return result.sorted()
    }
    private func editingInput(_ asset: PHAsset) throws -> PHContentEditingInput {
        let ready = expectation(description: "Read actual Photos adjustment")
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = false; options.canHandleAdjustmentData = { _ in true }
        var input: PHContentEditingInput?
        let token = asset.requestContentEditingInput(with: options) { value, _ in
            DispatchQueue.main.async { input = value; ready.fulfill() }
        }
        guard XCTWaiter.wait(for: [ready], timeout: 15) == .completed else {
            asset.cancelContentEditingInputRequest(token); throw failure("Readback timed out")
        }
        return try XCTUnwrap(input)
    }
    private func bytes(_ resource: PHAssetResource) throws -> Data {
        let done = expectation(description: "Read exact fixture resource")
        let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
        let lock = NSLock(); var result = Data(), error: Error?
        let token = PHAssetResourceManager.default().requestData(for: resource, options: options, dataReceivedHandler: { chunk in
            lock.lock(); result.append(chunk); lock.unlock()
        }) { value in error = value; done.fulfill() }
        guard XCTWaiter.wait(for: [done], timeout: 15) == .completed else {
            PHAssetResourceManager.default().cancelDataRequest(token); throw failure("Resource read timed out")
        }
        if let error = error { throw error }; return result
    }
    private func integrity(_ asset: PHAsset) throws -> Object {
        var resources: [Object] = [], original: Data?, current: Data?
        for resource in PHAssetResource.assetResources(for: asset) {
            let data = try bytes(resource)
            resources.append(["type": resource.type.rawValue, "filename": resource.originalFilename,
                              "uti": resource.uniformTypeIdentifier, "sha256": digest(data)])
            if resource.type == .photo { original = data }
            if resource.type == .fullSizePhoto { current = data }
        }
        let source = try XCTUnwrap(original), rendered = current ?? source
        var result: Object = ["asset_identifier": asset.localIdentifier,
            "resources": resources.sorted {
                ($0["type"] as! Int, $0["filename"] as! String, $0["sha256"] as! String)
                < ($1["type"] as! Int, $1["filename"] as! String, $1["sha256"] as! String)
            },
            "original_sha256": digest(source), "current_sha256": digest(rendered),
            "original_pixels_sha256": try pixels(source), "current_pixels_sha256": try pixels(rendered)]
        if let adjustment = try editingInput(asset).adjustmentData {
            result["adjustment_sha256"] = digest(adjustment.data)
            result["adjustment_identifier"] = adjustment.formatIdentifier
            result["adjustment_version"] = adjustment.formatVersion
        }
        return result
    }
    private func pixels(_ data: Data) throws -> String {
        let cg = try XCTUnwrap(UIImage(data: data)?.cgImage)
        let context = try XCTUnwrap(CGContext(data: nil, width: cg.width, height: cg.height, bitsPerComponent: 8,
            bytesPerRow: cg.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(cg, in: CGRect(x: 0, y: 0, width: CGFloat(cg.width), height: CGFloat(cg.height)))
        return digest(Data(bytes: try XCTUnwrap(context.data), count: context.bytesPerRow * cg.height))
    }
    private func emit(_ stage: String, _ value: Object) throws {
        print("IOS_PHOTOS_HOST_STORAGE " + stage + " " + String(decoding: try canonical(value), as: UTF8.self))
    }
    private func canonical(_ object: Object) throws -> Data { try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) }
    private func string(_ object: Object, _ key: String) throws -> String { try XCTUnwrap(object[key] as? String) }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func need(_ condition: Bool, _ message: String) throws { if !condition { throw failure(message) } }
    private func failure(_ message: String) -> NSError { NSError(domain: "Celluloid.ActualPhotosHost", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
