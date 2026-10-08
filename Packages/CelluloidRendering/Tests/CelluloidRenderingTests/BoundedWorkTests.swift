import XCTest
import CoreGraphics
import CelluloidDomain
@testable import CelluloidRendering

final class BoundedWorkTests: XCTestCase {
    func testMaximumFontUsesBoundedSearchAndFitsAllCharacters() throws {
        let text = String(repeating: "中", count: 5_461) // 16,383 UTF-8 bytes
        let layout = try BoundedTextLayout.make(text: text, maximumFont: 8192,
                                               rect: CGRect(x: 0, y: 0, width: 800, height: 800))
        XCTAssertLessThanOrEqual(layout.shapingPasses, 17)
        XCTAssertGreaterThanOrEqual(layout.fontSize, 1)
    }
    func testCannotFitDoesNotSilentlyTruncate() {
        XCTAssertThrowsError(try BoundedTextLayout.make(text: String(repeating: "m", count: 16_384), maximumFont: 8192,
                                                        rect: CGRect(x: 0, y: 0, width: 1, height: 1)))
    }
    func testHundredMaximumTextLayersStayWithinExplicitPerLayerWorkBound() throws {
        let text = String(repeating: "a", count: 16_384)
        var total = 0
        for _ in 0..<100 {
            let layout = try BoundedTextLayout.make(text: text, maximumFont: 8192,
                                                   rect: CGRect(x: 0, y: 0, width: 800, height: 800))
            total += layout.shapingPasses
        }
        XCTAssertLessThanOrEqual(total, 1700)
    }
    func testCanceledLayoutAndQueuedRenderStopBeforeHeavyWork() async throws {
        let task = Task {
            while !Task.isCancelled { await Task.yield() }
            return try BoundedTextLayout.make(text: String(repeating: "a", count: 16_384), maximumFont: 8192,
                                              rect: CGRect(x: 0, y: 0, width: 800, height: 800))
        }
        task.cancel()
        do { _ = try await task.value; XCTFail("Canceled layout succeeded") }
        catch { XCTAssertTrue(error is CancellationError) }
        let queue = NativeRenderQueue()
        let render = Task {
            while !Task.isCancelled { await Task.yield() }
            return try await queue.preview(EditRecipe(), sources: [:])
        }
        render.cancel()
        do { _ = try await render.value; XCTFail("Canceled render succeeded") }
        catch { XCTAssertTrue(error is CancellationError) }
    }
}
