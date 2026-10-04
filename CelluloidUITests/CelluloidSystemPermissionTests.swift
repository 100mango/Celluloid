import XCTest
import UIKit

/// Run explicitly after simctl changes the real app Photos grant. These tests do
/// not use the DEBUG authorization overrides and are excluded from the main suite.
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
    }
    func testRealGrantedAccessCanSelectFixture() {
        app.resetAuthorizationStatus(for: .photos)
        let monitor = installExpectedFullPhotosAccessMonitor()
        defer { removeUIInterruptionMonitor(monitor) }
        openPicker()
        let fixture = app.descendants(matching: .any)["photo-0"]
        XCTAssertTrue(waitForFullPhotoAccessPicker(app))
        assertFullPhotoAccessPicker(app)
        fixture.tap()
        XCTAssertTrue(app.buttons["picker-done"].isEnabled)
        app.buttons["Cancel"].tap()
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }
    func testRealRevokedAccessClearsSelectionAndHasRecovery() {
        openPicker()
        let state = app.staticTexts["photos-state"]
        XCTAssertTrue(state.waitForExistence(timeout: 10))
        XCTAssertTrue(state.label.contains("Settings"))
        XCTAssertGreaterThanOrEqual(state.frame.minY, app.navigationBars.firstMatch.frame.maxY, "Permission recovery text must not hide underneath the navigation bar")
        XCTAssertTrue(app.buttons["photos-settings"].isHittable)
        XCTAssertFalse(app.buttons["picker-done"].isEnabled)
        XCTAssertFalse(app.descendants(matching: .any)["photo-0"].exists)
        app.buttons["Cancel"].tap()
        app.buttons["edit-photo"].tap()
        XCTAssertFalse(app.buttons["picker-done"].isEnabled)
    }
    func testRealLimitedSelectionAndManagement() {
        let monitor = installExpectedLimitedPhotosAccessMonitor()
        defer { removeUIInterruptionMonitor(monitor) }
        openPicker()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let limitedNames = ["Select Photos…", "Select Photos...", "Select Photos", "Allow Limited Access", "Limited Access"]
        let permissionTitle = "Allow “Celluloid” to access your photo library?"
        let manage = app.buttons["manage-photos"]
        var limited: XCUIElement?
        var observedPermission: XCUIElement?
        for _ in 0..<10 {
            if manage.exists { break } // The narrow monitor may have performed the same explicit limited choice.
            if let alert = [system.alerts[permissionTitle], app.alerts[permissionTitle]].first(where: { $0.exists }) {
                let choices = alert.buttons.matching(NSPredicate(format: "label IN %@", limitedNames))
                if choices.count == 1, choices.element.isEnabled, choices.element.isHittable {
                    observedPermission = alert; limited = choices.element; break
                }
            }
            _ = system.alerts.firstMatch.waitForExistence(timeout: 1)
        }
        if let limited = limited {
            XCTAssertEqual(observedPermission?.label, permissionTitle)
            XCTAssertTrue(observedPermission?.exists == true)
            print("DIRECT_LIMITED_PHOTOS_AUTHORIZATION_ACTION " + limited.label)
            limited.tap()
        }
        else if !manage.exists {
            recordLimitedDiagnostics(system: system)
            XCTFail("Neither the exact limited-access action nor its required management postcondition appeared")
            return
        }
        // Observed iOS27 selection action grants limited access with zero selected
        // assets and returns to this app. Use its real management entry to choose.
        XCTAssertTrue(manage.waitForExistence(timeout: 10))
        if manage.isHittable {
            let message = app.staticTexts["photos-state"]
            if message.exists { XCTAssertGreaterThanOrEqual(message.frame.minY, app.navigationBars.firstMatch.frame.maxY) }
            manage.tap()
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.dateFormat = "MMMM dd"
        let today = formatter.string(from: Date())
        // Keep the observed identifier/date selection. Filter on the server once,
        // instead of querying every photo's exists, hittability and label repeatedly.
        let fixtureQuery = app.images.matching(NSPredicate(format:
            "identifier == %@ AND (label CONTAINS %@ OR label CONTAINS %@)",
            "PXGGridLayout-Info", today, "Today"))
        func fixtureCandidates() -> [XCUIElement] { fixtureQuery.allElementsBoundByIndex }
        _ = fixtureQuery.firstMatch.waitForExistence(timeout: 10)
        let cells = fixtureCandidates()
        print("SYSTEM_LIMITED_GRID_CANDIDATES " + cells.map { $0.label }.joined(separator: " | "))
        guard let fixture = cells.last else {
            recordLimitedDiagnostics(system: system)
            XCTFail("Could not verify a synthetic fixture dated today in the real limited picker")
            return
        }
        let hittable = fixture.isHittable
        print("SYSTEM_LIMITED_SELECTED_CANDIDATE label=\(fixture.label) frame=\(fixture.frame) hittable=\(hittable)")
        if !hittable { recordLimitedDiagnostics(system: system) }
        XCTAssertTrue(hittable, "The observed synthetic fixture must expose a genuine semantic tap point")
        fixture.tap()
        let confirmation = [app.buttons["Update"], app.buttons["Done"], app.buttons["Add"], system.buttons["Done"], system.buttons["Add"]].first { $0.exists && $0.isHittable && $0.isEnabled }
        XCTAssertNotNil(confirmation)
        confirmation?.tap()
        XCTAssertTrue(app.buttons["manage-photos"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["photo-1"].exists, "Limited access must expose only the selected synthetic fixture")
        app.descendants(matching: .any)["photo-0"].tap()
        XCTAssertTrue(app.buttons["picker-done"].isEnabled)
        app.buttons["manage-photos"].tap()
        XCTAssertTrue(fixtureQuery.firstMatch.waitForExistence(timeout: 10))
        let selected = fixtureCandidates().filter { $0.isSelected || (($0.value as? String)?.localizedCaseInsensitiveContains("selected") ?? false) }
        guard selected.count == 1 else {
            recordLimitedDiagnostics(system: system)
            XCTFail("The real management picker must identify exactly one selected synthetic fixture before removal")
            return
        }
        selected[0].tap()
        [app.buttons["Update"], app.buttons["Done"], app.buttons["Add"], system.buttons["Done"], system.buttons["Add"]].first { $0.exists && $0.isHittable && $0.isEnabled }?.tap()
        XCTAssertTrue(app.buttons["picker-done"].waitForExistence(timeout: 10))
        let pruned = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !self.app.buttons["picker-done"].isEnabled && !self.app.descendants(matching: .any)["photo-0"].exists
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [pruned], timeout: 10), .completed)
        XCTAssertTrue(app.staticTexts["photos-state"].label.contains("No photos"))
        print("SYSTEM_LIMITED_RESULT:PASS real limited authorization, selection, management and revoked-selection pruning")
    }
    private func recordLimitedDiagnostics(system: XCUIApplication) {
        // Named XCTest attachment is exported by the workflow AFTER test execution,
        // keeping large screenshot bytes out of the live XCTest activity stream.
        let jpeg = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.55)!
        XCTAssertLessThanOrEqual(jpeg.count, 500_000)
        let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
        attachment.name = "celluloid-limited-picker-diagnostic"
        attachment.lifetime = .keepAlways
        add(attachment)
        print("SYSTEM_LIMITED_DIAGNOSTIC_APP " + String(app.debugDescription.prefix(20000)))
        print("SYSTEM_LIMITED_DIAGNOSTIC_SYSTEM " + String(system.debugDescription.prefix(24000)))
        print("SYSTEM_LIMITED_EFFECTIVE_STATE manage=\(app.buttons["manage-photos"].exists) settings=\(app.buttons["photos-settings"].exists) done=\(app.buttons["picker-done"].isEnabled)")
    }

}
