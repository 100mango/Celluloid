import XCTest
import UIKit

final class CelluloidUITests: XCTestCase {
    private var app: XCUIApplication!
    private var recordedFailure = false
    override func record(_ issue: XCTIssue) {
        // Capture the failing orientation before tearDown rotates the simulator.
        // Do not query hittability again here: that can itself record a new issue.
        if !recordedFailure, app != nil {
            recordedFailure = true
            attachScreenshot("celluloid-failure-" + name)
            print("UI_FAILURE_STATE name=\(name) orientation=\(XCUIDevice.shared.orientation.rawValue) state=\(app.state.rawValue)")
            print("UI_FAILURE_APP_BEGIN " + String(app.debugDescription.prefix(24000)))
            print("UI_FAILURE_APP_END")
        }
        super.record(issue)
    }
    override func setUp() { super.setUp(); continueAfterFailure = false; app = XCUIApplication() }
    override func tearDown() { XCUIDevice.shared.orientation = .portrait; app.terminate(); super.tearDown() }
    private func launch(_ arguments: [String] = [], language: String = "en") {
        app.launchArguments = arguments + ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "zh-Hans" ? "zh_CN" : "en_US"]
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 10))
    }
    func testHomeChoiceGeometryInEnglishAndChineseAcrossRotation() {
        for language in ["en", "zh-Hans"] {
            var normalFooterHeight: CGFloat = 0
            for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
                XCUIDevice.shared.orientation = .portrait
                launch(["-UIPreferredContentSizeCategoryName", category.rawValue], language: language)
                let initialFooterHeight = app.buttons["privacy-policy"].frame.height
                if category == .large { normalFooterHeight = initialFooterHeight }
                else { XCTAssertGreaterThan(initialFooterHeight, normalFooterHeight, "The largest text setting must actually affect the app") }
                for orientation in [UIDeviceOrientation.portrait, .landscapeLeft] {
                    XCUIDevice.shared.orientation = orientation
                    let edit = app.buttons["edit-photo"]
                    let collage = app.buttons["make-collage"]
                    let footer = app.buttons["privacy-policy"]
                    XCTAssertTrue(edit.isHittable && collage.isHittable && footer.isHittable)
                    XCTAssertGreaterThanOrEqual(edit.frame.height, 120)
                    XCTAssertGreaterThanOrEqual(collage.frame.height, 120)
                    XCTAssertFalse(edit.frame.intersects(collage.frame), "Primary choices must not collapse together")
                    XCTAssertGreaterThanOrEqual(footer.frame.minY + 1, max(edit.frame.maxY, collage.frame.maxY))
                    XCTAssertLessThan(footer.frame.height, app.frame.height * 0.40)
                }
                app.terminate()
            }
        }
    }

    func testPrivacyPolicyEntryRemainsAccessibleAndCanClose() {
        launch()
        let policy = app.buttons["privacy-policy"]
        XCTAssertTrue(policy.isHittable)
        XCTAssertEqual(policy.label, "Privacy Policy")
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(policy.isHittable)
        policy.tap()
        // The browser's Close action is available even when external networking is offline.
        let close = app.buttons["Close"]
        let visible = close.waitForExistence(timeout: 15)
        if !visible {
            print("PRIVACY_ACCESSIBILITY_BEGIN")
            print(String(app.debugDescription.prefix(18000)))
            print("PRIVACY_ACCESSIBILITY_END")
        }
        XCTAssertTrue(visible, "The policy browser must provide its explicit Close control")
        close.tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
        XCTAssertTrue(policy.isHittable)
    }

    func testDeniedPhotosShowsRecoveryAndCanCancelRepeatedly() {
        launch(["--photos-denied"])
        for _ in 0..<2 {
            app.buttons["edit-photo"].tap()
            let state = app.staticTexts["photos-state"]
            XCTAssertTrue(state.waitForExistence(timeout: 5))
            XCTAssertTrue(state.label.contains("Settings"))
            XCTAssertFalse(app.buttons["picker-done"].isEnabled)
            app.buttons["Cancel"].tap()
            XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
        }
    }
    func testLimitedEmptyPhotosHasManagementAndAdaptiveLayout() {
        launch(["--photos-limited-empty"])
        app.buttons["make-collage"].tap()
        XCTAssertTrue(app.buttons["manage-photos"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["photos-state"].label.contains("No photos"))
        XCUIDevice.shared.orientation = .landscapeLeft
        // Retain a strict failure, then collect whether actual interaction or only
        // the immediate accessibility activation calculation is affected.
        continueAfterFailure = true
        let cancel = app.buttons["Cancel"]
        let immediatelyHittable = cancel.isHittable
        XCTAssertTrue(immediatelyHittable)
        if !immediatelyHittable {
            let settled = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in cancel.isHittable }, object: nil)
            let settledResult = XCTWaiter.wait(for: [settled], timeout: 3)
            print("ROTATION_HIT_DIAGNOSTIC initial=\(immediatelyHittable) settled=\(settledResult.rawValue) app=\(app.frame) cancel=\(cancel.frame)")
            // This targets the visible native button's observed center. A passing
            // dismissal here is diagnostic only; it cannot erase the failure above.
            cancel.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            let dismissed = app.buttons["make-collage"].waitForExistence(timeout: 5)
            print("ROTATION_CENTER_TAP_DISMISSED \(dismissed)")
            attachScreenshot("celluloid-failure-cancel-after-center-tap")
            print("ROTATION_AFTER_TAP_APP " + String(app.debugDescription.prefix(16000)))
            XCTAssertTrue(dismissed)
        } else { cancel.tap() }
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }
    func testSeededPhotoEditingSaveAndReopen() {
        launch()
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 15), "CI must seed Photos and grant simulator Photos permission")
        app.descendants(matching: .any)["photo-0"].tap()
        app.buttons["picker-done"].tap()
        let done = app.buttons["editor-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 15))
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: done)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        app.buttons["tool-filter"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.element(boundBy: 1).tap()
        // Picker selection dismisses its sheet; the editor should survive backgrounding.
        if app.buttons["Cancel"].exists && !done.isHittable { app.buttons["Cancel"].tap() }
        app.buttons["tool-sticker"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        app.buttons["tool-bubble"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        let text = app.textViews["bubble-text"]
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        text.tap()
        text.typeText("Hello")
        app.buttons["bubble-text-done"].tap()
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        let bubble = app.images.matching(identifier: "attachment-image").allElementsBoundByIndex.last
        if let bubble = bubble, bubble.isHittable {
            let start = bubble.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            start.press(forDuration: 0.2, thenDragTo: start.withOffset(CGVector(dx: 100, dy: 30)))
        }
        emitScreenshot("edited-fixture")
        XCUIDevice.shared.press(.home)
        app.activate()
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        XCUIDevice.shared.orientation = .landscapeLeft
        let shareDone = app.buttons["share-done"]
        XCTAssertTrue(shareDone.isHittable, "Saved-photo dismissal must remain visible in compact landscape")
        XCTAssertTrue(app.frame.contains(shareDone.frame))
        shareDone.tap()
        XCUIDevice.shared.orientation = .portrait
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 10))
        app.descendants(matching: .any)["photo-0"].tap()
        app.buttons["picker-done"].tap()
        XCTAssertTrue(app.buttons["editor-done"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["tool-bubble"].isHittable)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }
    func testTwoPhotoCollageZoomRotateAndSave() {
        launch()
        app.buttons["make-collage"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-1"].waitForExistence(timeout: 15))
        app.descendants(matching: .any)["photo-0"].tap()
        app.descendants(matching: .any)["photo-1"].tap()
        app.buttons["picker-done"].tap()
        let done = app.buttons["collage-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 10))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: done)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        let image = app.scrollViews["collage-image"].firstMatch
        XCTAssertTrue(image.waitForExistence(timeout: 5))
        image.pinch(withScale: 1.5, velocity: 1)
        image.swipeLeft()
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(done.isHittable)
        XCUIDevice.shared.orientation = .portrait
        emitScreenshot("collage-preview")
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(app.buttons["share-done"].isHittable)
        app.buttons["share-done"].tap()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }

    private func emitScreenshot(_ name: String) {
        // Two bounded screenshots per CI job, from the iPhone run and synthetic data only.
        guard UIDevice.current.userInterfaceIdiom == .phone,
              UIScreen.main.bounds.width < 400,
              UIScreen.main.traitCollection.userInterfaceStyle == .dark,
              let image = UIImage(data: app.screenshot().pngRepresentation),
              let jpeg = image.jpegData(compressionQuality: 0.55), jpeg.count <= 500_000 else { return }
        addJPEG(jpeg, name: "celluloid-evidence-" + name)
    }

    private func attachScreenshot(_ name: String) {
        guard let jpeg = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.55),
              jpeg.count <= 500_000 else {
            print("UI_FAILURE_SCREENSHOT_EXCEEDS_BOUND")
            return
        }
        addJPEG(jpeg, name: name)
    }
    private func addJPEG(_ jpeg: Data, name: String) {
        let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

}
