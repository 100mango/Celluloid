import XCTest
import UIKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidTV

final class NativeTVTests: XCTestCase {
    @MainActor func testNativeTVExecutableAndScene() {
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "appletvsimulator")
        XCTAssertFalse(UIApplication.shared.connectedScenes.isEmpty)
        print("TV_NATIVE_RUNTIME bundle=\(Bundle.main.bundleURL.path)")
    }
    func testRecoverableRecipeRoundtripAndStrictMetadataBudget() throws {
        var recipe = EditRecipe()
        let source = SourceImage(displayName: "Synthetic", pixelWidth: 1200, pixelHeight: 800)
        recipe.sources = [source]; recipe.canvasWidth = 1200; recipe.canvasHeight = 800
        recipe.overlays = [Overlay(bubble: .say1, text: "TV 世界")]
        let saved = TVSavedRecipe(recipe: recipe, photoIDs: [source.id: "synthetic-photos-identifier"], fingerprints: [source.id: String(repeating: "a", count: 64)])
        XCTAssertEqual(try TVSavedRecipe.decode(saved.encoded()), saved)
        XCTAssertLessThan(try saved.encoded().count, 256 * 1024)
        var invalid = saved; invalid.photoIDs.removeAll(); XCTAssertThrowsError(try invalid.encoded())
        invalid = saved; invalid.version = 2; XCTAssertThrowsError(try invalid.encoded())
        invalid = saved
        invalid.recipe.overlays = (0..<100).map { _ in Overlay(bubble: .say1, text: String(repeating: "a", count: 16_384)) }
        XCTAssertThrowsError(try invalid.encoded())
        XCTAssertThrowsError(try TVSavedRecipe.decode(Data(repeating: 0, count: TVSavedRecipe.maximumBytes + 1)))
    }
    @MainActor func testTVImageProofDetectsColorAndDimensionChanges() throws {
        func picture(_ red: CGFloat) throws -> Data {
            let context = try RasterCodec.bitmap(width: 120, height: 80)
            context.setFillColor(CGColor(srgbRed: red, green: 0, blue: 0, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
            return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
        }
        let a = try picture(1), b = try picture(0)
        XCTAssertEqual(try TVPhotoLibrary.normalizedProof(a), try TVPhotoLibrary.normalizedProof(a))
        XCTAssertNotEqual(try TVPhotoLibrary.normalizedProof(a), try TVPhotoLibrary.normalizedProof(b))
        XCTAssertThrowsError(try TVPhotoLibrary.normalizedProof(Data()))
    }
    @MainActor func testSameDimensionSourceReplacementKeepsCurrentCompositionIntact() async throws {
        func png(_ red: CGFloat) throws -> Data {
            let bitmap = try RasterCodec.bitmap(width: 12,height: 8)
            bitmap.setFillColor(CGColor(srgbRed: red,green: 0.3,blue: 0.7,alpha: 1));bitmap.fill(CGRect(x: 0,y: 0,width: 12,height: 8))
            return try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()),as:.png)
        }
        let suite = "Celluloid.TV.Test." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        let source = StubPhotoSource(bytes: try png(1))
        let model = TVEditorModel(defaults: defaults)
        await model.importPhotos(["same-asset-id"],library:source); model.keepRecipe()
        let previousRecipe = model.recipe, previousBytes = model.originals
        source.bytes = try png(0)
        XCTAssertEqual(try RasterCodec.metadata(source.bytes).pixelWidth,12)
        await model.reopen(library:source)
        XCTAssertEqual(model.recipe,previousRecipe);XCTAssertEqual(model.originals,previousBytes)
        XCTAssertEqual(model.error,TVPhotoError.changed.localizedDescription)
    }
    @MainActor func testTwoThreeFourPhotoEditsKeepCropOrderLayersUndoAndReopen() async throws {
        let suite = "Celluloid.TV.Collage." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        var photos: [String: Data] = [:]
        for index in 0..<4 {
            let bitmap = try RasterCodec.bitmap(width: 96, height: 64)
            for x in 0..<96 {
                let value = CGFloat(x) / 95
                bitmap.setFillColor(CGColor(srgbRed: index % 2 == 0 ? value : 1-value, green: CGFloat(index)/4, blue: 0.2+value/2, alpha: 1))
                bitmap.fill(CGRect(x: x,y: 0,width: 1,height: 64))
            }
            photos["synthetic-source-\(index)"] = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()),as:.png)
        }
        for count in 2...4 {
            let library = CollagePhotoSource(photos: photos), model = TVEditorModel(defaults: defaults)
            let ids = (0..<count).map { "synthetic-source-\($0)" }
            await model.importPhotos(ids,library:library)
            XCTAssertNil(model.error); XCTAssertEqual(model.recipe.sources.count,count)
            let originalIDs = model.recipe.sources.map(\.id)
            model.change { recipe in
                for index in recipe.sources.indices { recipe.sources[index].crop.centerX = 0.2+Double(index)/10; recipe.sources[index].crop.centerY = 0.7; recipe.sources[index].crop.zoom = 2.5 }
                recipe.sources.swapAt(0,count-1)
            }
            let cropped = model.recipe.sources
            for template in try NativeResources.templates(count:count) {
                model.change { $0.collageTemplate = template.assetName }
                XCTAssertEqual(model.recipe.sources,cropped,"Changing template must preserve each source crop and order")
            }
            model.add(Overlay(sticker:try XCTUnwrap(StickerAsset.all.first)))
            model.add(Overlay(bubble:.say1,text:"TV 世界"))
            let beforeTransform = model.recipe
            model.editLayer { $0.rotation = 30; $0.mirrored = true; $0.centerX = 0.6; $0.fontSize = 0.035 }
            XCTAssertNotEqual(model.recipe,beforeTransform)
            model.undo(); XCTAssertEqual(model.recipe,beforeTransform)
            model.editLayer { $0.rotation = 15; $0.mirrored = true }
            let complete = model.recipe
            model.keepRecipe(); XCTAssertNil(model.error)
            let stored = try XCTUnwrap(defaults.data(forKey:TVEditorModel.savedKey))
            XCTAssertLessThanOrEqual(stored.count,TVSavedRecipe.maximumBytes)
            let record = try TVSavedRecipe.decode(stored)
            XCTAssertEqual(record.recipe,complete)
            XCTAssertEqual(record.photoIDs[originalIDs[0]],ids[0])
            let reopened = TVEditorModel(defaults:defaults)
            await reopened.reopen(library:library)
            XCTAssertNil(reopened.error); XCTAssertEqual(reopened.recipe,complete); XCTAssertEqual(reopened.originals,model.originals)
            await reopened.saveToPhotos(library:library)
            XCTAssertNil(reopened.error)
            let output = try XCTUnwrap(library.saved.last), metadata = try RasterCodec.metadata(output)
            XCTAssertEqual(metadata.pixelWidth,800); XCTAssertEqual(metadata.pixelHeight,800)
            let removed = reopened.recipe.sources[0].id
            var removal = reopened.recipe; removal.sources.removeFirst(); try TVEditorModel.configureCanvas(&removal)
            reopened.change { $0 = removal }
            XCTAssertFalse(reopened.recipe.sources.contains { $0.id == removed })
            reopened.undo(); XCTAssertEqual(reopened.recipe,complete)
            print("TV_NATIVE_MODEL_COLLAGE sources=\(count) allTemplates/crop/order/layers/multilingualText/undo/recipeReopen/export verified; injected data source, not Photos focus E2E")
        }
    }
    @MainActor private final class CollagePhotoSource: TVPhotoDataSource {
        let photos: [String: Data]
        var saved: [Data] = []
        init(photos: [String:Data]) { self.photos = photos }
        func currentImageData(_ id:String,limit:Int) async throws -> Data {
            guard let bytes = photos[id] else { throw TVPhotoError.missing }
            guard bytes.count <= limit else { throw RecipeError.resourceLimit }; return bytes
        }
        func saveVerifiedPNG(_ bytes:Data) async throws -> String {
            _ = try RasterCodec.metadata(bytes); saved.append(bytes); return "synthetic-saved-output"
        }
    }
    @MainActor private final class StubPhotoSource: TVPhotoDataSource {
        var bytes: Data
        init(bytes:Data) { self.bytes=bytes }
        func currentImageData(_ id:String,limit:Int) async throws -> Data { guard bytes.count<=limit else { throw RecipeError.resourceLimit };return bytes }
        func saveVerifiedPNG(_ bytes:Data) async throws -> String { throw TVPhotoError.unavailable }
    }
    func testResourceStreamRejectsOversizeAndCancelsRequest() async {
        let state = TVResourceRead(limit: 4)
        let cancelled = expectation(description: "PhotoKit request cancellation")
        state.setCancellation { cancelled.fulfill() }
        do {
            let _: Data = try await withCheckedThrowingContinuation { continuation in
                state.install(continuation); state.append(Data([1,2,3])); state.append(Data([4,5])); state.finish(nil)
            }
            XCTFail("Oversize stream must fail")
        } catch { }
        await fulfillment(of: [cancelled], timeout: 2)
        let pending = TVResourceRead(limit: 4)
        pending.cancel()
        do { let _: Data = try await withCheckedThrowingContinuation { pending.install($0) }; XCTFail("Canceled stream must fail") }
        catch is CancellationError { }
        catch { XCTFail("Expected cancellation") }
    }

}
