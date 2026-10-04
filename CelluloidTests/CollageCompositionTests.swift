import XCTest
import UIKit
import CryptoKit
import Photos
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class CollageCompositionTests: XCTestCase {
    private let palette = [[235, 45, 40], [40, 200, 70], [30, 60, 230], [235, 190, 25]]

    func testDistinctAsymmetricSourcesComposeTwoThreeFourAndReorderWithoutReuse() throws {
        let assets = try (0..<4).map { try XCTUnwrap(CelluloidTestFixtures.syntheticAsset(width: 800 + $0, height: 600), "CI must seed all four distinct composition fixtures") }
        XCTAssertEqual(Set(assets.map { $0.localIdentifier }).count, 4)
        let models = assets.map { PhotoModel(asset: $0) }
        let loaded = expectation(description: "Coalesced distinct source loads")
        loaded.expectedFulfillmentCount = 8
        for model in models {
            for _ in 0..<2 {
                model.loadImage { result in
                    if case .failure(let error) = result { XCTFail("Fixture load failed: \(error)") }
                    loaded.fulfill()
                }
            }
        }
        wait(for: [loaded], timeout: 20)
        var hashes: [String] = []
        for (index, model) in models.enumerated() {
            let source = try XCTUnwrap(model.loadedImage)
            let cg = try XCTUnwrap(source.cgImage)
            let hash = SHA256.hash(data: try XCTUnwrap(source.pngData())).map { String(format: "%02x", $0) }.joined()
            let pixelHash = try rgbaHash(cg)
            let resources = PHAssetResource.assetResources(for: model.asset)
            let adjusted = resources.contains { $0.type == .adjustmentData }
            hashes.append(hash)
            print("COLLAGE_INITIAL_SOURCE role=\(index) asset=\(model.asset.localIdentifier) files=\(resources.map { $0.originalFilename }) pixels=\(cg.width)x\(cg.height) current_rgba_sha256=\(pixelHash) loaded_png_sha256=\(hash) has_adjustment=\(adjusted)")
            XCTAssertFalse(adjusted, "Pristine composition checks must run before any UI phase edits these fixtures")
            assertColor(pixel(source, x: cg.width / 2, y: cg.height / 2), palette[index])
            assertColor(pixel(source, x: 5, y: 5), [255, 255, 255])
            assertColor(pixel(source, x: cg.width - 5, y: cg.height - 5), [0, 0, 0])
        }
        XCTAssertEqual(Set(hashes).count, 4)
        let collage = CollageView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        let orders = [[0, 1], [0, 1, 2], [0, 1, 2, 3], [3, 2, 1, 0], [3, 1]]
        for order in orders {
            let count = order.count
            let areas = (0..<count).map { index -> [CGPoint] in
                let left = CGFloat(index) * 100 / CGFloat(count), right = CGFloat(index + 1) * 100 / CGFloat(count)
                return [CGPoint(x: left, y: 0), CGPoint(x: right, y: 0), CGPoint(x: right, y: 100), CGPoint(x: left, y: 100)]
            }
            let model = CollageModel(imageName: "test-only-rectangles", areas: areas)
            collage.setupWithCollageModel(model, photoModels: order.map { models[$0] }, forEdit: false)
            XCTAssertEqual(collage.subviews.count, count)
            let result = collage.render()
            XCTAssertEqual(result.cgImage?.width, 800)
            XCTAssertEqual(result.cgImage?.height, 800)
            for (position, role) in order.enumerated() {
                let center = Int((CGFloat(position) + 0.5) * 800 / CGFloat(count))
                assertColor(pixel(result, x: center, y: 400), palette[role])
                // Every source's top-left asymmetric marker must stay top-left,
                // not flip or inherit another cell's crop/cache after rearrangement.
                let left = Int(CGFloat(position) * 800 / CGFloat(count))
                assertColor(pixel(result, x: left + 10, y: 10), [255, 255, 255])
            }
            print("COLLAGE_RENDER_CHECK count=\(count) source_roles=\(order) asset_ids=\(order.map { assets[$0].localIdentifier })")
        }
    }

    private func rgbaHash(_ image: CGImage) throws -> String {
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let rendered = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(image.width), height: CGFloat(image.height)))
            return true
        }
        XCTAssertTrue(rendered)
        return SHA256.hash(data: Data(bytes)).map { String(format: "%02x", $0) }.joined()
    }

    private func assertColor(_ actual: [UInt8], _ expected: [Int], file: StaticString = #filePath, line: UInt = #line) {
        for channel in 0..<3 { XCTAssertLessThanOrEqual(abs(Int(actual[channel]) - expected[channel]), 12, file: file, line: line) }
    }
    private func pixel(_ image: UIImage, x: Int, y: Int) -> [UInt8] {
        let cropped = image.cgImage!.cropping(to: CGRect(x: x, y: y, width: 1, height: 1))!
        var bytes = [UInt8](repeating: 0, count: 4)
        bytes.withUnsafeMutableBytes { buffer in
            let context = CGContext(data: buffer.baseAddress, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.draw(cropped, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        }
        return bytes
    }
}
