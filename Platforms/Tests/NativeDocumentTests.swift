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
    @MainActor func testPendingTextAndTransformOrdersKeepExactTextGeometryUndoAndReopen() throws {
        let bytes = try image()
        for textFirst in [true, false] {
            var value = NativeDocument(); try value.replaceSources([("Original.png", bytes)])
            let bubble = Overlay(bubble: .say1, text: "Hello")
            value.recipe.overlays = [bubble]
            let sourceID = try XCTUnwrap(value.recipe.sources.first?.id)
            // Both actions were created by the same old displayed view. They
            // intentionally carry IDs/field mutations rather than its snapshot.
            let text: RecipeMutation = { $0.editOverlay(bubble.id) { $0.text = "Saved 世界 مرحبا" } }
            let transform: RecipeMutation = {
                $0.editOverlay(bubble.id) { $0.centerX += 0.01; $0.rotation += 15 }
                $0.editSourceCrop(sourceID) { $0.zoom = 1.5 }
            }
            let manager = UndoManager(); manager.groupsByEvent = false
            let undo = DocumentUndo(); undo.apply = { value = $0 }
            for mutation in textFirst ? [text, transform] : [transform, text] {
                let next = try value.editing(mutation)
                manager.beginUndoGrouping(); undo.change(from: value, to: next, manager: manager, name: "Synthetic field edit"); manager.endUndoGrouping()
            }
            XCTAssertEqual(value.recipe.overlays[0].text, "Saved 世界 مرحبا")
            XCTAssertEqual(value.recipe.overlays[0].centerX, 0.51, accuracy: 0.000_001)
            XCTAssertEqual(value.recipe.overlays[0].rotation, 15)
            XCTAssertEqual(value.recipe.sources[0].crop.zoom, 1.5)
            manager.undo()
            XCTAssertEqual(value.recipe.overlays[0].text, textFirst ? "Saved 世界 مرحبا" : "Hello")
            XCTAssertEqual(value.recipe.overlays[0].rotation, textFirst ? 0 : 15)
            manager.redo()
            XCTAssertEqual(value.recipe.overlays[0].text, "Saved 世界 مرحبا")
            XCTAssertEqual(value.recipe.overlays[0].centerX, 0.51, accuracy: 0.000_001)
            XCTAssertEqual(value.recipe.overlays[0].rotation, 15)
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".celluloid")
            defer { try? FileManager.default.removeItem(at: folder) }
            try value.archive().write(to: folder, options: .atomic, originalContentsURL: nil)
            let reopened = try NativeDocument(wrapper: FileWrapper(url: folder, options: .immediate))
            XCTAssertEqual(reopened, value); XCTAssertEqual(reopened.originals[sourceID], bytes)
        }
    }
    func testLateTextForRemovedLayerCannotReplaceAnotherLayer() throws {
        var value = NativeDocument(); try value.replaceSources([("Original.png", image())])
        let removed = Overlay(bubble: .say1, text: "Old"), retained = Overlay(bubble: .call2, text: "Keep 世界")
        value.recipe.overlays = [removed, retained]
        value = try value.editing { $0.overlays.removeAll { $0.id == removed.id } }
        let snapshot = value
        value = try value.editing { $0.editOverlay(removed.id) { $0.text = "Late obsolete text" } }
        XCTAssertEqual(value, snapshot); XCTAssertEqual(value.recipe.overlays.first?.text, "Keep 世界")
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
