import XCTest
import UIKit

final class CelluloidUITests: XCTestCase {
    private var app: XCUIApplication!
    private var recordedFailure = false
    private var photosAccessMonitor: NSObjectProtocol?
    private var failClosedMonitor: NSObjectProtocol?
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
    override func setUp() {
        super.setUp(); continueAfterFailure = false; recordedFailure = false
        failClosedMonitor = installFailClosedSystemAlertMonitor()
        app = XCUIApplication()
    }
    override func tearDown() {
        XCUIDevice.shared.orientation = .portrait; app.terminate()
        if let monitor = photosAccessMonitor { removeUIInterruptionMonitor(monitor); photosAccessMonitor = nil }
        if let monitor = failClosedMonitor { removeUIInterruptionMonitor(monitor); failClosedMonitor = nil }
        super.tearDown()
    }
    private func launch(_ arguments: [String] = [], language: String = "en", diagnostics: Bool = true, photosAccess: Bool = false) {
        if photosAccess {
            // A preceding injected denial/limited case must not determine this
            // real granted flow's system state. No unrelated permission is reset.
            app.resetAuthorizationStatus(for: .photos)
            if photosAccessMonitor == nil { photosAccessMonitor = installExpectedFullPhotosAccessMonitor() }
        }
        app.launchArguments = arguments + (diagnostics ? ["--ui-diagnostics"] : []) + ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "zh-Hans" ? "zh_CN" : "en_US"]
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 10))
        waitForStableLayout(["edit-photo", "make-collage", "privacy-policy"],
                            landscape: XCUIDevice.shared.orientation.isLandscape)
    }

    private func rotate(_ orientation: UIDeviceOrientation, observing identifiers: [String]) {
        XCUIDevice.shared.orientation = orientation
        waitForStableLayout(identifiers, landscape: orientation.isLandscape)
    }

    private func waitForStableLayout(_ identifiers: [String], landscape: Bool? = nil, root: XCUIElement? = nil,
                                     file: StaticString = #filePath, line: UInt = #line) {
        let snapshotRoot: XCUIElement = root ?? app
        var prior: [CGRect] = []
        var stableSince = ProcessInfo.processInfo.systemUptime
        var lastSnapshotDetails = "No snapshot captured"
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            // One public snapshot is a coherent, local tree. Querying exists/frame
            // separately for every element made two polls consume the whole bound
            // on SE3, even though the actual interface had already settled.
            guard let snapshot = try? snapshotRoot.snapshot() else { return false }
            func descendants(_ node: XCUIElementSnapshot) -> [XCUIElementSnapshot] {
                [node] + node.children.flatMap { descendants($0) }
            }
            let nodes = descendants(snapshot)
            let matches = identifiers.compactMap { identifier in
                nodes.first { $0.identifier == identifier || ($0.identifier.isEmpty && $0.label == identifier) }
            }
            lastSnapshotDetails = "root=\(snapshot.frame) matches=\(matches.map { $0.identifier }) frames=\(matches.map { $0.frame }) node_count=\(nodes.count)"
            if identifiers.contains("bubble-text") {
                print("SHEET_LAYOUT_SNAPSHOT " + lastSnapshotDetails + " available_identifiers=\(nodes.map { $0.identifier }.filter { !$0.isEmpty })")
            }
            guard matches.count == identifiers.count else { return false }
            let frames = [snapshot.frame] + matches.map { $0.frame }
            guard frames.allSatisfy({ $0.width > 0 && $0.height > 0 && $0.minX.isFinite && $0.minY.isFinite }) else { return false }
            if let landscape = landscape, (frames[0].width > frames[0].height) != landscape { return false }
            let unchanged = prior.count == frames.count && zip(prior, frames).allSatisfy { pair in
                let (a, b) = pair
                return abs(a.minX - b.minX) < 0.25 && abs(a.minY - b.minY) < 0.25 && abs(a.width - b.width) < 0.25 && abs(a.height - b.height) < 0.25
            }
            if unchanged { return ProcessInfo.processInfo.systemUptime - stableSince >= 0.4 }
            prior = frames
            stableSince = ProcessInfo.processInfo.systemUptime
            return false
        }, object: nil)
        let outcome = XCTWaiter.wait(for: [ready], timeout: 8)
        print("LAYOUT_WAIT_RESULT outcome=\(outcome.rawValue) " + lastSnapshotDetails)
        XCTAssertEqual(outcome, .completed,
                       "Assert settled interface geometry rather than an in-flight rotation/foreground frame", file: file, line: line)
        print("LAYOUT_STABLE landscape=\(String(describing: landscape)) frames=\(prior)")
    }
    private func audit(_ screen: String) {
        print("ACCESSIBILITY_AUDIT_BEGIN screen=\(screen)")
        let originalContinue = continueAfterFailure
        continueAfterFailure = true
        defer { continueAfterFailure = originalContinue }
        do {
            try app.performAccessibilityAudit(for: .all) { issue in
                let element = issue.element
                print("ACCESSIBILITY_AUDIT_ISSUE screen=\(screen) type=\(issue.auditType.rawValue) identifier=\(element?.identifier ?? "nil") label=\(element?.label ?? "nil") frame=\(String(describing: element?.frame)) description=\(issue.compactDescription) detail=\(issue.detailedDescription)")
                // This exact class draws persisted photo artwork. System text
                // settings must not reflow saved compositions. The decoration
                // exposes its text to VoiceOver and a separate Dynamic Type text
                // editor, both asserted below. No other category/class is ignored.
                if screen == "editor-with-decorations", issue.auditType == .dynamicType,
                   element?.identifier == "bubble-artwork-text",
                   issue.detailedDescription == "User will not be able to change the font size of this CelluloidKit.BubbleLabel" {
                    print("ACCESSIBILITY_AUDIT_FIXED_ARTWORK_EXCEPTION class=CelluloidKit.BubbleLabel category=dynamicType reason=persisted_photo_typography text_editing_audited_separately")
                    return true
                }
                return false
            }
        } catch { XCTFail("Accessibility audit \(screen) failed: \(error)") }
        print("ACCESSIBILITY_AUDIT_END screen=\(screen)")
    }

    func testAccessibilityHomeAndDeniedPicker() {
        launch(["--photos-denied"], diagnostics: false)
        audit("home")
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(app.staticTexts["photos-state"].waitForExistence(timeout: 5))
        waitForStableLayout(["photos-state", "photos-settings"])
        audit("denied-picker")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }

    func testAccessibilityGrantedPickerEditorAndSaved() {
        launch(diagnostics: false, photosAccess: true)
        app.buttons["edit-photo"].tap()
        let photo = app.descendants(matching: .any)["photo-0"]
        XCTAssertTrue(waitForFullPhotoAccessPicker(app))
        assertFullPhotoAccessPicker(app)
        waitForStableLayout(["photo-0", "picker-done"])
        audit("granted-picker")
        photo.tap()
        app.buttons["picker-done"].tap()
        let done = app.buttons["editor-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 15))
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: done)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        app.buttons["tool-sticker"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        app.buttons["tool-bubble"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        let text = app.textViews["bubble-text"]
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        text.tap()
        text.typeText("Accessible caption")
        app.buttons["bubble-text-done"].tap()
        let accessibleBubble = app.images.matching(identifier: "attachment-image").matching(NSPredicate(format: "value == %@", "Accessible caption")).firstMatch
        XCTAssertTrue(accessibleBubble.waitForExistence(timeout: 5), "Fixed canvas text must be exposed through its editable decoration")
        accessibleBubble.tap()
        let editText = app.buttons.matching(identifier: "bubble-edit-text").allElementsBoundByIndex.first { $0.isHittable }
        XCTAssertNotNil(editText, "The existing decoration must retain a reachable text-edit control")
        editText?.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        XCTAssertEqual(text.value as? String, "Accessible caption")
        XCTAssertEqual(text.label, "Bubble Text")
        // The app-level snapshot omits this modal on iOS27 even though direct
        // queries resolve it. Snapshot the observed container holding both controls.
        let modal = app.otherElements.containing(.textView, identifier: "bubble-text")
            .containing(.button, identifier: "bubble-text-done").firstMatch
        XCTAssertTrue(modal.waitForExistence(timeout: 5))
        waitForStableLayout(["bubble-text", "bubble-text-done"], root: modal)
        XCTAssertTrue(text.isHittable && app.buttons["bubble-text-done"].isHittable)
        XCTAssertTrue(app.frame.contains(text.frame))
        XCTAssertGreaterThan(text.frame.height, app.frame.height * 0.6,
                             "Caption editing must use the full-screen task area")
        XCTAssertLessThanOrEqual(text.frame.width, 720)
        XCTAssertTrue(app.buttons["bubble-text-cancel"].isHittable,
                      "Full-screen editing must retain a reachable discard action")
        audit("bubble-text-editor")
        text.tap()
        text.typeText(" updated")
        // A native tap places the caret where UIKit chooses; it need not append.
        // Require the typed insertion and exact text-to-artwork round trip.
        let editedCaption = text.value as? String ?? ""
        XCTAssertNotEqual(editedCaption, "Accessible caption")
        XCTAssertEqual(editedCaption.replacingOccurrences(of: " updated", with: ""), "Accessible caption")
        app.buttons["bubble-text-done"].tap()
        let updatedBubble = app.images.matching(identifier: "attachment-image")
            .matching(NSPredicate(format: "value == %@", editedCaption)).firstMatch
        XCTAssertTrue(updatedBubble.waitForExistence(timeout: 5),
                      "Editing a reopened caption must update the actual accessible artwork")
        var reopen = app.buttons.matching(identifier: "bubble-edit-text").allElementsBoundByIndex.first { $0.isHittable }
        if reopen == nil {
            updatedBubble.tap()
            reopen = app.buttons.matching(identifier: "bubble-edit-text").allElementsBoundByIndex.first { $0.isHittable }
        }
        XCTAssertNotNil(reopen)
        reopen?.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        text.tap(); text.typeText(" discarded")
        app.buttons["bubble-text-cancel"].tap()
        XCTAssertTrue(updatedBubble.waitForExistence(timeout: 5), "Cancel must preserve the exact last saved caption")
        waitForStableLayout(["editor-done", "tool-filter"])
        audit("editor-with-decorations")
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        waitForStableLayout(["share-done", "share-photo"])
        audit("saved")
        app.buttons["share-done"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
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
                    let edit = app.buttons["edit-photo"]
                    let collage = app.buttons["make-collage"]
                    let footer = app.buttons["privacy-policy"]
                    rotate(orientation, observing: ["edit-photo", "make-collage", "privacy-policy"])
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
        rotate(.landscapeLeft, observing: ["privacy-policy"])
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
        let cancel = app.buttons["Cancel"]
        let manage = app.buttons["manage-photos"]
        rotate(.landscapeLeft, observing: ["Cancel", "manage-photos"])
        XCTAssertTrue(cancel.isHittable)
        XCTAssertTrue(manage.isHittable)
        XCTAssertTrue(app.frame.contains(manage.frame))
        XCTAssertFalse(app.navigationBars.firstMatch.frame.intersects(manage.frame))
        cancel.tap()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }
    func testSeededPhotoEditingSaveAndReopen() {
        launch(photosAccess: true)
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(waitForFullPhotoAccessPicker(app), "The granted flow must finish the exact Photos consent prompt and expose fixtures")
        assertFullPhotoAccessPicker(app)
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
        waitForStableLayout(["editor-done"])
        XCTAssertTrue(done.isEnabled && done.isHittable)
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        let shareDone = app.buttons["share-done"]
        rotate(.landscapeLeft, observing: ["share-done", "share-photo"])
        continueAfterFailure = true
        let settledHittable = shareDone.isHittable
        print("SHARE_HIT_DIAGNOSTIC " + String(describing: shareDone.value))
        XCTAssertTrue(settledHittable, "Saved-photo dismissal must remain visible in compact landscape")
        XCTAssertTrue(app.frame.contains(shareDone.frame))
        if settledHittable { shareDone.tap() }
        else {
            // Preserve the failure. This diagnostic establishes actual touch
            // behavior separately from XCTest's inaccessible activation point.
            shareDone.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            let dismissed = app.buttons["edit-photo"].waitForExistence(timeout: 5)
            print("SHARE_CENTER_TAP_DISMISSED \(dismissed)")
            XCTAssertTrue(dismissed)
            if !dismissed { return }
        }
        rotate(.portrait, observing: ["edit-photo", "make-collage"])
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
        launch(photosAccess: true)
        app.buttons["make-collage"].tap()
        XCTAssertTrue(waitForFullPhotoAccessPicker(app))
        XCTAssertTrue(app.descendants(matching: .any)["photo-1"].waitForExistence(timeout: 5))
        assertFullPhotoAccessPicker(app)
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
        rotate(.landscapeLeft, observing: ["collage-done", "collage-image"])
        XCTAssertTrue(done.isHittable)
        rotate(.portrait, observing: ["collage-done", "collage-image"])
        emitScreenshot("collage-preview")
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        rotate(.landscapeLeft, observing: ["share-done", "share-photo"])
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

// Only expected full-access flows use this monitor. The library contains CI
// fixtures; denied/revoked/limited cases intentionally never install this handler.
extension XCTestCase {
    func waitForFullPhotoAccessPicker(_ app: XCUIApplication) -> Bool {
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let title = "Allow “Celluloid” to access your photo library?"
        let deadline = Date().addingTimeInterval(15)
        repeat {
            // Queries alone do not invoke an interruption monitor. Resolve only
            // this expected Photos prompt directly, before waiting for assets.
            let alerts = [system.alerts[title], app.alerts[title]]
            if let alert = alerts.first(where: { $0.exists }) {
                let actions = alert.buttons.matching(NSPredicate(format: "label IN %@",
                    ["Allow Full Access", "Allow Access to All Photos"]))
                if actions.count == 1, actions.element.isEnabled, actions.element.isHittable {
                    print("EXPECTED_PHOTOS_DIRECT_AUTHORIZATION_ACTION " + actions.element.label)
                    actions.element.tap()
                    let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
                    guard XCTWaiter.wait(for: [dismissed], timeout: 10) == .completed else { return false }
                }
            }
            if app.descendants(matching: .any)["photo-0"].exists { return true }
            Thread.sleep(forTimeInterval: 0.25)
        } while Date() < deadline
        print("EXPECTED_PHOTOS_PREREQUISITE_UNRESOLVED " + String(system.debugDescription.prefix(6000)))
        return false
    }

    func assertFullPhotoAccessPicker(_ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].exists, "Granted flow requires actual assets", file: file, line: line)
        XCTAssertFalse(app.buttons["manage-photos"].exists, "The app exposes this management control for limited access only", file: file, line: line)
        XCTAssertFalse(app.buttons["photos-settings"].exists, "Granted flow cannot remain denied", file: file, line: line)
        print("FULL_ACCESS_PICKER_POSTCONDITION assets_visible=true limited_management=false denied_recovery=false")
    }

    func installExpectedFullPhotosAccessMonitor() -> NSObjectProtocol {
        addUIInterruptionMonitor(withDescription: "Celluloid synthetic Photos full-access prerequisite") { alert in
            guard alert.label == "Allow “Celluloid” to access your photo library?" else { stopForUnexpectedSystemAlert() }
            print("EXPECTED_PHOTOS_AUTHORIZATION_ALERT " + String(alert.debugDescription.prefix(6000)))
            let actions = alert.buttons.matching(NSPredicate(format: "label IN %@",
                ["Allow Full Access", "Allow Access to All Photos"]))
            guard actions.count == 1, actions.element.isEnabled, actions.element.isHittable else { stopForUnexpectedSystemAlert() }
            print("EXPECTED_PHOTOS_AUTHORIZATION_ACTION " + actions.element.label)
            actions.element.tap()
            let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
            guard XCTWaiter.wait(for: [gone], timeout: 10) == .completed else { stopForUnexpectedSystemAlert() }
            return true
        }
    }

    func installFailClosedSystemAlertMonitor() -> NSObjectProtocol {
        addUIInterruptionMonitor(withDescription: "Abort every unexpected system interruption") { _ in
            stopForUnexpectedSystemAlert()
        }
    }

    func installExpectedLimitedPhotosAccessMonitor() -> NSObjectProtocol {
        addUIInterruptionMonitor(withDescription: "Only the explicitly tested limited Photos grant") { alert in
            guard alert.label == "Allow “Celluloid” to access your photo library?" else { stopForUnexpectedSystemAlert() }
            let actions = alert.buttons.matching(NSPredicate(format: "label IN %@",
                ["Select Photos…", "Select Photos...", "Select Photos", "Allow Limited Access", "Limited Access"]))
            guard actions.count == 1, actions.element.isEnabled, actions.element.isHittable else { stopForUnexpectedSystemAlert() }
            print("EXPECTED_LIMITED_PHOTOS_AUTHORIZATION_ACTION " + actions.element.label)
            actions.element.tap()
            let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
            guard XCTWaiter.wait(for: [gone], timeout: 10) == .completed else { stopForUnexpectedSystemAlert() }
            return true
        }
    }
}

/// Shared by both suites. This branch performs no UI action or throwable XCTest
/// recording, so it cannot return false and delegate to the default auto-handler.
private func stopForUnexpectedSystemAlert() -> Never {
    print("CELLULOID_UNEXPECTED_SYSTEM_ALERT_FAIL_CLOSED_ABORT")
    fatalError("Celluloid UI test stopped before an unexpected system alert action")
}

// Release-only host acceptance harness. The preceding c587 UI suite and its
// fail-closed permission helpers are byte-for-byte unchanged.
import Photos
import CryptoKit
import ImageIO

final class CelluloidHostAcceptanceTests: XCTestCase {
    private let app = XCUIApplication()
    private let photos = XCUIApplication(bundleIdentifier: "com.apple.mobileslideshow")
    private let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    private var hostInterruption: NSObjectProtocol?
    private var fixtures: [CaptureFixtureIdentity] = []
    private var allowPreservationNotice = false
    private var preservationNoticeDismissed = false
    private var receiptNumber = 0
    private var selectedLabel = ""
    private var recordedFailure = false
    private let notificationTitle = "“Photos” Would Like to Send You Notifications"
    private let expectedResources = [
        "celluloid-fixture-a.png": "90ce9a3adb8b98b667d6cd9fcd4c092b748744c2b49b20c15ef7d50317d6686d",
        "celluloid-fixture-b.png": "8daf8dec2b9de9cb70bd74943369e7a4b948545117b773b9d0aff3f70a1d1c86"]

    override func setUp() {
        super.setUp(); continueAfterFailure = false
        // Never return false to XCTest's default permission-accepting handler.
        hostInterruption = addUIInterruptionMonitor(withDescription: "Only known Photos notification decline or scoped preservation notice; otherwise abort") { [unowned self] alert in
            if self.declineObservedNotification(alert) || self.dismissPreservationNotice(alert) { return true }
            self.haltForUnexpectedAlert("Unexpected interruption outside the exact permitted alert contexts")
        }
        XCUIDevice.shared.orientation = .portrait
    }
    override func record(_ issue: XCTIssue) {
        if !recordedFailure {
            recordedFailure = true
            print("PHOTOS_HOST_ACCEPTANCE_FAILURE " + String(issue.compactDescription.prefix(1500)))
            hierarchy("failure")
        }
        // No failure screenshot: the two evidence slots have fixed meanings.
        super.record(issue)
    }
    override func tearDown() {
        // Photos stays alive across cases; final workflow shutdown owns cleanup.
        app.terminate()
        if let monitor = hostInterruption { removeUIInterruptionMonitor(monitor) }
        hostInterruption = nil
        super.tearDown()
    }
    private func haltForUnexpectedAlert(_ reason: String) -> Never {
        print("PHOTOS_HOST_FAIL_CLOSED_ABORT " + String(reason.prefix(300)))
        fatalError("Photos-host test stopped before any unknown alert action")
    }
    private func declineObservedNotification(_ alert: XCUIElement) -> Bool {
        guard alert.exists && alert.label == notificationTitle else { return false }
        let deny = alert.buttons.matching(NSPredicate(format: "label IN %@", ["Don’t Allow", "Don't Allow"]))
        guard deny.count == 1, deny.element.isEnabled, deny.element.isHittable else { return false }
        print("PHOTOS_EXPECTED_NOTIFICATION_DECLINED label=\(alert.label)")
        deny.element.tap()
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
        return XCTWaiter.wait(for: [gone], timeout: 10) == .completed
    }
    private func dismissPreservationNotice(_ alert: XCUIElement) -> Bool {
        guard allowPreservationNotice, alert.exists else { return false }
        let messages = [
            "Earlier Edits Preserved": "Earlier edits could not be safely loaded. Editing is disabled to preserve the photo and its editing data.",
            "已保留之前的编辑": "无法安全读取之前的编辑内容。为保留照片和编辑数据，已停用编辑。"]
        guard let message = messages[alert.label], alert.staticTexts[message].exists else { return false }
        let done = alert.buttons.matching(NSPredicate(format: "label IN %@", ["Done", "完成"]))
        guard done.count == 1, done.element.isEnabled, done.element.isHittable else { return false }
        done.element.tap()
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
        guard XCTWaiter.wait(for: [gone], timeout: 10) == .completed else { return false }
        preservationNoticeDismissed = true
        print("PHOTOS_PROTECTED_NOTICE_DISMISSED exact_title_and_body=true scoped_phase=true")
        return true
    }
    @discardableResult private func promptFree() -> Bool {
        for alert in system.alerts.allElementsBoundByIndex + photos.alerts.allElementsBoundByIndex where alert.exists {
            if declineObservedNotification(alert) || dismissPreservationNotice(alert) { continue }
            haltForUnexpectedAlert("Unexpected alert before host interaction or pixel capture")
        }
        return true
    }
    private func requireSyntheticAuthorization() throws {
        #if targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        let candidate = environment["CELLULOID_PROBE_SOURCE_SHA"] ?? ""
        let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard UIDevice.current.userInterfaceIdiom == .phone,
              environment["CELLULOID_SYNTHETIC_PROBE"] == "1",
              candidate.count == 40, candidate.allSatisfy({ "0123456789abcdef".contains($0) }),
              environment["CELLULOID_SHIPPING_SOURCE_SHA"] == "c5875ee7586611c28879b5030e5e575a9f33fcbd",
              status == .authorized else {
            throw captureProbeError("Explicit marked Simulator/phone/full-Photos/exact-shipping prerequisites are absent")
        }
        print("PHOTOS_HOST_AUTHORIZATION_PREREQUISITE raw=\(status.rawValue) candidate=\(candidate) shipping=c5875ee7586611c28879b5030e5e575a9f33fcbd")
        #else
        throw captureProbeError("Synthetic host acceptance may not mutate a physical library")
        #endif
    }
    private func bindFixtures() throws {
        try requireSyntheticAuthorization()
        fixtures = try captureFixtureIdentities("host-case-baseline")
        guard Set(fixtures.map { $0.resourceFilename }) == Set(expectedResources.keys),
              fixtures.allSatisfy({ $0.originalFileSHA == expectedResources[$0.resourceFilename] &&
                  $0.originalImage.cgImage?.width == 640 && $0.originalImage.cgImage?.height == 480 }),
              fixtures[0].resourceFilename == "celluloid-fixture-b.png",
              fixtures[0].creationDate > fixtures[1].creationDate else {
            throw captureProbeError("Exactly two intended fixture hashes/dimensions/creation order are required")
        }
        print("PHOTOS_HOST_FIXTURES_BOUND exact_resources=true distinct_asset_identifiers=true creation_order=B_then_A")
    }
    private func fixture(_ name: String) throws -> CaptureFixtureIdentity {
        try XCTUnwrap(fixtures.first { $0.resourceFilename == "celluloid-fixture-\(name).png" })
    }
    private func freshOwnedAsset(_ baseline: CaptureFixtureIdentity) throws -> PHAsset {
        try requireSyntheticAuthorization()
        guard fixtures.contains(where: { $0.assetIdentifier == baseline.assetIdentifier && $0.originalFileSHA == baseline.originalFileSHA }) else {
            throw captureProbeError("Asset is not one of the exact bound synthetic resources")
        }
        return try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [baseline.assetIdentifier], options: nil).firstObject)
    }
    private func require(_ value: Bool, _ message: String) throws {
        guard value else { hierarchy(message); throw captureProbeError(message) }
    }
    private func launchHost() throws {
        promptFree()
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        try require(app.buttons["edit-photo"].waitForExistence(timeout: 15), "Shipping app registration did not reach its actual home")
        app.terminate()
        // The workflow performed the one initial zh-Hans launch. Ordinary entry
        // must preserve that process, including between the two cases.
        try require(photos.state == .runningForeground || photos.state == .runningBackground || photos.state == .runningBackgroundSuspended,
                    "The initial workflow-owned Photos process is no longer running")
        photos.activate()
        print("PHOTOS_HOST_PROCESS_ENTRY activated_existing=true")
        try showLibrary()
    }
    private func showLibrary() throws {
        promptFree()
        if photos.buttons["BackButton"].firstMatch.exists { try require(tapReady(photos.buttons["BackButton"].firstMatch), "One-up Back is not actionable") }
        _ = tapLabel(["图库", "Library", "所有照片", "All Photos"])
        let title = photos.staticTexts["“照片”新功能"].firstMatch
        let action = photos.buttons["继续"].firstMatch
        if action.waitForExistence(timeout: 10) {
            try require(title.exists, "Continue is outside the observed Photos What's New sheet")
            try require(tapReady(action), "Observed welcome Continue is not ready")
        }
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in !title.exists && !action.exists }, object: nil)
        try require(XCTWaiter.wait(for: [gone], timeout: 10) == .completed, "Observed welcome did not leave")
        let grid = photos.images.matching(identifier: "PXGGridLayout-Info")
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            grid.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.count >= 2
        }, object: nil)
        try require(XCTWaiter.wait(for: [ready], timeout: 10) == .completed, "Observed Photos grid not ready")
    }
    private func selectFixture(_ baseline: CaptureFixtureIdentity, verifyCurrentPixels: Bool = true) throws {
        _ = try freshOwnedAsset(baseline)
        let latest = Array(photos.images.matching(identifier: "PXGGridLayout-Info").allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.suffix(2))
        let ordered = fixtures.sorted { $0.creationDate < $1.creationDate }
        try require(latest.count == 2 && ordered.count == 2, "Exactly two latest visible fixture grid entries are required")
        for (image, source) in zip(latest, ordered) {
            let parts = Calendar.current.dateComponents([.month, .day], from: source.creationDate)
            let month = try XCTUnwrap(parts.month), day = try XCTUnwrap(parts.day)
            try require(image.label.range(of: "\\b\(month)月0?\(day)日", options: .regularExpression) != nil,
                        "Grid order/date does not match the exact owned fixtures")
        }
        let index = try XCTUnwrap(ordered.firstIndex { $0.assetIdentifier == baseline.assetIdentifier })
        let image = latest[index]; selectedLabel = image.label
        try captureJSON("PHOTOS_HOST_SELECTION_BINDING", ["asset_identifier": baseline.assetIdentifier,
            "resource_filename": baseline.resourceFilename, "creation_date": baseline.creationDate.timeIntervalSince1970,
            "ascending_fixture_slot": index, "observed_grid_label": selectedLabel])
        try require(tapReady(image), "Identified synthetic grid image is not actionable")
        try require(waitReady(photos.buttons["编辑"].firstMatch), "Selected fixture did not reach one-up Edit")
        if verifyCurrentPixels { try verifySelectedCurrent(baseline, phase: "before-edit-selection") }
    }
    private func verifySelectedCurrent(_ baseline: CaptureFixtureIdentity, phase: String) throws {
        _ = try integrity(baseline, phase: phase)
        let current = try currentImage(baseline)
        try require(try visiblePhotoMatches(current, label: selectedLabel, phase: phase), "One-up pixels do not identify the verified CURRENT owned rendering")
    }
    private func beginExtension(_ baseline: CaptureFixtureIdentity, protected: Bool) throws {
        try verifySelectedCurrent(baseline, phase: "before-enter-edit")
        try require(tapReady(photos.buttons["编辑"].firstMatch), "Actual Edit unavailable")
        try require(openExtensionsPicker("open"), "Observed More to Extensions route unavailable")
        allowPreservationNotice = protected; preservationNoticeDismissed = false
        try require(enterCelluloid("open"), "Observed Celluloid extension unavailable")
        if protected {
            let deadline = Date().addingTimeInterval(30)
            repeat {
                promptFree()
                if preservationNoticeDismissed && photos.staticTexts["read-only-adjustment"].exists { break }
                Thread.sleep(forTimeInterval: 0.25)
            } while Date() < deadline
            try require(preservationNoticeDismissed && photos.staticTexts["read-only-adjustment"].exists,
                        "Protected extension did not expose its exact notice and read-only state")
            try require(["tool-filter", "tool-bubble", "tool-sticker"].allSatisfy { !photos.buttons[$0].exists },
                        "Protected extension exposes an editing control")
        } else {
            try require(waitReady(photos.buttons["tool-filter"], timeout: 30), "Editable extension is not ready")
        }
        allowPreservationNotice = false
    }
    private func finishExtension(_ baseline: CaptureFixtureIdentity, protected: Bool, cancel: Bool) throws {
        try require(tapLabel(cancel ? ["取消", "Cancel"] : ["完成", "Done"]), "Observed extension completion action unavailable")
        let marker = protected ? photos.staticTexts["read-only-adjustment"] : photos.buttons["tool-filter"]
        let deadline = Date().addingTimeInterval(30)
        repeat {
            promptFree() // An unobserved discard confirmation is fatal, never accepted.
            if !marker.exists { return }
            Thread.sleep(forTimeInterval: 0.25)
        } while Date() < deadline
        throw captureProbeError("Extension surface did not leave after its actual action")
    }
    /// Does not turn an outer Cancel/back into a save claim. Every caller verifies
    /// exact final receipts after this observed normal exit.
    @discardableResult private func resolveOuterNoChange(_ phase: String) throws -> String {
        promptFree()
        if waitReady(photos.buttons["编辑"].firstMatch, timeout: 2) {
            print("PHOTOS_HOST_OUTER_EXIT phase=\(phase) route=already_one_up"); return "already_one_up"
        }
        try require(photos.navigationBars["PUPhotoEditView"].exists, "Unknown outer container after extension return")
        let route: String
        if tapLabel(["完成", "Done"]) { route = "outer_done" }
        else if tapLabel(["取消", "Cancel"]) { route = "outer_cancel" }
        else if tapReady(photos.buttons["BackButton"].firstMatch, timeout: 2) { route = "outer_back" }
        else { throw captureProbeError("No observed normal no-change exit in Photos") }
        try require(waitReady(photos.buttons["编辑"].firstMatch, timeout: 15), "Outer no-change exit did not resolve to one-up")
        print("PHOTOS_HOST_OUTER_EXIT phase=\(phase) route=\(route)")
        return route
    }
    private func saveEditableOuter() throws {
        try require(tapReady(photos.buttons["完成"].firstMatch), "Actual Photos Done unavailable for edited output")
        try require(waitReady(photos.buttons["编辑"].firstMatch, timeout: 15), "Photos save did not reach one-up")
    }
    private func retainScreenshot(_ frame: UIImage, slot: Int, name: String) throws {
        let jpeg = try XCTUnwrap(frame.jpegData(compressionQuality: 0.55))
        try persistHostEvidence(jpeg, name: name, slot: slot)
    }

    func testProtectedAdjustmentDoneCancelReopen() throws {
        try bindFixtures()
        let target = try fixture("a"), control = try fixture("b")
        let pristine = try integrity(target, phase: "protected-pristine")
        try require(pristine.adjustment == nil && pristine.currentPixels == pristine.originalPixels,
                    "Protected fixture must start pristine before explicit setup")
        let unchangedControl = try integrity(control, phase: "protected-control-before")
        let opaque = try installOverBudget(target)
        let baseline = try integrity(target, phase: "protected-installed")
        try require(baseline.original == pristine.original && baseline.originalPixels == pristine.originalPixels &&
                    baseline.currentPixels != pristine.currentPixels && baseline.adjustment == captureDigest(opaque) &&
                    baseline.identifier == "Mango.CelluloidPhotoExtension" && baseline.version == "1.0",
                    "Protected setup did not install exact opaque/current state while preserving original")
        try require(try integrity(control, phase: "protected-control-after-setup") == unchangedControl, "Setup changed the other owned fixture")
        try launchHost(); try selectFixture(target)
        try beginExtension(target, protected: true)
        promptFree()
        try retainScreenshot(XCUIScreen.main.screenshot().image, slot: 1, name: "celluloid-host-protected-read-only")
        try finishExtension(target, protected: true, cancel: false)
        try require(try integrity(target, phase: "protected-after-extension-done") == baseline, "Actual no-change Done altered protected bytes")
        try require(try integrity(control, phase: "protected-control-after-done") == unchangedControl, "Done changed other fixture")
        _ = try resolveOuterNoChange("protected-done")
        try require(try integrity(target, phase: "protected-after-outer-exit") == baseline, "Outer no-change exit altered protected bytes")
        // Both cancel/reopen cycles end at a resolved one-up screen, regardless of
        // test order. No Photos Revert is ever invoked for this protected asset.
        for cycle in 1...2 {
            try beginExtension(target, protected: true)
            try finishExtension(target, protected: true, cancel: true)
            _ = try resolveOuterNoChange("protected-cancel-\(cycle)")
            try require(try integrity(target, phase: "protected-cancel-reopen-\(cycle)") == baseline,
                        "Cancel/reopen changed protected original/current/opaque data")
            try require(try integrity(control, phase: "protected-control-final-\(cycle)") == unchangedControl,
                        "Cancel/reopen changed other owned fixture")
        }
        print("PHOTOS_HOST_PROTECTED_NO_CHANGE_PASS exact_owned_asset done_cancel_reopen final_safe_exit all_original_current_opaque_receipts_unchanged")
    }

    func testEditableSaveDisplayProcessStateAndRevert() throws {
        try bindFixtures()
        let target = try fixture("b"), control = try fixture("a")
        let baseline = try integrity(target, phase: "editable-pristine")
        let unchangedControl = try integrity(control, phase: "editable-control-before")
        try require(baseline.adjustment == nil && baseline.currentPixels == baseline.originalPixels, "Editable fixture must start pristine")
        try launchHost(); try selectFixture(target); try beginExtension(target, protected: false)
        try require(tapReady(photos.buttons["tool-filter"]), "Editable filter action unavailable")
        try require(tapReady(photos.collectionViews.cells.element(boundBy: 1)), "Observed Sepia preset unavailable")
        try finishExtension(target, protected: false, cancel: false); try saveEditableOuter()
        let sepia = try captureHostIntegrity(target, phase: "after-host-save")
        let saved = try integrity(target, phase: "editable-saved-sepia")
        try require(try integrity(control, phase: "editable-control-after-save") == unchangedControl, "Editable save changed other fixture")
        // Readiness uses geometry only. The first measured frame is immutable;
        // the exact same UIImage supplies slot2, even when its pixels are wrong.
        let immediate = try visiblePhotoMatches(sepia, label: selectedLabel, phase: "immediately-after-save", retainImmediate: true)
        try captureCurrentPhotoRepresentations(target, expected: sepia, phase: "after-extension-save")
        var libraryPerformed = false, restartPerformed = false
        var libraryMatches: Bool? = nil, restartMatches: Bool? = nil
        var finalMatches = immediate
        if !immediate {
            // Losing/ambiguously identifying the one-up image after a mismatch
            // is a prerequisite failure, never permission to navigate further.
            _ = try settledOneUpFrame(label: selectedLabel, aspect: 640.0 / 480.0, cropEditor: false)
            try showLibrary(); try selectFixture(target, verifyCurrentPixels: false)
            libraryPerformed = true
            try require(try integrity(target, phase: "after-library-reopen") == saved, "Ordinary reopen changed persisted resource identity")
            try require(try integrity(control, phase: "editable-control-after-library-reopen") == unchangedControl, "Library reopen changed control fixture")
            libraryMatches = try visiblePhotoMatches(sepia, label: selectedLabel, phase: "after-library-reopen")
            // Exactly one normal public-app lifecycle restart, no daemon or
            // permission change, reimport, resave, native filter or third image.
            photos.terminate()
            let stopped = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in self.photos.state == .notRunning }, object: nil)
            try require(XCTWaiter.wait(for: [stopped], timeout: 10) == .completed, "Normal Photos termination was not observed")
            photos.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
            photos.launch(); restartPerformed = true
            try showLibrary(); try selectFixture(target, verifyCurrentPixels: false)
            try require(try integrity(target, phase: "after-normal-process-relaunch") == saved, "Process relaunch changed persisted resource identity")
            try require(try integrity(control, phase: "editable-control-after-relaunch") == unchangedControl, "Relaunch changed control fixture")
            restartMatches = try visiblePhotoMatches(sepia, label: selectedLabel, phase: "after-normal-process-relaunch")
            finalMatches = restartMatches == true
        }
        try captureJSON("PHOTOS_HOST_SEPIA_DISPLAY_RESULT", ["asset_identifier": target.assetIdentifier,
            "immediate_display_matches": immediate, "library_reopen_performed": libraryPerformed,
            "library_reopen_display_matches": libraryMatches.map { $0 as Any } ?? NSNull(),
            "photos_process_relaunch_performed": restartPerformed,
            "relaunch_display_matches": restartMatches.map { $0 as Any } ?? NSNull(),
            "final_display_matches": finalMatches, "cold_view_has_exported_image": false])
        // A known immediate failure ends after its finite discriminator, even
        // when the cold view corrects. It never performs another Edit or Revert.
        try require(immediate, "Immediate saved Sepia preview failed; bounded discriminator finished with no further editing")
        try beginExtension(target, protected: false)
        try captureHostIntegrity(target, phase: "after-host-reopen")
        try require(tapReady(photos.buttons["tool-filter"]), "Reopened filter action unavailable")
        try require(tapReady(photos.collectionViews.cells.element(boundBy: 0)), "Observed Original preset unavailable")
        try finishExtension(target, protected: false, cancel: false); try saveEditableOuter()
        try captureHostRestoredOriginal(target)
        try require(try integrity(control, phase: "editable-control-after-original") == unchangedControl, "Original save changed other fixture")
        try verifySelectedCurrent(target, phase: "before-system-revert")
        try require(tapReady(photos.buttons["编辑"].firstMatch) &&
                    tapReady(photos.navigationBars["PUPhotoEditView"].buttons["复原"].firstMatch), "Actual Photos Revert unavailable")
        // This exact direct confirmation route was observed in prior host runs.
        // It is deliberately not an allowed interruption-monitor fallback.
        let confirmation = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            self.photos.sheets.firstMatch.exists || self.photos.alerts.firstMatch.exists
        }, object: nil)
        try require(XCTWaiter.wait(for: [confirmation], timeout: 10) == .completed, "Expected Photos Revert confirmation absent")
        let containers = photos.sheets.allElementsBoundByIndex + photos.alerts.allElementsBoundByIndex
        let actions = containers.flatMap { $0.buttons.allElementsBoundByIndex }.filter {
            ($0.label.contains("复原") || $0.label.lowercased().contains("revert")) && $0.isHittable
        }
        try require(actions.count == 1, "Actual Revert confirmation action is ambiguous")
        print("PHOTOS_HOST_SYSTEM_REVERT_CONFIRMATION label=\(actions[0].label)")
        actions[0].tap()
        let closed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !self.photos.sheets.firstMatch.exists && !self.photos.alerts.firstMatch.exists
        }, object: nil)
        try require(XCTWaiter.wait(for: [closed], timeout: 15) == .completed, "Revert confirmation did not close")
        try captureHostSystemRevertedOriginal(target)
        let nativeEditor = photos.navigationBars["PUPhotoEditView"].exists && photos.otherElements["cropView"].firstMatch.exists
        try require(try visiblePhotoMatches(target.originalImage, label: selectedLabel, phase: "after-system-revert", cropEditor: nativeEditor),
                    "Photos system-Reverted original is not visibly correct")
        _ = try resolveOuterNoChange("system-revert")
        try captureHostSystemRevertedOriginal(target)
        try require(try integrity(control, phase: "editable-control-final") == unchangedControl, "Host round trip changed other fixture")
        print("PHOTOS_HOST_EDITABLE_RESTORE_REVERT_PASS actual_editable_original system_revert immediate_display all_integrity_checks")
    }

    private struct HostResourceReceipt: Codable, Equatable {
        let type: Int
        let filename: String
        let sha256: String
    }
    private struct HostIntegrity: Codable, Equatable {
        let assetIdentifier: String
        let resources: [HostResourceReceipt]
        let originalPixels: String
        let currentPixels: String
        let original: String
        let current: String
        let adjustment: String?
        let identifier: String?
        let version: String?
    }
    private func hostInput(_ baseline: CaptureFixtureIdentity, handles: Bool) throws -> PHContentEditingInput {
        let asset = try freshOwnedAsset(baseline)
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = false; options.canHandleAdjustmentData = { _ in handles }
        let loaded = XCTestExpectation(description: "Read exact owned host input")
        var input: PHContentEditingInput?; var failure: Error?
        let request = asset.requestContentEditingInput(with: options) { value, info in
            input = value; failure = info[PHContentEditingInputErrorKey] as? Error; loaded.fulfill()
        }
        guard XCTWaiter.wait(for: [loaded], timeout: 15) == .completed else {
            asset.cancelContentEditingInputRequest(request); throw captureProbeError("Exact owned host input timed out")
        }
        if let failure = failure { throw failure }
        return try XCTUnwrap(input)
    }
    private func hostResourceBytes(_ resource: PHAssetResource) throws -> Data {
        let loaded = XCTestExpectation(description: "Read bound host resource bytes")
        let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
        var bytes = Data(); let lock = NSLock(); var failure: Error?
        let request = PHAssetResourceManager.default().requestData(for: resource, options: options, dataReceivedHandler: { chunk in
            lock.lock(); bytes.append(chunk); lock.unlock()
        }, completionHandler: { error in failure = error; loaded.fulfill() })
        guard XCTWaiter.wait(for: [loaded], timeout: 15) == .completed else {
            PHAssetResourceManager.default().cancelDataRequest(request); throw captureProbeError("Bound host resource read timed out")
        }
        if let failure = failure { throw failure }
        return bytes
    }
    private func currentImage(_ baseline: CaptureFixtureIdentity) throws -> UIImage {
        let input = try hostInput(baseline, handles: false)
        return try XCTUnwrap(UIImage(contentsOfFile: XCTUnwrap(input.fullSizeImageURL).path))
    }
    private func integrity(_ baseline: CaptureFixtureIdentity, phase: String) throws -> HostIntegrity {
        let asset = try freshOwnedAsset(baseline)
        var receipts: [HostResourceReceipt] = []
        var originals: [Data] = [], edited: [Data] = []
        for resource in PHAssetResource.assetResources(for: asset) {
            let bytes = try hostResourceBytes(resource)
            receipts.append(HostResourceReceipt(type: resource.type.rawValue, filename: resource.originalFilename, sha256: captureDigest(bytes)))
            if resource.type == .photo { originals.append(bytes) }
            if resource.type == .fullSizePhoto { edited.append(bytes) }
        }
        guard originals.count == 1, edited.count <= 1 else { throw captureProbeError("Ambiguous owned original/current resource set") }
        let original = try XCTUnwrap(originals.first), current = edited.first ?? original
        let originalImage = try XCTUnwrap(UIImage(data: original)), currentImage = try XCTUnwrap(UIImage(data: current))
        let handled = try hostInput(baseline, handles: true), flattened = try hostInput(baseline, handles: false)
        let inputBytes = try Data(contentsOf: XCTUnwrap(flattened.fullSizeImageURL))
        guard captureDigest(original) == baseline.originalFileSHA,
              captureDigest(try captureRGB(originalImage)) == baseline.originalPixelSHA,
              captureDigest(inputBytes) == captureDigest(current),
              currentImage.cgImage?.width == 640, currentImage.cgImage?.height == 480 else {
            throw captureProbeError("Fresh original/current URL/resource/dimension binding failed")
        }
        let receipt = HostIntegrity(assetIdentifier: asset.localIdentifier,
            resources: receipts.sorted { ($0.type, $0.filename, $0.sha256) < ($1.type, $1.filename, $1.sha256) },
            originalPixels: captureDigest(try captureRGB(originalImage)), currentPixels: captureDigest(try captureRGB(currentImage)),
            original: captureDigest(original), current: captureDigest(current), adjustment: handled.adjustmentData.map { captureDigest($0.data) },
            identifier: handled.adjustmentData?.formatIdentifier, version: handled.adjustmentData?.formatVersion)
        receiptNumber += 1
        let bytes = try JSONEncoder().encode(receipt)
        print("PHOTOS_HOST_RESOURCE_RECEIPT candidate=\(ProcessInfo.processInfo.environment["CELLULOID_PROBE_SOURCE_SHA"] ?? "UNSET") phase=\(phase) sequence=\(receiptNumber) " + String(decoding: bytes, as: UTF8.self))
        return receipt
    }
    private func installOverBudget(_ baseline: CaptureFixtureIdentity) throws -> Data {
        // Literal c587 legacy shape and reviewed1024-layer budget. Shared NSArray
        // references keep this well below the byte cap and test the count guard.
        let sticker: NSDictionary = ["imageName": "32", "center": NSValue(cgPoint: CGPoint(x: 100, y: 100)),
            "bounds": NSValue(cgRect: CGRect(x: 0, y: 0, width: 100, height: 100)),
            "transform": NSValue(cgAffineTransform: .identity)]
        let dictionary: NSDictionary = ["filterType": "Original", "stickers": NSArray(array: Array(repeating: sticker, count: 1025))]
        let opaque = try NSKeyedArchiver.archivedData(withRootObject: dictionary, requiringSecureCoding: true)
        guard opaque.count < 4 * 1024 * 1024 else { throw captureProbeError("Count-only opaque fixture unexpectedly exceeds byte budget") }
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.preferredRange = .standard
        let rendered = UIGraphicsImageRenderer(size: CGSize(width: 640, height: 480), format: format).image { context in
            UIColor.cyan.setFill(); context.fill(CGRect(x: 0, y: 0, width: 640, height: 480))
            UIColor.magenta.setFill(); context.fill(CGRect(x: 320, y: 0, width: 320, height: 480))
            UIColor.yellow.setFill(); context.fill(CGRect(x: 0, y: 240, width: 160, height: 240))
        }
        let jpeg = try XCTUnwrap(rendered.jpegData(compressionQuality: 1))
        let input = try hostInput(baseline, handles: true)
        guard input.adjustmentData == nil else { throw captureProbeError("Protected setup may only change its pristine owned asset") }
        let output = PHContentEditingOutput(contentEditingInput: input)
        output.adjustmentData = PHAdjustmentData(formatIdentifier: "Mango.CelluloidPhotoExtension", formatVersion: "1.0", data: opaque)
        try jpeg.write(to: output.renderedContentURL, options: .atomic)
        let asset = try freshOwnedAsset(baseline)
        try requireSyntheticAuthorization() // Throwing prerequisite immediately before the only synthetic mutation.
        let done = XCTestExpectation(description: "Install explicit protected synthetic adjustment")
        var success = false; var failure: Error?
        PHPhotoLibrary.shared().performChanges({ PHAssetChangeRequest(for: asset).contentEditingOutput = output }) { value, error in
            success = value; failure = error; done.fulfill()
        }
        guard XCTWaiter.wait(for: [done], timeout: 30) == .completed else { throw captureProbeError("Protected fixture setup timed out; no retry") }
        if let failure = failure { throw failure }
        guard success else { throw captureProbeError("Protected fixture setup rejected") }
        let receipt = try integrity(baseline, phase: "protected-setup-bound-resource")
        guard receipt.current == captureDigest(jpeg), receipt.currentPixels == captureDigest(try captureRGB(XCTUnwrap(UIImage(data: jpeg)))) else {
            throw captureProbeError("Actual current resource differs from the explicit rendered setup")
        }
        try captureJSON("PHOTOS_HOST_OPAQUE_SETUP", ["asset_identifier": baseline.assetIdentifier,
            "adjustment_sha256": captureDigest(opaque), "adjustment_bytes": opaque.count, "decorations": 1025,
            "rendered_sha256": captureDigest(jpeg), "pinned_shipping_decoration_limit": 1024])
        return opaque
    }
    private func hierarchy(_ stage: String) {
        print("PHOTOS_HOST_HIERARCHY_BEGIN:\(stage)")
        print(String(photos.debugDescription.prefix(24000)))
        print("PHOTOS_HOST_HIERARCHY_END:\(stage)")
    }
    private func tapLabel(_ labels: [String]) -> Bool {
        guard promptFree() else { return false }
        for label in labels {
            for control in photos.buttons.matching(NSPredicate(format: "label == %@", label)).allElementsBoundByIndex {
                if control.exists && control.isEnabled && control.isHittable { control.tap(); return true }
            }
        }
        return false
    }
    private func waitReady(_ control: XCUIElement, timeout: TimeInterval = 10) -> Bool {
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND enabled == true AND hittable == true"), object: control)
        guard XCTWaiter.wait(for: [ready], timeout: timeout) == .completed else {
            if control.exists {
                print("PHOTOS_HOST_CONTROL_NOT_READY label=\(control.label) exists=true enabled=\(control.isEnabled) hittable=\(control.isHittable) frame=\(control.frame)")
            } else { print("PHOTOS_HOST_CONTROL_NOT_READY exists=false") }
            return false
        }
        return true
    }
    private func tapReady(_ control: XCUIElement, timeout: TimeInterval = 10) -> Bool {
        guard promptFree(), waitReady(control, timeout: timeout) else { return false }
        control.tap()
        return true
    }
    /// A bounded, output-independent settling gate: exactly one identity-bound
    /// one-up element, correct raster aspect and two stable geometry snapshots.
    /// No source/output pixel values are read here. Missing/ambiguous identity
    /// throws immediately, including after an earlier observed mismatch.
    private func settledOneUpFrame(label: String, aspect: CGFloat, cropEditor: Bool) throws -> CGRect {
        let deadline = Date().addingTimeInterval(10)
        var previous: CGRect?
        repeat {
            promptFree()
            let images = cropEditor ? [photos.otherElements["cropView"].firstMatch] :
                photos.images.matching(NSPredicate(format: "label == %@", label)).allElementsBoundByIndex
            let candidates = images.filter {
                let frame = $0.frame
                return $0.exists && frame.width > photos.frame.width * 0.7 && frame.height > 100 && photos.frame.contains(frame)
            }
            guard candidates.count == 1 else { throw captureProbeError("One-up image identity is missing or ambiguous; no further diagnostic navigation") }
            let frame = candidates[0].frame
            guard abs(frame.width / frame.height - aspect) < 0.01 else { throw captureProbeError("Observed one-up image is not the unzoomed bound raster") }
            if previous == frame { return frame }
            previous = frame
            Thread.sleep(forTimeInterval: 0.25)
        } while Date() < deadline
        throw captureProbeError("One-up geometry did not settle independently of expected pixels")
    }
    private func visiblePhotoMatches(_ expected: UIImage, label: String, phase: String,
                                     cropEditor: Bool = false, retainImmediate: Bool = false) throws -> Bool {
        let source = try XCTUnwrap(expected.cgImage)
        let frame = try settledOneUpFrame(label: label, aspect: CGFloat(source.width) / CGFloat(source.height), cropEditor: cropEditor)
        promptFree()
        let screen = XCUIScreen.main.screenshot().image
        let raster = try XCTUnwrap(screen.cgImage)
        let scaleX = CGFloat(raster.width) / photos.frame.width, scaleY = CGFloat(raster.height) / photos.frame.height
        var samples: [[String: Any]] = []
        var maximum = 0
        for y in [CGFloat(0.25), 0.5, 0.75] {
            for x in [CGFloat(0.25), 0.5, 0.75] {
                let target = try capturePixel(expected, x: Int(CGFloat(source.width) * x), y: Int(CGFloat(source.height) * y))
                let actual = try capturePixel(screen, x: Int((frame.minX + frame.width * x) * scaleX), y: Int((frame.minY + frame.height * y) * scaleY))
                let delta = zip(target, actual).map { abs($0 - $1) }.max() ?? 255
                maximum = max(maximum, delta)
                samples.append(["x": x, "y": y, "expected_rgb": target, "screen_rgb": actual, "maximum_delta": delta])
            }
        }
        try captureJSON("PHOTOS_HOST_VISIBLE_PIXEL_PROBE", ["phase": phase, "observation": 1,
            "frame": [frame.minX, frame.minY, frame.width, frame.height], "samples": samples,
            "maximum_delta": maximum, "display_tolerance": 12, "pixel_retry_count": 0,
            "native_frame_pixel_sha256": captureDigest(try captureRGB(screen))])
        if retainImmediate { try retainScreenshot(screen, slot: 2, name: "celluloid-host-immediate-editable-save") }
        return maximum <= 12
    }
    private func openExtensionsPicker(_ stage: String) -> Bool {
        guard tapReady(photos.buttons["edit.moreButton"].firstMatch) else {
            hierarchy(stage + "-more-unavailable"); return false
        }
        // This exact submenu button was observed in the previous actual Photos hierarchy.
        guard tapReady(photos.buttons["扩展"].firstMatch) else {
            hierarchy(stage + "-submenu-unavailable"); return false
        }
        return true
    }
    private func enterCelluloid(_ stage: String) -> Bool {
        let query = photos.descendants(matching: .any).matching(NSPredicate(format: "label == %@ OR label == %@", "CelluloidPhotoExtension", "Celluloid"))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            query.allElementsBoundByIndex.contains { $0.exists && $0.isHittable }
        }, object: nil)
        guard XCTWaiter.wait(for: [ready], timeout: 10) == .completed,
              let entry = query.allElementsBoundByIndex.first(where: { $0.exists && $0.isHittable }) else {
            hierarchy(stage + "-entry-unavailable"); return false
        }
        hierarchy(stage + "-extension-picker")
        entry.tap()
        return true
    }
}

private func captureCurrentPhotoRepresentations(_ baseline: CaptureFixtureIdentity, expected: UIImage, phase: String) throws {
    let asset = try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [baseline.assetIdentifier], options: nil).firstObject)
    let options = PHImageRequestOptions()
    options.version = .current; options.deliveryMode = .highQualityFormat
    options.resizeMode = .exact; options.isSynchronous = true; options.isNetworkAccessAllowed = false
    var derivative: UIImage?
    var readError: Error?
    PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 640, height: 480), contentMode: .aspectFit, options: options) { image, info in
        derivative = image; readError = info?[PHImageErrorKey] as? Error
    }
    if let error = readError { throw error }
    let preview = try XCTUnwrap(derivative)
    let expectedCG = try XCTUnwrap(expected.cgImage), previewCG = try XCTUnwrap(preview.cgImage)
    var samples: [[String: Any]] = []
    for y in [CGFloat(0.25), 0.5, 0.75] {
        for x in [CGFloat(0.25), 0.5, 0.75] {
            let desired = try capturePixel(expected, x: Int(CGFloat(expectedCG.width) * x), y: Int(CGFloat(expectedCG.height) * y))
            let current = try capturePixel(preview, x: Int(CGFloat(previewCG.width) * x), y: Int(CGFloat(previewCG.height) * y))
            samples.append(["x": x, "y": y, "current_full_rgb": desired, "current_derivative_rgb": current,
                "maximum_delta": zip(desired, current).map { abs($0 - $1) }.max() ?? 255])
        }
    }
    try captureJSON("PHOTOS_CURRENT_DERIVATIVE", ["phase": phase, "asset_identifier": baseline.assetIdentifier,
        "width": previewCG.width, "height": previewCG.height, "pixel_sha256": captureDigest(try captureRGB(preview)), "samples": samples])
    let inputOptions = PHContentEditingInputRequestOptions()
    inputOptions.isNetworkAccessAllowed = false; inputOptions.canHandleAdjustmentData = { _ in false }
    let loaded = XCTestExpectation(description: "Read actual current rendered resource URL")
    var input: PHContentEditingInput?
    let request = asset.requestContentEditingInput(with: inputOptions) { value, _ in input = value; loaded.fulfill() }
    guard XCTWaiter.wait(for: [loaded], timeout: 15) == .completed else {
        asset.cancelContentEditingInputRequest(request); throw captureProbeError("Current rendered resource input timed out")
    }
    let currentInput = try XCTUnwrap(input), url = try XCTUnwrap(currentInput.fullSizeImageURL)
    let bytes = try Data(contentsOf: url), image = try XCTUnwrap(UIImage(data: bytes))
    try captureJSON("PHOTOS_CURRENT_RESOURCE_CONTRACT", ["phase": phase, "asset_identifier": baseline.assetIdentifier,
        "url_last_component": url.lastPathComponent, "url_extension": url.pathExtension,
        "resource_sha256": captureDigest(bytes), "pixel_sha256": captureDigest(try captureRGB(image)),
        "input_orientation": currentInput.fullSizeImageOrientation, "image_metadata": try captureImageMetadata(bytes, image: image)])
}

private func hostEvidenceDirectory() -> URL {
    FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("CelluloidSyntheticHostEvidence", isDirectory: true)
}
private func persistHostEvidence(_ jpeg: Data, name: String, slot: Int) throws {
    let allowed = [1: "celluloid-host-protected-read-only", 2: "celluloid-host-immediate-editable-save"]
    guard allowed[slot] == name, jpeg.count <= 500_000 else { throw captureProbeError("Unexpected host slot/name or byte count") }
    let directory = hostEvidenceDirectory()
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let destination = directory.appendingPathComponent("host-evidence-\(slot).jpg")
    let metadataURL = directory.appendingPathComponent("host-evidence-\(slot).json")
    guard !FileManager.default.fileExists(atPath: destination.path), !FileManager.default.fileExists(atPath: metadataURL.path) else {
        throw captureProbeError("A fixed evidence slot may only be written once; no old frame may be replaced")
    }
    let pixels = try XCTUnwrap(UIImage(data: jpeg)?.cgImage)
    let metadata: [String: Any] = ["slot": slot, "name": name, "bytes": jpeg.count,
        "width": pixels.width, "height": pixels.height, "sha256": captureDigest(jpeg),
        "scope": "ephemeral_test_runner_cache_only", "source": "native_XCUIScreen_JPEG_no_resize"]
    try jpeg.write(to: destination, options: .withoutOverwriting)
    try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: metadataURL, options: .withoutOverwriting)
    try captureJSON("PHOTOS_HOST_LOCAL_EVIDENCE", metadata)
}
private func captureImageMetadata(_ data: Data, image: UIImage) throws -> [String: Any] {
    let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
    let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
    let cg = try XCTUnwrap(image.cgImage)
    return ["imageio_type": CGImageSourceGetType(source).map { $0 as String } ?? "unknown",
        "width": cg.width, "height": cg.height, "bits_per_component": cg.bitsPerComponent,
        "bits_per_pixel": cg.bitsPerPixel, "row_bytes": cg.bytesPerRow,
        "color_space": cg.colorSpace?.name.map { $0 as String } ?? "unknown",
        "alpha_info": cg.alphaInfo.rawValue, "image_orientation": image.imageOrientation.rawValue,
        "metadata_orientation": properties[kCGImagePropertyOrientation] ?? "absent",
        "metadata_depth": properties[kCGImagePropertyDepth] ?? "absent",
        "metadata_profile": properties[kCGImagePropertyProfileName] ?? "absent"]
}

private struct CaptureFixtureIdentity {
    let pickerIndex: Int
    let assetIdentifier: String
    let resourceFilename: String
    let creationDate: Date
    let originalFileSHA: String
    let originalPixelSHA: String
    let currentFileSHA: String
    let currentPixelSHA: String
    let originalImage: UIImage
    let currentImage: UIImage
}

private func captureDigest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
private func captureProbeError(_ text: String) -> NSError {
    NSError(domain: "CelluloidCaptureProbe", code: 1, userInfo: [NSLocalizedDescriptionKey: text])
}
private func captureJSON(_ marker: String, _ object: [String: Any]) throws {
    print(marker + " " + String(decoding: try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]), as: UTF8.self))
}
private func captureRGB(_ image: UIImage) throws -> Data {
    let cg = try XCTUnwrap(image.cgImage)
    var rgba = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
    let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
    let drawn = rgba.withUnsafeMutableBytes { bytes -> Bool in
        guard let context = CGContext(data: bytes.baseAddress, width: cg.width, height: cg.height,
            bitsPerComponent: 8, bytesPerRow: cg.width * 4, space: space,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { return false }
        context.draw(cg, in: CGRect(x: 0, y: 0, width: CGFloat(cg.width), height: CGFloat(cg.height)))
        return true
    }
    guard drawn else { throw captureProbeError("Cannot decode synthetic image pixels") }
    var rgb = Data(capacity: cg.width * cg.height * 3)
    for offset in stride(from: 0, to: rgba.count, by: 4) { rgb.append(contentsOf: rgba[offset..<(offset + 3)]) }
    return rgb
}
private func capturePixel(_ image: UIImage, x: Int, y: Int) throws -> [Int] {
    let cg = try XCTUnwrap(image.cgImage)
    // Pixel inspection only; all exported screenshots remain full native frames, unmodified.
    let one = try XCTUnwrap(cg.cropping(to: CGRect(x: CGFloat(x), y: CGFloat(y), width: 1, height: 1)))
    return Array(try captureRGB(UIImage(cgImage: one))).prefix(3).map(Int.init)
}
private func captureFixtureIdentities(_ phase: String) throws -> [CaptureFixtureIdentity] {
    let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    guard status == .authorized else { throw captureProbeError("UI-test runner Photos authorization is \(status.rawValue), expected authorized") }
    let options = PHFetchOptions()
    options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
    let assets = PHAsset.fetchAssets(with: .image, options: options)
    var records: [CaptureFixtureIdentity] = []
    for index in 0..<min(assets.count, 32) {
        let asset = assets.object(at: index)
        let resources = PHAssetResource.assetResources(for: asset)
        guard let resource = resources.first(where: { $0.type == .photo && ["celluloid-fixture-a.png", "celluloid-fixture-b.png"].contains($0.originalFilename) }) else { continue }
        var original = Data()
        var readError: Error?
        let lock = NSLock()
        let done = XCTestExpectation(description: "Read synthetic original resource")
        let resourceOptions = PHAssetResourceRequestOptions()
        resourceOptions.isNetworkAccessAllowed = false
        PHAssetResourceManager.default().requestData(for: resource, options: resourceOptions, dataReceivedHandler: { chunk in
            lock.lock(); original.append(chunk); lock.unlock()
        }, completionHandler: { error in readError = error; done.fulfill() })
        guard XCTWaiter.wait(for: [done], timeout: 15) == .completed else { throw captureProbeError("Synthetic resource read timed out") }
        if let error = readError { throw error }
        var current: Data?
        var currentError: Error?
        let imageOptions = PHImageRequestOptions()
        imageOptions.isSynchronous = true
        imageOptions.isNetworkAccessAllowed = false
        imageOptions.version = .current
        imageOptions.deliveryMode = .highQualityFormat
        PHImageManager.default().requestImageDataAndOrientation(for: asset, options: imageOptions) { bytes, _, _, info in
            current = bytes; currentError = info?[PHImageErrorKey] as? Error
        }
        if let error = currentError { throw error }
        let currentBytes = try XCTUnwrap(current)
        let originalImage = try XCTUnwrap(UIImage(data: original))
        let currentImage = try XCTUnwrap(UIImage(data: currentBytes))
        guard originalImage.imageOrientation == .up && currentImage.imageOrientation == .up else { throw captureProbeError("Synthetic fixture orientation changed unexpectedly") }
        let creationDate = try XCTUnwrap(asset.creationDate)
        let row = CaptureFixtureIdentity(pickerIndex: index, assetIdentifier: asset.localIdentifier,
            resourceFilename: resource.originalFilename, creationDate: creationDate,
            originalFileSHA: captureDigest(original), originalPixelSHA: captureDigest(try captureRGB(originalImage)),
            currentFileSHA: captureDigest(currentBytes), currentPixelSHA: captureDigest(try captureRGB(currentImage)),
            originalImage: originalImage, currentImage: currentImage)
        records.append(row)
        try captureJSON("CAPTURE_SYNTHETIC_ASSET", ["phase": phase, "picker_identifier": "photo-\(index)",
            "asset_identifier": row.assetIdentifier, "resource_filename": row.resourceFilename,
            "creation_date": row.creationDate.timeIntervalSince1970,
            "original_resource_sha256": row.originalFileSHA, "original_pixel_sha256": row.originalPixelSHA,
            "current_resource_sha256": row.currentFileSHA, "current_pixel_sha256": row.currentPixelSHA,
            "original_width": originalImage.cgImage!.width, "original_height": originalImage.cgImage!.height,
            "current_width": currentImage.cgImage!.width, "current_height": currentImage.cgImage!.height,
            "pixel_method": "CGContext sRGB RGBA8 big-endian then alpha stripped",
            "original_metadata": try captureImageMetadata(original, image: originalImage),
            "current_metadata": try captureImageMetadata(currentBytes, image: currentImage),
            "asset_resources": resources.map { ["type": $0.type.rawValue, "filename": $0.originalFilename, "uniform_type_identifier": $0.uniformTypeIdentifier] as [String: Any] }])
    }
    guard records.count == 2, Set(records.map { $0.assetIdentifier }).count == 2,
          Set(records.map { $0.originalPixelSHA }).count == 2,
          records[0].creationDate != records[1].creationDate else {
        throw captureProbeError("Expected exactly two distinct synthetic assets with unique creation times; no duplicate reseeding")
    }
    return records
}
@discardableResult
private func captureHostIntegrity(_ baseline: CaptureFixtureIdentity, phase: String) throws -> UIImage {
    let asset = try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [baseline.assetIdentifier], options: nil).firstObject)
    let options = PHContentEditingInputRequestOptions()
    options.isNetworkAccessAllowed = false
    options.canHandleAdjustmentData = { _ in true }
    var result: PHContentEditingInput?
    var readError: Error?
    let done = XCTestExpectation(description: "Read persisted actual Photos-host adjustment")
    let request = asset.requestContentEditingInput(with: options) { input, info in
        result = input; readError = info[PHContentEditingInputErrorKey] as? Error; done.fulfill()
    }
    guard XCTWaiter.wait(for: [done], timeout: 15) == .completed else {
        asset.cancelContentEditingInputRequest(request)
        throw captureProbeError("Persisted host adjustment read timed out")
    }
    if let error = readError { throw error }
    let input = try XCTUnwrap(result)
    let adjustment = try XCTUnwrap(input.adjustmentData)
    let classes: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
    let archive = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: classes, from: adjustment.data) as? [String: Any])
    guard adjustment.formatIdentifier == "Mango.CelluloidPhotoExtension", adjustment.formatVersion == "1.0",
          archive["filterType"] as? String == "Sepia" else {
        throw captureProbeError("Actual Photos-host persisted adjustment does not match Celluloid 1.0 Sepia")
    }
    let after = try XCTUnwrap(captureFixtureIdentities(phase).first { $0.assetIdentifier == baseline.assetIdentifier })
    guard after.originalFileSHA == baseline.originalFileSHA,
          after.originalPixelSHA == baseline.originalPixelSHA,
          after.currentPixelSHA != baseline.currentPixelSHA else {
        throw captureProbeError("Host edit must preserve original bytes/pixels and change current rendered pixels")
    }
    let cg = try XCTUnwrap(after.currentImage.cgImage)
    let sample = try capturePixel(after.currentImage, x: cg.width / 4, y: cg.height * 3 / 4)
    guard sample[0] > sample[1] + 3 && sample[1] > sample[2] + 3 else {
        throw captureProbeError("Persisted current output does not have the expected sepia channel ordering")
    }
    try captureJSON("PHOTOS_HOST_INTEGRITY_PASS", ["phase": phase, "asset_identifier": after.assetIdentifier,
        "format_identifier": adjustment.formatIdentifier, "format_version": adjustment.formatVersion,
        "filter_type": archive["filterType"] as! String,
        "adjustment_sha256": captureDigest(adjustment.data), "original_resource_sha256": after.originalFileSHA,
        "before_current_pixel_sha256": baseline.currentPixelSHA, "after_current_pixel_sha256": after.currentPixelSHA,
        "sepia_sample_rgb": sample])
    return after.currentImage
}


private func captureHostRestoredOriginal(_ baseline: CaptureFixtureIdentity) throws {
    let asset = try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [baseline.assetIdentifier], options: nil).firstObject)
    let options = PHContentEditingInputRequestOptions()
    options.isNetworkAccessAllowed = false
    options.canHandleAdjustmentData = { _ in true }
    var result: PHContentEditingInput?
    let done = XCTestExpectation(description: "Read restored Original adjustment")
    let request = asset.requestContentEditingInput(with: options) { input, _ in result = input; done.fulfill() }
    guard XCTWaiter.wait(for: [done], timeout: 15) == .completed else {
        asset.cancelContentEditingInputRequest(request)
        throw captureProbeError("Restored Original adjustment timed out")
    }
    let adjustment = try XCTUnwrap(result?.adjustmentData)
    let classes: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
    let archive = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: classes, from: adjustment.data) as? [String: Any])
    guard adjustment.formatIdentifier == "Mango.CelluloidPhotoExtension", adjustment.formatVersion == "1.0",
          archive["filterType"] as? String == "Original" else {
        throw captureProbeError("Reopened editor did not persist Celluloid1.0 Original state")
    }
    let after = try XCTUnwrap(captureFixtureIdentities("after-original-restored").first { $0.assetIdentifier == baseline.assetIdentifier })
    guard after.originalFileSHA == baseline.originalFileSHA, after.originalPixelSHA == baseline.originalPixelSHA,
          after.originalImage.cgImage?.width == after.currentImage.cgImage?.width,
          after.originalImage.cgImage?.height == after.currentImage.cgImage?.height else {
        throw captureProbeError("Original resource or restored raster dimensions changed")
    }
    let original = try captureRGB(after.originalImage)
    let restored = try captureRGB(after.currentImage)
    guard original.count == restored.count, !original.isEmpty else { throw captureProbeError("Restored pixel buffers mismatch") }
    var maximum = 0, total: UInt64 = 0, overThree = 0
    for (a, b) in zip(original, restored) {
        let delta = abs(Int(a) - Int(b))
        maximum = max(maximum, delta); total += UInt64(delta)
        if delta > 3 { overThree += 1 }
    }
    let mean = Double(total) / Double(original.count)
    let fractionOverThree = Double(overThree) / Double(original.count)
    try captureJSON("PHOTOS_HOST_ORIGINAL_PIXEL_COMPARISON", ["asset_identifier": baseline.assetIdentifier,
        "channels": original.count, "maximum_channel_delta": maximum, "mean_absolute_delta": mean,
        "fraction_over_three": fractionOverThree, "max_allowed": 8, "mean_allowed": 1.5,
        "fraction_over_three_allowed": 0.01, "original_pixel_sha256": after.originalPixelSHA,
        "restored_pixel_sha256": after.currentPixelSHA, "adjustment_sha256": captureDigest(adjustment.data)])
    guard maximum <= 8, mean <= 1.5, fractionOverThree <= 0.01 else {
        throw captureProbeError("Reopened editor did not restore original pixels within narrow full-image JPEG tolerance")
    }
    print("PHOTOS_HOST_ORIGINAL_RESTORATION_PASS exact_asset original_resource_unchanged full_raster_pixels_verified")
}


private func captureHostSystemRevertedOriginal(_ baseline: CaptureFixtureIdentity) throws {
    let asset = try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [baseline.assetIdentifier], options: nil).firstObject)
    let options = PHContentEditingInputRequestOptions()
    options.isNetworkAccessAllowed = false
    options.canHandleAdjustmentData = { _ in true }
    let done = XCTestExpectation(description: "Read actual system-Reverted Photos asset")
    var input: PHContentEditingInput?
    let request = asset.requestContentEditingInput(with: options) { value, _ in input = value; done.fulfill() }
    guard XCTWaiter.wait(for: [done], timeout: 15) == .completed else {
        asset.cancelContentEditingInputRequest(request)
        throw captureProbeError("Photos system-Revert input timed out")
    }
    let restored = try XCTUnwrap(input)
    guard restored.adjustmentData == nil else { throw captureProbeError("Photos system Revert did not clear the actual adjustment data") }
    let after = try XCTUnwrap(captureFixtureIdentities("after-system-revert").first { $0.assetIdentifier == baseline.assetIdentifier })
    guard after.originalFileSHA == baseline.originalFileSHA, after.originalPixelSHA == baseline.originalPixelSHA,
          after.currentPixelSHA == baseline.originalPixelSHA else {
        throw captureProbeError("Photos system Revert did not restore the exact original pixels/resource")
    }
    try captureJSON("PHOTOS_HOST_SYSTEM_REVERT_PASS", ["asset_identifier": baseline.assetIdentifier,
        "adjustment_data_is_nil": true, "original_resource_sha256": after.originalFileSHA,
        "original_pixel_sha256": after.originalPixelSHA, "current_pixel_sha256": after.currentPixelSHA])
}
