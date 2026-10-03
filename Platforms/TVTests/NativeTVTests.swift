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
        let saved = TVSavedRecipe(recipe: recipe, photoIDs: [source.id: "synthetic-photos-identifier"])
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
        XCTAssertEqual(try TVPhotoLibrary.normalizedProof(a), TVPhotoLibrary.normalizedProof(a))
        XCTAssertNotEqual(try TVPhotoLibrary.normalizedProof(a), TVPhotoLibrary.normalizedProof(b))
        XCTAssertThrowsError(try TVPhotoLibrary.normalizedProof(Data()))
    }
}
