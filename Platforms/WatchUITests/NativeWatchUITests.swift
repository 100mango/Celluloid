import XCTest

final class NativeWatchUITests: XCTestCase {
    private var failClosedInterruption: NSObjectProtocol?
    override func setUpWithError() throws {
        try super.setUpWithError()
        // Install before every launch. Known consent/dialog controls are handled
        // explicitly by the test; every otherwise-unhandled interruption stops
        // this process without returning to XCTest's default auto-handler.
        failClosedInterruption = addUIInterruptionMonitor(withDescription: "Abort every unhandled native system interruption") { _ in
            // No UI query, XCTest failure recorder or throwable callback work:
            // none may fail and fall through to another monitor/default action.
            print("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=watch")
            fatalError("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=watch; unexpected interruption; no alert action taken")
        }
    }
    override func tearDownWithError() throws {
        defer {
            if let monitor = failClosedInterruption { removeUIInterruptionMonitor(monitor) }
            failClosedInterruption = nil
        }
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
        print("WATCH_NATIVE_REMOVE_CONFIRMATION_AX " + String(app.debugDescription.prefix(18000)))
        let confirmation = XCTAttachment(screenshot: app.screenshot())
        confirmation.name = "native-watch-remove-confirmation"; confirmation.lifetime = .keepAlways; add(confirmation)
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
    @MainActor func testSimplifiedChineseOfflinePhotoAndLargeText() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); defer { app.terminate() }
        var ordinaryHeight: CGFloat = 0
        for large in [false, true] {
            if app.state != .notRunning { app.terminate() }
            app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-UIPreferredContentSizeCategoryName",
                                   large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch()
            let picker = app.descendants(matching: .any)["watch.import-photo"].firstMatch
            XCTAssertTrue(picker.waitForExistence(timeout: 20)); XCTAssertEqual(picker.label, "选择照片")
            let photo = app.descendants(matching: .any)["watch.photo.A2E0E7B0-0A3B-47D3-94E5-309F3614E54A"].firstMatch
            try reveal(photo, in: app); photo.tap()
            XCTAssertTrue(app.images["watch.preview"].waitForExistence(timeout: 10))
            let explanation = app.staticTexts["预览图最长边为 512 像素"]
            XCTAssertTrue(explanation.waitForExistence(timeout: 10))
            let height = explanation.frame.height
            if large {
                continueAfterFailure = true
                XCTAssertGreaterThan(height, ordinaryHeight, "The requested large Watch text must measurably affect the real localized view")
                continueAfterFailure = false
            } else { ordinaryHeight = height }
            let request = app.buttons["watch.process-phone"]
            XCTAssertEqual(request.label, "在 iPhone 上处理"); try reveal(request, in: app)
            print("WATCH_ZH_HANS_OFFLINE requestedLarge=\(large) captionHeight=\(height) ordinaryHeight=\(ordinaryHeight) processControlFrame=\(request.frame)")
            let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = large ? "native-watch-zh-Hans-large-offline" : "native-watch-zh-Hans-offline"; shot.lifetime = .keepAlways; add(shot)
            if #available(watchOS 27.0, *) {
                let previous = continueAfterFailure; continueAfterFailure = true
                defer { continueAfterFailure = previous }
                try app.performAccessibilityAudit(for: .all) { issue in
                print("NATIVE_ACCESSIBILITY_ISSUE state=watch-zh-Hans requestedLarge=\(large) description=\(issue.compactDescription) element=\(issue.element?.debugDescription ?? "none")"); return false
                }
            }
        }
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
            // Actual 4c endpoint traces show full swipes overshoot by about
            // 270 points and oscillate. Drag only one quarter of this observed
            // viewport, slowly, then stop the finger to avoid fling momentum.
            // The public coordinate gesture's Watch SDK build remains a gate.
            let start = viewport.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.46 : 0.72))
            let end = viewport.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.72 : 0.46))
            print("WATCH_SHORT_DRAG start=\(start.screenPoint) end=\(end.screenPoint)")
            start.press(forDuration: 0.05, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
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
