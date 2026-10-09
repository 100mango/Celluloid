import XCTest
import UIKit
@testable import CelluloidKit

extension XCTestCase {
    /// Wait for the asynchronous recipe/preview and actual hosting-view layout.
    /// The original pixel, metadata, identity and no-write assertions remain intact.
    @MainActor
    func waitForSwiftUIEditor(_ editor: PhotoEditingViewController, file: StaticString = #filePath, line: UInt = #line) {
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            editor.view.setNeedsLayout()
            editor.view.layoutIfNeeded()
            let session = editor.session
            guard session.phase != .loading, session.phase != .empty else { return false }
            if session.phase == .failed { return true }
            if session.isReadOnly { return editor.preview.image === session.previewImage }
            return !session.previewIsLoading && session.adjustment.referenceCanvasSize != nil
        }, object: nil)
        let result = XCTWaiter.wait(for: [ready], timeout: 15)
        XCTAssertEqual(result, .completed, "SwiftUI editor must finish the bound recipe/preview before its preservation oracle runs", file: file, line: line)
    }
}
