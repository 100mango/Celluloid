import XCTest

/// Real production processor/results UI starting from an explicitly seeded durable
/// inbox. This does not simulate or establish paired WatchConnectivity delivery.
final class PhoneCompanionUITests: XCTestCase {
    private let processID = "58B78AAA-30B8-44DB-BD4F-10762900A001"
    private let pendingID = "58B78AAA-30B8-44DB-BD4F-10762900A002"
    override func tearDownWithError() throws {
        let app = XCUIApplication(); if app.state != .notRunning { app.terminate() }
        try super.tearDownWithError()
    }
    @MainActor func testSeededDurableRequestResumePhotosReadbackRelaunchAndDelete() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["CELLULOID_PHONE_OUTPUT_PROOF"] = "YES"
        app.launch(); defer { app.terminate() }
        let resume = app.buttons["companion.resume." + processID]
        let discard = app.buttons["companion.discard." + pendingID]
        XCTAssertTrue(resume.waitForExistence(timeout: 20))
        XCTAssertTrue(discard.exists)
        try audit(app, state: "seeded-pending-inbox")
        capture(app, name: "native-phone-seeded-pending-inbox")

        // Cancel a genuine pending-discard dialog and prove that both requests
        // survive a process relaunch before any local processing begins.
        try reveal(discard, in: app); discard.tap()
        let cancel = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(cancel.waitForExistence(timeout: 5)); cancel.tap()
        app.terminate(); app.launch()
        XCTAssertTrue(resume.waitForExistence(timeout: 20)); XCTAssertTrue(discard.exists)
        try reveal(resume, in: app); resume.tap()
        let result = app.buttons["companion.result." + processID]
        XCTAssertTrue(result.waitForExistence(timeout: 30))
        XCTAssertFalse(resume.exists); XCTAssertTrue(discard.exists)
        XCTAssertTrue(app.staticTexts["Ready on iPhone; Watch delivery is pending or failed."].exists)
        try reveal(result, in: app); result.tap()
        XCTAssertTrue(app.images["companion.preview"].waitForExistence(timeout: 15))
        try audit(app, state: "locally-processed-result")

        // A canceled result delete must preserve the full output and its request
        // association through another real process relaunch.
        let remove = app.buttons["companion.delete"]
        try reveal(remove, in: app); remove.tap()
        XCTAssertTrue(cancel.waitForExistence(timeout: 5)); cancel.tap()
        app.buttons["companion.done"].tap()
        app.terminate(); app.launch()
        XCTAssertTrue(result.waitForExistence(timeout: 20)); XCTAssertTrue(discard.exists)
        try reveal(result, in: app); result.tap()
        let save = app.buttons["companion.save"]
        try reveal(save, in: app); save.tap()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if system.alerts.firstMatch.waitForExistence(timeout: 8) {
            print("PHONE_COMPANION_PHOTOS_PERMISSION_AX " + String(system.alerts.debugDescription.prefix(16000)))
            XCTAssertTrue(system.alerts.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Celluloid'")).firstMatch.exists)
            let allow = system.alerts.buttons.matching(NSPredicate(format: "label == 'Allow Full Access' OR label == 'Allow Access to All Photos'")).firstMatch
            XCTAssertTrue(allow.waitForExistence(timeout: 5)); allow.tap()
        }
        let verified = app.staticTexts["Saved to Photos and verified by reading the image back."]
        XCTAssertTrue(verified.waitForExistence(timeout: 45), app.debugDescription)
        capture(app, name: "native-phone-real-photos-save-readback")
        try audit(app, state: "photos-output-verified")

        try reveal(remove, in: app); remove.tap()
        let confirmDelete = app.sheets.buttons["Delete Phone Result"].firstMatch
        XCTAssertTrue(confirmDelete.waitForExistence(timeout: 5)); confirmDelete.tap()
        XCTAssertTrue(discard.waitForExistence(timeout: 15)); XCTAssertFalse(result.exists)
        try reveal(discard, in: app); discard.tap()
        let confirmDiscard = app.sheets.buttons["Discard Pending Request"].firstMatch
        XCTAssertTrue(confirmDiscard.waitForExistence(timeout: 5)); confirmDiscard.tap()
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts["companion.empty"].waitForExistence(timeout: 20))
        XCTAssertFalse(result.exists); XCTAssertFalse(discard.exists); XCTAssertFalse(resume.exists)
        try audit(app, state: "explicit-local-deletion-empty-inbox")
        print("PHONE_COMPANION_REAL_UI seeded inbox/cancel/relaunch/local resume/Photos write-refetch/delete completed; paired delivery remains untested")
    }
    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        for _ in 0..<6 {
            if element.isHittable { return }
            app.swipeUp()
        }
        XCTFail("Companion control remained outside the visible scroll area: " + element.identifier)
    }
    @MainActor private func audit(_ app: XCUIApplication, state: String) throws {
        guard #available(iOS 27.0, *) else { return }
        let previous = continueAfterFailure; continueAfterFailure = true
        defer { continueAfterFailure = previous }
        try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE state=phone-\(state) description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false
        }
    }
    @MainActor private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
