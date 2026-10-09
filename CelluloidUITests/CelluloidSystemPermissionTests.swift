import XCTest
import UIKit

/// Run only in the seeded disposable simulator. System picker browsing is allowed
/// before a PhotoKit grant; original editing is separately and explicitly granted.
final class CelluloidSystemPermissionTests: XCTestCase {
    private let app = XCUIApplication()
    private var failClosedMonitor: NSObjectProtocol?

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        failClosedMonitor = installFailClosedSystemAlertMonitor()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
    }
    override func tearDown() {
        app.terminate()
        if let monitor = failClosedMonitor { removeUIInterruptionMonitor(monitor) }
        failClosedMonitor = nil
        super.tearDown()
    }

    private func openPicker() {
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 10))
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(waitForSystemPhotoPicker(app))
        XCTAssertFalse(app.buttons["photos-allow-originals"].exists,
                       "Opening PHPicker must not ask for PhotoKit access or resolve originals")
    }

    func testRealGrantedAccessCanSelectFixture() {
        app.resetAuthorizationStatus(for: .photos)
        let monitor = installExpectedFullPhotosAccessMonitor()
        defer { removeUIInterruptionMonitor(monitor) }
        openPicker()
        selectSystemPhotos(app, indices: [0])
        XCTAssertTrue(app.buttons["photos-allow-originals"].waitForExistence(timeout: 5))
        allowOriginalEditingIfRequested(app)
        let done = app.buttons["editor-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 15))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: done)], timeout: 15), .completed)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }

    func testRealRevokedAccessClearsSelectionAndHasRecovery() {
        // The calling CI phase explicitly revokes PhotoKit access first. PHPicker
        // still works; denied original-edit access must never turn into copy mode.
        openPicker()
        for _ in 0..<2 {
            selectSystemPhotos(app, indices: [0])
            let state = app.staticTexts["photos-state"]
            XCTAssertTrue(state.waitForExistence(timeout: 10))
            XCTAssertTrue(app.buttons["photos-settings"].isHittable)
            XCTAssertFalse(app.buttons["editor-done"].exists)
            XCTAssertFalse(app.buttons["collage-done"].exists)
            app.buttons["selected-photos-cancel"].tap()
            XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
            app.buttons["edit-photo"].tap()
        }
        app.buttons["Cancel"].tap()
    }

    func testRealLimitedSelectionAndManagement() {
        app.resetAuthorizationStatus(for: .photos)
        let monitor = installExpectedLimitedPhotosAccessMonitor()
        defer { removeUIInterruptionMonitor(monitor) }
        openPicker()
        let labels = selectSystemPhotos(app, indices: [0])
        XCTAssertEqual(labels.count, 1)
        XCTAssertTrue(app.buttons["photos-allow-originals"].waitForExistence(timeout: 5))
        app.buttons["photos-allow-originals"].tap()
        chooseExactLimitedAuthorization()
        let manage = app.buttons["manage-photos"]
        // iOS versions either finish with an empty limited grant or immediately
        // show its selection UI. Handle only these observable, expected states.
        let transition = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            manage.exists || !self.systemPhotoCandidates(self.app).isEmpty
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [transition], timeout: 10), .completed)
        if manage.exists { manage.tap() }
        XCTAssertTrue(waitForSystemPhotoPicker(app))
        let matching = systemPhotoCandidates(app).filter { $0.label == labels[0] }
        XCTAssertEqual(matching.count, 1, "Select the same public photo label, never a private Photos identifier")
        guard let samePhoto = matching.first else { return }
        if !samePhoto.isSelected { samePhoto.tap() }
        confirmLimitedSelection()
        XCTAssertTrue(app.buttons["editor-done"].waitForExistence(timeout: 15))
        app.buttons["Cancel"].tap()

        // Two selected originals while only one is accessible must not open a
        // one-photo editor or silently import either inaccessible original.
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
        app.buttons["make-collage"].tap()
        selectSystemPhotos(app, indices: [0, 1])
        XCTAssertTrue(manage.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["editor-done"].exists)
        XCTAssertFalse(app.buttons["collage-done"].exists)
        manage.tap()
        XCTAssertTrue(waitForSystemPhotoPicker(app))
        let selected = systemPhotoCandidates(app).filter { $0.isSelected }
        XCTAssertEqual(selected.count, 1, "The public selection trait must identify exactly the one permitted fixture")
        guard let permitted = selected.first else { return }
        permitted.tap()
        confirmLimitedSelection()
        XCTAssertTrue(manage.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["photos-state"].label.contains("unavailable"))
        XCTAssertFalse(app.buttons["collage-done"].exists)
        app.buttons["selected-photos-cancel"].tap()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }

    private func chooseExactLimitedAuthorization() {
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let title = "Allow “Celluloid” to access your photo library?"
        let approved = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            if self.app.buttons["manage-photos"].exists || !self.systemPhotoCandidates(self.app).isEmpty { return true }
            guard let alert = [system.alerts[title], self.app.alerts[title]].first(where: { $0.exists }) else { return false }
            let choices = alert.buttons.matching(NSPredicate(format: "label IN %@", ["Select Photos…", "Select Photos...", "Select Photos", "Allow Limited Access", "Limited Access"]))
            guard choices.count == 1, choices.element.isEnabled, choices.element.isHittable else { return false }
            choices.element.tap()
            return true
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [approved], timeout: 10), .completed)
    }

    private func confirmLimitedSelection() {
        let choices = app.buttons.matching(NSPredicate(format: "label IN %@", ["Update", "Done", "Add"]))
            .allElementsBoundByIndex.filter { $0.isEnabled && $0.isHittable }
        XCTAssertEqual(choices.count, 1, "Only the visible public limited-selection confirmation is allowed")
        choices.first?.tap()
    }
}
