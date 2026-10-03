import XCTest
import CoreGraphics
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidMac

final class NativeDocumentTests: XCTestCase {
    private func image() throws -> Data {
        let context = try RasterCodec.bitmap(width: 80, height: 60)
        context.setFillColor(CGColor(red: 0.2, green: 0.8, blue: 0.4, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 80, height: 60))
        return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
    }
    func testSaveReadbackReopenKeepsOriginalsAndNonDestructiveRecipe() throws {
        var document = NativeDocument()
        let original = try image()
        try document.replaceSources([("Original.png", original)])
        document.recipe.filter = .fade
        var bubble = Overlay(bubble: .call2, text: "你好 👋 مرحبا")
        bubble.rotation = 73; bubble.centerX = 0.32
        document.recipe.overlays = [bubble]
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".celluloid")
        defer { try? FileManager.default.removeItem(at: directory) }
        try document.archive().write(to: directory, options: .atomic, originalContentsURL: nil)
        let reopened = try NativeDocument(wrapper: FileWrapper(url: directory, options: .immediate))
        XCTAssertEqual(document, reopened)
        XCTAssertEqual(reopened.originals.values.first, original)
        let output = try RecipeRenderer().render(reopened.recipe, sources: reopened.originals)
        XCTAssertEqual(output.width, 80); XCTAssertEqual(output.height, 60)
    }
    func testTwoDocumentsDoNotLeakStateAndBadImportIsAtomic() throws {
        var one = NativeDocument(); let two = NativeDocument()
        try one.replaceSources([("One", image())]); one.recipe.filter = .invert
        XCTAssertTrue(two.recipe.sources.isEmpty); XCTAssertEqual(two.recipe.filter, .original)
        let snapshot = one
        XCTAssertThrowsError(try one.replaceSources([("bad", Data())]))
        XCTAssertEqual(snapshot, one)
    }
    func testRejectMissingOriginalAndExtraFile() throws {
        var document = NativeDocument(); try document.replaceSources([("Image", image())])
        let package = try document.archive()
        package.addRegularFile(withContents: Data(), preferredFilename: "unexpected")
        XCTAssertThrowsError(try NativeDocument(wrapper: package))
        let empty = FileWrapper(directoryWithFileWrappers: ["recipe.json": FileWrapper(regularFileWithContents: try document.recipe.encoded())])
        XCTAssertThrowsError(try NativeDocument(wrapper: empty))
    }
    @MainActor func testUndoRedoRestoresExactRecipe() throws {
        let manager = UndoManager(); manager.groupsByEvent = false
        let undo = DocumentUndo()
        let old = NativeDocument(); var new = old; new.recipe.filter = .sepia
        var value = old; undo.apply = { value = $0 }
        manager.beginUndoGrouping(); undo.change(from: old, to: new, manager: manager, name: "Filter"); manager.endUndoGrouping()
        XCTAssertEqual(value, new)
        manager.undo(); XCTAssertEqual(value, old)
        manager.redo(); XCTAssertEqual(value, new)
    }
}
