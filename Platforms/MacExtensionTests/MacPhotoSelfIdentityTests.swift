#if DEBUG
import XCTest
import AppKit

final class MacPhotoSelfIdentityTests: XCTestCase {
    func testSelfIdentityCaptureRejectsTheNativeTestBundle() {
        // An isolated XCTest bundle cannot manufacture an extension observation.
        // The collector must reject it before any own executable/dylib file open.
        XCTAssertNotEqual(Bundle.main.bundleIdentifier, "Mango.Celluloid.CelluloidPhotoExtension")
        XCTAssertThrowsError(try MacPhotoSelfIdentityCapture.observe(generation: UUID()))
    }

    @MainActor func testSelfIdentityStartReplacesGenerationAndCancelClearsSynchronously() {
        let identity = MacPhotoSelfIdentity()
        XCTAssertNil(identity.generation); XCTAssertNil(identity.value)
        identity.contentEditingStarted()
        let first = identity.generation
        XCTAssertNotNil(first); XCTAssertNil(identity.value)
        identity.contentEditingStarted()
        XCTAssertNotNil(identity.generation); XCTAssertNotEqual(identity.generation, first)
        XCTAssertNil(identity.value, "A new session must clear the old observation before asynchronous work")
        identity.invalidate()
        XCTAssertNil(identity.generation); XCTAssertNil(identity.value)
        identity.invalidate()
        XCTAssertNil(identity.generation); XCTAssertNil(identity.value)
    }

    @MainActor func testSelfIdentityAccessibilityRejectsUnstartedDetachedAndCancelledEditors() {
        let identity = MacPhotoSelfIdentity(), session = MacPhotoSession()
        let view = MacPhotoSelfIdentityAccessibilityView(frame: NSRect(x: 0, y: 0, width: 1, height: 1))
        view.identity = identity; view.session = session
        XCTAssertNil(identity.readyValue(for: session))
        XCTAssertNil(view.accessibilityValue()); XCTAssertFalse(view.isAccessibilityElement())
        identity.contentEditingStarted()
        XCTAssertNil(view.accessibilityValue()); XCTAssertFalse(view.isAccessibilityElement())
        XCTAssertNil(view.hitTest(.zero)); XCTAssertFalse(view.acceptsFirstResponder)
        identity.invalidate()
        XCTAssertNil(identity.readyValue(for: session))
        XCTAssertNil(view.accessibilityValue()); XCTAssertFalse(view.isAccessibilityElement())
    }
}
#endif
