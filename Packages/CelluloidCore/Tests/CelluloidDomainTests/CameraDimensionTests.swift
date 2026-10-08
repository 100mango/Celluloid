import XCTest
@testable import CelluloidDomain

final class CameraDimensionTests: XCTestCase {
    func testCommonNominal48MPDimensionsAreAccepted() throws {
        let source = SourceImage(displayName: "48MP", pixelWidth: 8064, pixelHeight: 6048)
        XCTAssertEqual(source.pixelWidth * source.pixelHeight, 48_771_072)
        XCTAssertNoThrow(try source.validate())
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 8064; recipe.canvasHeight = 6048
        XCTAssertNoThrow(try recipe.validate())
        XCTAssertThrowsError(try SourceImage(displayName: "too large", pixelWidth: 10_000, pixelHeight: 5_001).validate())
    }
}
