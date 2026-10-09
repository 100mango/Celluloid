import XCTest
import UIKit
@testable import CelluloidKit

extension XCTestCase {
    /// Real app-process window hosting for controller-level PhotoKit tests.
    /// This is not the Photos application's extension-host UI.
    @MainActor
    func mountControllerTestWindow(_ editor: PhotoEditingViewController, size: CGSize) throws -> UIWindow {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(origin: .zero, size: size)
        window.rootViewController = editor
        window.makeKeyAndVisible()
        window.frame = CGRect(origin: .zero, size: size)
        editor.view.frame = window.bounds
        window.layoutIfNeeded(); editor.view.layoutIfNeeded()
        XCTAssertTrue(editor.view.window === window)
        XCTAssertEqual(editor.view.bounds.size, size)
        return window
    }

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
