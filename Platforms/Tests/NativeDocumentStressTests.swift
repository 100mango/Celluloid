import XCTest
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidMac

final class NativeDocumentStressTests: XCTestCase {
    @MainActor func testUndoBudgetTrimsDistinctImportsAndRetainsLatestUndo() {
        let manager = UndoManager(); manager.groupsByEvent = false
        let undo = DocumentUndo(maximumRetainedBytes: 128)
        var value = NativeDocument(); var trimCount = 0
        undo.apply = { value = $0 }; undo.historyTrimmed = { trimCount += 1 }
        // Tiny injected byte budget verifies the same accounting without allocating private photos.
        for number in 1...5 {
            var next = NativeDocument()
            next.recipe.filter = number.isMultiple(of: 2) ? .sepia : .fade
            next.originals[UUID()] = Data(repeating: UInt8(number), count: 64)
            manager.beginUndoGrouping()
            undo.change(from: value, to: next, manager: manager, name: "Import")
            manager.endUndoGrouping()
        }
        XCTAssertGreaterThan(trimCount, 0)
        XCTAssertEqual(value.originals.values.first?.first, 5)
        manager.undo(); XCTAssertEqual(value.originals.values.first?.first, 4)
        manager.redo(); XCTAssertEqual(value.originals.values.first?.first, 5)
        XCTAssertEqual(manager.levelsOfUndo, 20)
    }
    @MainActor func testCropUndoRestoresEntireSourceOrderAndGeometry() {
        let manager = UndoManager(); manager.groupsByEvent = false
        let undo = DocumentUndo(); var before = NativeDocument()
        before.recipe.sources = (0..<3).map { SourceImage(displayName: "\($0)", pixelWidth: 100, pixelHeight: 100) }
        before.recipe.collageTemplate = "layout"
        var after = before
        after.recipe.sources[0].crop.zoom = 5; after.recipe.sources[0].crop.centerY = 0.2
        after.recipe.sources.swapAt(0, 2)
        var value = before; undo.apply = { value = $0 }
        manager.beginUndoGrouping(); undo.change(from: before, to: after, manager: manager, name: "Crop"); manager.endUndoGrouping()
        XCTAssertEqual(value, after)
        manager.undo(); XCTAssertEqual(value, before)
        manager.redo(); XCTAssertEqual(value, after)
    }
}
