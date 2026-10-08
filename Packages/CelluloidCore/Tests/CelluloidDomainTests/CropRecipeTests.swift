import XCTest
@testable import CelluloidDomain

final class CropRecipeTests: XCTestCase {
    func testCropRoundtripAndReorderPreserveSourceIdentityAndAdjustments() throws {
        var value = EditRecipe()
        value.sources = (1...3).map { SourceImage(displayName: "Photo \($0)", pixelWidth: 1200, pixelHeight: 800) }
        value.collageTemplate = "three_pic_1"
        value.sources[0].crop.zoom = 4.5; value.sources[0].crop.centerX = 0.2; value.sources[0].crop.centerY = 0.8
        let adjusted = value.sources[0]
        value.sources.swapAt(0, 2); value.collageTemplate = "another_template"
        let restored = try EditRecipe.decode(value.encoded())
        XCTAssertEqual(restored.sources[2], adjusted)
        XCTAssertEqual(restored.sources.map(\.id), value.sources.map(\.id))
    }
    func testInvalidZoomAndFocalPointsAreRejected() {
        var source = SourceImage(displayName: "Photo", pixelWidth: 50, pixelHeight: 50)
        for value in [0.0, 5.01, Double.infinity, Double.nan] {
            source.crop.zoom = value; XCTAssertThrowsError(try source.validate())
        }
        source.crop = SourceCrop(); source.crop.centerX = -0.01
        XCTAssertThrowsError(try source.validate())
        source.crop.centerX = 0.5; source.crop.centerY = 1.01
        XCTAssertThrowsError(try source.validate())
    }
}
