import XCTest

/// Real production processor/results UI starting from an explicitly seeded durable
/// inbox. This does not simulate or establish paired WatchConnectivity delivery.
final class PhoneCompanionUITests: XCTestCase {
    private var failClosedInterruption: NSObjectProtocol?
    override func setUpWithError() throws {
        try super.setUpWithError()
        // Install before every launch. Known consent/dialog controls are handled
        // explicitly by the test; every otherwise-unhandled interruption stops
        // this process without returning to XCTest's default auto-handler.
        failClosedInterruption = addUIInterruptionMonitor(withDescription: "Abort every unhandled native system interruption") { _ in
            // No UI query, XCTest failure recorder or throwable callback work:
            // none may fail and fall through to another monitor/default action.
            print("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=phone")
            fatalError("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=phone; unexpected interruption; no alert action taken")
        }
    }
    private let processID = "58B78AAA-30B8-44DB-BD4F-10762900A001"
    private let pendingID = "58B78AAA-30B8-44DB-BD4F-10762900A002"
    override func tearDownWithError() throws {
        defer {
            if let monitor = failClosedInterruption { removeUIInterruptionMonitor(monitor) }
            failClosedInterruption = nil
        }
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
        try verifyPendingLargeText(app)
        XCTAssertTrue(resume.waitForExistence(timeout: 20)); XCTAssertTrue(discard.exists)

        // Cancel a genuine pending-discard dialog and prove that both requests
        // survive a process relaunch before any local processing begins.
        try reveal(discard, in: app); discard.tap()
        try dismissConfirmationWithoutChangingData(app, action: "Discard Pending Request", state: "pending-discard")
        XCTAssertFalse(app.buttons["companion.result." + pendingID].exists, "Discard must never also invoke the same row's Resume action")
        XCTAssertFalse(app.buttons["companion.result." + processID].exists)
        XCTAssertTrue(resume.exists); XCTAssertTrue(discard.exists)
        app.terminate(); app.launch()
        XCTAssertTrue(resume.waitForExistence(timeout: 20)); XCTAssertTrue(discard.exists)
        try reveal(resume, in: app); resume.tap()
        let result = app.buttons["companion.result." + processID]
        XCTAssertTrue(result.waitForExistence(timeout: 30))
        XCTAssertFalse(resume.exists); XCTAssertTrue(discard.exists)
        XCTAssertFalse(app.sheets.firstMatch.exists, "Resume must not also open its row's discard dialog")
        XCTAssertFalse(app.buttons["companion.result." + pendingID].exists)
        XCTAssertTrue(app.staticTexts["Ready on iPhone; Watch delivery is pending or failed."].exists)
        try reveal(result, in: app); result.tap()
        XCTAssertTrue(app.images["companion.preview"].waitForExistence(timeout: 15))
        try audit(app, state: "locally-processed-result")

        // A canceled result delete must preserve the full output and its request
        // association through another real process relaunch.
        let remove = app.buttons["companion.delete"]
        try reveal(remove, in: app); remove.tap()
        try dismissConfirmationWithoutChangingData(app, action: "Delete Phone Result", state: "result-delete")
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

        // Reuse this real completed request while it still exists. No new
        // fixture/transport path is inserted into the production application.
        try chineseResultSave(app, resultID: processID)
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch(); XCTAssertTrue(result.waitForExistence(timeout: 20)); try reveal(result, in: app); result.tap()
        XCTAssertTrue(app.images["companion.preview"].waitForExistence(timeout: 15))
        try reveal(remove, in: app); remove.tap()
        let deletePanel = try confirmationPanel(in: app, action: "Delete Phone Result")
        let confirmDelete = deletePanel.buttons["Delete Phone Result"].firstMatch
        XCTAssertTrue(confirmDelete.isHittable); confirmDelete.tap()
        XCTAssertTrue(discard.waitForExistence(timeout: 15)); XCTAssertFalse(result.exists)
        try reveal(discard, in: app); discard.tap()
        let discardPanel = try confirmationPanel(in: app, action: "Discard Pending Request")
        let confirmDiscard = discardPanel.buttons["Discard Pending Request"].firstMatch
        XCTAssertTrue(confirmDiscard.isHittable); confirmDiscard.tap()
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts["companion.empty"].waitForExistence(timeout: 20))
        XCTAssertFalse(result.exists); XCTAssertFalse(discard.exists); XCTAssertFalse(resume.exists)
        try audit(app, state: "explicit-local-deletion-empty-inbox")
        print("PHONE_COMPANION_REAL_UI seeded inbox/cancel/relaunch/local resume/Photos write-refetch/delete completed; paired delivery remains untested")
    }
    @MainActor private func verifyPendingLargeText(_ app: XCUIApplication) throws {
        let empty = app.staticTexts["companion.empty"]
        XCTAssertTrue(empty.exists); let ordinaryHeight = empty.frame.height
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["companion.resume." + processID].waitForExistence(timeout: 20))
        try reveal(empty, in: app)
        let largeHeight = empty.frame.height
        print("PHONE_PENDING_TEXT_SIZE ordinaryHeight=\(ordinaryHeight) largeHeight=\(largeHeight) fullValue=\(empty.label)")
        let previous = continueAfterFailure; continueAfterFailure = true
        XCTAssertGreaterThan(largeHeight, ordinaryHeight, "The existing empty-result explanation must actually scale; a launch argument is not proof")
        continueAfterFailure = previous
        capture(app, name: "native-phone-large-pending-inbox")
        try audit(app, state: "large-pending-inbox")
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
    }
    @MainActor private func confirmationPanel(in app: XCUIApplication, action: String) throws -> XCUIElement {
        let popover = app.popovers.containing(.button, identifier: action).firstMatch
        let compact = app.sheets.containing(.button, identifier: "Cancel").firstMatch
        let presented = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            popover.exists || (compact.exists && compact.buttons[action].exists)
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [presented], timeout: 5), .completed, app.debugDescription)
        // The underlying result is itself a sheet with a same-named Delete
        // button. Scope to the actual popover or compact Cancel-bearing panel.
        return popover.exists ? popover : compact
    }
    /// A regular-size-class confirmation is a real system popover with no
    /// Cancel button. Dismiss only its observed outside-dismiss region, rather
    /// than invoking model state or assuming the compact action-sheet shape.
    @MainActor private func dismissConfirmationWithoutChangingData(_ app: XCUIApplication, action: String, state: String) throws {
        let panelElement = try confirmationPanel(in: app, action: action)
        print("PHONE_COMPANION_CONFIRMATION_AX state=\(state) " + String(app.debugDescription.prefix(24000)))
        capture(app, name: "native-phone-" + state + "-confirmation")
        let cancel = panelElement.buttons["Cancel"].firstMatch
        if cancel.exists {
            XCTAssertTrue(cancel.isHittable); cancel.tap()
            XCTAssertTrue(cancel.waitForNonExistence(timeout: 5))
            return
        }
        let popover = app.popovers.firstMatch
        let dismiss = app.otherElements["PopoverDismissRegion"].firstMatch
        XCTAssertTrue(popover.exists); XCTAssertTrue(dismiss.exists)
        let bounds = dismiss.frame, panel = popover.frame
        XCTAssertFalse(bounds.isEmpty); XCTAssertFalse(panel.isEmpty)
        let choices = [CGPoint(x: bounds.midX, y: bounds.maxY - 24),
                       CGPoint(x: bounds.minX + 24, y: bounds.midY),
                       CGPoint(x: bounds.maxX - 24, y: bounds.midY)]
        let point = try XCTUnwrap(choices.first { bounds.contains($0) && !panel.insetBy(dx: -24, dy: -24).contains($0) })
        print("PHONE_COMPANION_CONFIRMATION_DISMISS state=\(state) popover=\(panel) dismissRegion=\(bounds) tap=\(point)")
        dismiss.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: point.x - bounds.minX, dy: point.y - bounds.minY)).tap()
        XCTAssertTrue(popover.waitForNonExistence(timeout: 5), app.debugDescription)
        XCTAssertFalse(dismiss.exists)
    }
    @MainActor private func chineseResultSave(_ app: XCUIApplication, resultID: String) throws {
        var ordinaryHeight: CGFloat = 0
        for large in [false, true] {
            app.terminate()
            app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-UIPreferredContentSizeCategoryName",
                                   large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch()
            XCTAssertTrue(app.navigationBars["手表照片"].waitForExistence(timeout: 15))
            let result = app.buttons["companion.result." + resultID]
            XCTAssertTrue(result.waitForExistence(timeout: 20)); try reveal(result, in: app); result.tap()
            XCTAssertTrue(app.images["companion.preview"].waitForExistence(timeout: 15))
            let description = app.staticTexts["处理结果采用从手表接收的图像分辨率。保存时会新建一张照片，现有图库照片保持不变。"]
            XCTAssertTrue(description.waitForExistence(timeout: 10))
            let measured = description.frame.height
            if large {
                continueAfterFailure = true
                XCTAssertGreaterThan(measured, ordinaryHeight, "Large-text coverage requires an actual larger rendered paragraph, not just a launch argument")
                continueAfterFailure = false
            } else { ordinaryHeight = measured }
            let save = app.buttons["companion.save"]
            XCTAssertEqual(save.label, "将图片存入照片图库")
            try reveal(save, in: app); save.tap()
            XCTAssertTrue(app.staticTexts["已存入照片图库，并重新读取图片验证成功。"].waitForExistence(timeout: 45))
            print("PHONE_ZH_HANS_RESULT_SAVE requestedLarge=\(large) paragraphHeight=\(measured) ordinaryHeight=\(ordinaryHeight) actual Photos readback complete")
            capture(app, name: large ? "native-phone-zh-Hans-large-result" : "native-phone-zh-Hans-result")
            try audit(app, state: large ? "zh-Hans-large-result" : "zh-Hans-result")
        }
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
        print("PHONE_COMPANION_AUDIT_STATE state=\(state) " + String(app.debugDescription.prefix(24000)))
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
