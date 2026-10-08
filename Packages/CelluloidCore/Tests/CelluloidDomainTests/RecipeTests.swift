import XCTest
@testable import CelluloidDomain

final class RecipeTests: XCTestCase {
    func testNewDocumentRoundtripPreservesTextAndGeometry() throws {
        var value = EditRecipe()
        value.sources = [SourceImage(displayName: "原片", pixelWidth: 3024, pixelHeight: 4032)]
        value.canvasWidth = 3024; value.canvasHeight = 4032
        var bubble = Overlay(bubble: .think2, text: "你好 👨‍👩‍👧‍👦\nمرحبا café")
        bubble.centerX = 0.23; bubble.rotation = 71; bubble.mirrored = true
        value.overlays = [bubble]; value.filter = .fade
        XCTAssertEqual(try EditRecipe.decode(value.encoded()), value)
        XCTAssertEqual(value.format, "Celluloid.Document")
        XCTAssertNotEqual(value.format, "Mango.CelluloidPhotoExtension")
    }
    func testRejectUnknownVersionAndNonfiniteGeometry() throws {
        var value = EditRecipe(); value.version = 2
        XCTAssertThrowsError(try value.encoded())
        value.version = 1
        var overlay = Overlay(bubble: .say1); overlay.width = .nan; value.overlays = [overlay]
        XCTAssertThrowsError(try value.validate())
    }
    func testRejectDuplicateSourcesAndInvalidCollage() throws {
        var value = EditRecipe()
        let source = SourceImage(displayName: "a", pixelWidth: 5, pixelHeight: 6)
        value.sources = [source, source]
        XCTAssertThrowsError(try value.validate())
        value.sources[1] = SourceImage(displayName: "b", pixelWidth: 5, pixelHeight: 6)
        XCTAssertThrowsError(try value.validate())
        value.collageTemplate = "two_1"
        XCTAssertNoThrow(try value.validate())
    }
    func testRejectSourceOverflowBeforeMultiplication() {
        let image = SourceImage(displayName: "bad", pixelWidth: Int.max, pixelHeight: Int.max)
        XCTAssertThrowsError(try image.validate())
        var value = EditRecipe(); value.canvasWidth = Int.max
        XCTAssertThrowsError(try value.validate())
    }
}
