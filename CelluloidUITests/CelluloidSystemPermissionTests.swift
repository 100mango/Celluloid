import XCTest

/// Run explicitly after simctl changes the real app Photos grant. These tests do
/// not use the DEBUG authorization overrides and are excluded from the main suite.
final class CelluloidSystemPermissionTests: XCTestCase {
    private let app = XCUIApplication()
    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
    }
    override func tearDown() { app.terminate(); super.tearDown() }
    private func openPicker() {
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 10))
        app.buttons["edit-photo"].tap()
    }
    func testRealGrantedAccessCanSelectFixture() {
        openPicker()
        let fixture = app.descendants(matching: .any)["photo-0"]
        XCTAssertTrue(fixture.waitForExistence(timeout: 15))
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
        XCTAssertTrue(app.buttons["photos-settings"].isHittable)
        XCTAssertFalse(app.buttons["picker-done"].isEnabled)
        XCTAssertFalse(app.descendants(matching: .any)["photo-0"].exists)
        app.buttons["Cancel"].tap()
        app.buttons["edit-photo"].tap()
        XCTAssertFalse(app.buttons["picker-done"].isEnabled)
    }
    func testRealLimitedSelectionAndManagement() {
        openPicker()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let limitedNames = ["Select Photos…", "Select Photos...", "Select Photos", "Allow Limited Access", "Limited Access"]
        var limited: XCUIElement?
        for _ in 0..<10 {
            limited = limitedNames.flatMap { [app.buttons[$0], system.buttons[$0]] }.first { $0.exists && $0.isHittable }
            if limited != nil { break }
            _ = system.alerts.firstMatch.waitForExistence(timeout: 1)
        }
        guard let limited = limited else {
            print("SYSTEM_LIMITED_PROMPT_APP " + String(app.debugDescription.prefix(12000)))
            print("SYSTEM_LIMITED_PROMPT_SYSTEM " + String(system.debugDescription.prefix(12000)))
            XCTFail("The real Photos authorization sheet has no recognized limited-access action")
            return
        }
        limited.tap()
        let picker = app.collectionViews.firstMatch
        _ = picker.waitForExistence(timeout: 10)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.dateFormat = "MMMM d"
        let today = formatter.string(from: Date())
        let cells = app.collectionViews.cells.allElementsBoundByIndex.filter { $0.isHittable && $0.label.contains(today) }
        print("SYSTEM_LIMITED_PICKER " + String(app.debugDescription.prefix(18000)))
        guard let fixture = cells.last else {
            XCTFail("Could not verify a synthetic fixture dated today in the real limited picker")
            return
        }
        fixture.tap()
        let confirmation = [app.buttons["Done"], app.buttons["Add"]].first { $0.exists && $0.isHittable }
        XCTAssertNotNil(confirmation)
        confirmation?.tap()
        XCTAssertTrue(app.buttons["manage-photos"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["photo-1"].exists, "Limited access must expose only the selected synthetic fixture")
        app.buttons["manage-photos"].tap()
        XCTAssertTrue(app.buttons["Done"].waitForExistence(timeout: 10) || app.buttons["Add"].exists)
        [app.buttons["Done"], app.buttons["Add"]].first { $0.isHittable }?.tap()
        XCTAssertTrue(app.buttons["picker-done"].waitForExistence(timeout: 10))
        print("SYSTEM_LIMITED_RESULT:PASS real limited authorization, selected asset and management picker")
    }
}
