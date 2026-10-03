import XCTest

final class NativeWatchUITests: XCTestCase {
    override func tearDownWithError() throws {
        // An XCTest assertion abort can bypass Swift defer. End only the app
        // launched by this case; retain actual failures and runner time bounds.
        let app = XCUIApplication()
        if app.state != .notRunning { app.terminate() }
        try super.tearDownWithError()
    }
    @MainActor func testNativeOfflineGalleryControlsAndPrivacy() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)"]
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.descendants(matching: .any)["watch.import-photo"].firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.descendants(matching: .any)["watch.import-photo"].firstMatch.isHittable)
        let photo = app.descendants(matching: .any)["watch.photo.A2E0E7B0-0A3B-47D3-94E5-309F3614E54A"].firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 10)); photo.tap()
        XCTAssertTrue(app.images["watch.preview"].waitForExistence(timeout: 10))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-watch-offline-photo"; shot.lifetime = .keepAlways; add(shot)
        print("WATCH_NATIVE_UI_AX " + app.debugDescription)
        if #available(watchOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
        // Real system Photos selection and paired-phone file transport are separate gates.
    }
    @MainActor func testOfflinePhotoCompanionUnavailableCancelRelaunchDeleteAndPrivacy() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)"]
        app.launch(); defer { app.terminate() }
        let photo = app.descendants(matching: .any)["watch.photo.B2E0E7B0-0A3B-47D3-94E5-309F3614E54B"].firstMatch
        try reveal(photo, in: app); photo.tap()
        let request = app.buttons["watch.process-phone"]
        try reveal(request, in: app); request.tap()
        let unavailable = app.staticTexts["Open Celluloid on your paired iPhone, then try again."]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 15), "A fresh unpaired Watch must report the actual companion condition")
        let okay = app.buttons["OK"]; XCTAssertTrue(okay.isHittable); okay.tap()
        XCTAssertFalse(app.staticTexts["watch.job-status"].exists, "Unavailable transport must not invent a processing job")
        let remove = app.buttons["watch.remove"]
        try reveal(remove, in: app); remove.tap()
        let cancel = app.buttons["watch.remove-cancel"]
        XCTAssertTrue(cancel.waitForExistence(timeout: 5)); cancel.tap()
        app.terminate(); app.launch()
        XCTAssertTrue(photo.waitForExistence(timeout: 15), "Cancel must preserve the offline copy across relaunch")
        try reveal(photo, in: app); photo.tap(); try reveal(remove, in: app); remove.tap()
        let confirm = app.buttons["watch.remove-confirm"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5)); confirm.tap()
        let preserved = app.descendants(matching: .any)["watch.photo.A2E0E7B0-0A3B-47D3-94E5-309F3614E54A"].firstMatch
        XCTAssertTrue(preserved.waitForExistence(timeout: 15)); XCTAssertFalse(photo.exists)
        app.terminate(); app.launch()
        XCTAssertTrue(preserved.waitForExistence(timeout: 15)); XCTAssertFalse(photo.exists)
        let privacy = app.descendants(matching: .any)["watch.privacy"].firstMatch
        try reveal(privacy, in: app); privacy.tap()
        let policy = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings.")).firstMatch
        XCTAssertTrue(policy.waitForExistence(timeout: 10))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-watch-offline-removal-privacy"; shot.lifetime = .keepAlways; add(shot)
        if #available(watchOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE state=watch-privacy description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false
        } }
        print("WATCH_NATIVE_UI_UNPAIRED_ERROR_CANCEL_RELAUNCH_DELETE verified actual unavailable companion; no file delivery claimed")
    }
    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        for step in 0..<12 {
            if element.isHittable { return }
            let owner = app.scrollViews.containing(.any, identifier: element.identifier).firstMatch
            let viewport = owner.exists ? owner : app.scrollViews.firstMatch
            guard viewport.exists else {
                print("WATCH_SCROLL_FAILURE_AX " + String(app.debugDescription.prefix(24000)))
                XCTFail("No actual scroll container exposes the requested Watch control"); return
            }
            let frame = element.frame, bounds = viewport.frame
            let down = frame.midY < bounds.midY
            print("WATCH_SCROLL_STEP target=\(element.identifier) step=\(step) enabled=\(element.isEnabled) frame=\(frame) viewport=\(bounds) direction=\(down ? "down" : "up")")
            // A full-screen swipe can overshoot a short control. Resolve the
            // current target position each time and scroll its actual container.
            if down { viewport.swipeDown() } else { viewport.swipeUp() }
        }
        print("WATCH_SCROLL_FAILURE_AX " + String(app.debugDescription.prefix(24000)))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-watch-scroll-failure"; shot.lifetime = .keepAlways; add(shot)
        XCTFail("Watch control cannot be reached by ordinary scrolling: " + element.identifier)
    }
    func testSystemPhotosPickerReportsSimulatorLimitationAndCloses() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)"]
        app.launch(); defer { app.terminate() }
        let picker = app.descendants(matching: .any)["watch.import-photo"].firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 20)); picker.tap()
        let unavailable = app.staticTexts["Unable to Load Photos in Simulator"]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["You need to use an Apple Watch."].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "watch-system-photos-simulator-limitation"; shot.lifetime = .keepAlways; add(shot)
        let close = app.buttons["Close"]; XCTAssertTrue(close.isHittable); close.tap()
        XCTAssertTrue(picker.waitForExistence(timeout: 10))
        print("WATCH_NATIVE_PICKER_LIMITATION system PhotosPicker reports physical Apple Watch required; no import-success claim")
    }

}
