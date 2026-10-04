import XCTest
import UIKit
import Photos
import CryptoKit
import ImageIO

final class CelluloidUITests: XCTestCase {
    private var app: XCUIApplication!
    private var recordedFailure = false
    private var photosAccessMonitor: NSObjectProtocol?
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
    override func setUp() { super.setUp(); continueAfterFailure = false; recordedFailure = false; app = XCUIApplication() }
    override func tearDown() {
        if let monitor = photosAccessMonitor { removeUIInterruptionMonitor(monitor); photosAccessMonitor = nil }
        XCUIDevice.shared.orientation = .portrait; app.terminate(); super.tearDown()
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
            guard alert.label == "Allow “Celluloid” to access your photo library?" else { return false }
            print("EXPECTED_PHOTOS_AUTHORIZATION_ALERT " + String(alert.debugDescription.prefix(6000)))
            let actions = alert.buttons.matching(NSPredicate(format: "label IN %@",
                ["Allow Full Access", "Allow Access to All Photos"]))
            guard actions.count == 1, actions.element.isHittable else { return false }
            print("EXPECTED_PHOTOS_AUTHORIZATION_ACTION " + actions.element.label)
            actions.element.tap()
            return true
        }
    }
}

final class CelluloidCaptureTests: XCTestCase {
    private var app = XCUIApplication()
    private var capturedFailure = false
    private var hostInterruption: NSObjectProtocol?
    override func record(_ issue: XCTIssue) {
        if !capturedFailure {
            capturedFailure = true
            if let jpeg = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.55), jpeg.count <= 500_000 {
                let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
                let directory = hostEvidenceDirectory()
                let retained = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
                if retained.filter({ $0.pathExtension == "jpg" }).count < 2 {
                    try? persistHostEvidence(jpeg, name: "celluloid-capture-failure")
                    attachment.name = "celluloid-capture-failure"
                    attachment.lifetime = .keepAlways
                    add(attachment)
                }
            }
        }
        super.record(issue)
    }
    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
    }
    override func tearDown() {
        app.terminate()
        if let monitor = hostInterruption { removeUIInterruptionMonitor(monitor) }
        hostInterruption = nil
        super.tearDown()
    }

    private func launchChinese() {
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 15))
    }
    private func ready(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        let predicate = NSPredicate(format: "enabled == true AND hittable == true")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: element)], timeout: 15), .completed)
    }
    func testStoreScreenshots() throws {
        launchChinese()
        for (identifier, label) in [("edit-photo", "美化"), ("make-collage", "拼图"), ("privacy-policy", "隐私政策")] {
            XCTAssertEqual(app.buttons[identifier].label, label)
            XCTAssertTrue(app.buttons[identifier].isHittable)
        }
        let editFrame = app.buttons["edit-photo"].frame
        let collageFrame = app.buttons["make-collage"].frame
        let footerFrame = app.buttons["privacy-policy"].frame
        XCTAssertGreaterThanOrEqual(editFrame.height, 120)
        XCTAssertGreaterThanOrEqual(collageFrame.height, 120)
        XCTAssertFalse(editFrame.intersects(collageFrame), "Primary home choices must not overlap")
        XCTAssertGreaterThanOrEqual(footerFrame.minY + 1, max(editFrame.maxY, collageFrame.maxY))
        XCTAssertLessThan(footerFrame.height, app.frame.height * 0.40)
        XCTAssertTrue(app.frame.contains(editFrame) && app.frame.contains(collageFrame) && app.frame.contains(footerFrame))
        print("STORE_HOME_GEOMETRY edit=\(editFrame) collage=\(collageFrame) footer=\(footerFrame)")
        try emitStoreScreenshot("01-home")
        let editSources = try captureFixtureIdentities("before-editor")
        let editSource = editSources[0]
        try logSelection(editSource, phase: "editor")
        app.buttons["edit-photo"].tap()
        let photo = app.descendants(matching: .any)["photo-\(editSource.pickerIndex)"]
        ready(photo); photo.tap()
        app.buttons["picker-done"].tap()
        let editDone = app.buttons["editor-done"]
        ready(editDone)
        app.buttons["tool-filter"].tap()
        ready(app.collectionViews.cells.element(boundBy: 1))
        app.collectionViews.cells.element(boundBy: 1).tap()
        if app.buttons["取消"].exists && !editDone.isHittable { app.buttons["取消"].tap() }
        app.buttons["tool-sticker"].tap()
        ready(app.collectionViews.cells.firstMatch)
        app.collectionViews.cells.firstMatch.tap()
        ready(editDone)
        XCTAssertTrue(app.buttons["tool-filter"].isHittable)
        XCTAssertTrue(app.buttons["tool-sticker"].isHittable)
        try emitStoreScreenshot("02-edited-fixture")
        app.buttons["取消"].tap()
        ready(app.buttons["make-collage"])

        let collageSources = try captureFixtureIdentities("before-collage")
        guard collageSources[0].currentPixelSHA != collageSources[1].currentPixelSHA else {
            throw captureProbeError("Selected collage sources have identical current pixels")
        }
        let secondRead = try captureFixtureIdentities("selection-stability")
        for source in collageSources {
            guard let same = secondRead.first(where: { $0.pickerIndex == source.pickerIndex }),
                  same.assetIdentifier == source.assetIdentifier && same.currentPixelSHA == source.currentPixelSHA else {
                throw captureProbeError("Photo-N source identity changed before UI selection")
            }
            try logSelection(source, phase: "collage")
        }
        app.buttons["make-collage"].tap()
        for source in collageSources {
            let cell = app.descendants(matching: .any)["photo-\(source.pickerIndex)"]
            ready(cell); cell.tap()
        }
        app.buttons["picker-done"].tap()
        ready(app.buttons["collage-done"])
        XCTAssertTrue(app.scrollViews["collage-image"].firstMatch.waitForExistence(timeout: 5))
        try verifyCollagePixels(collageSources)
        try emitStoreScreenshot("03-collage")
    }

    private func logSelection(_ source: CaptureFixtureIdentity, phase: String) throws {
        try captureJSON("CAPTURE_SELECTED_ASSET", ["phase": phase, "picker_identifier": "photo-\(source.pickerIndex)",
            "asset_identifier": source.assetIdentifier, "resource_filename": source.resourceFilename,
            "original_pixel_sha256": source.originalPixelSHA, "current_pixel_sha256": source.currentPixelSHA])
    }
    private func verifyCollagePixels(_ sources: [CaptureFixtureIdentity]) throws {
        let cells = app.scrollViews.matching(identifier: "collage-image").allElementsBoundByIndex
        guard cells.count == sources.count && cells.count == 2 else { throw captureProbeError("Expected exactly two corresponding collage cells") }
        Thread.sleep(forTimeInterval: 1)
        let screen = XCUIScreen.main.screenshot().image
        let screenCG = try XCTUnwrap(screen.cgImage)
        let scaleX = CGFloat(screenCG.width) / app.frame.width
        let scaleY = CGFloat(screenCG.height) / app.frame.height
        var expectedSamples: [[Int]] = []
        for (index, source) in sources.enumerated() {
            let frame = cells[index].frame
            guard app.frame.contains(frame), frame.width > 0, frame.height > 0 else { throw captureProbeError("Collage cell is clipped or empty") }
            let sourceCG = try XCTUnwrap(source.currentImage.cgImage)
            let factor = max(frame.width / CGFloat(sourceCG.width), frame.height / CGFloat(sourceCG.height))
            // The default layout/zoom uses aspect-fill at zero contentOffset. This sample avoids both borders and the overlapping inset.
            let expected = try capturePixel(source.currentImage, x: Int(frame.width * 0.25 / factor), y: Int(frame.height * 0.75 / factor))
            let observed = try capturePixel(screen, x: Int((frame.minX + frame.width * 0.25) * scaleX), y: Int((frame.minY + frame.height * 0.75) * scaleY))
            let delta = zip(expected, observed).map { abs($0 - $1) }.max() ?? 255
            try captureJSON("CAPTURE_COLLAGE_CELL", ["cell_index": index, "asset_identifier": source.assetIdentifier,
                "picker_identifier": "photo-\(source.pickerIndex)", "current_pixel_sha256": source.currentPixelSHA,
                "frame": [frame.minX, frame.minY, frame.width, frame.height], "expected_rgb": expected,
                "observed_rgb": observed, "maximum_channel_delta": delta, "tolerance": 32])
            guard delta <= 32 else { throw captureProbeError("Collage cell pixels do not correspond to their selected current source") }
            expectedSamples.append(expected)
        }
        guard zip(expectedSamples[0], expectedSamples[1]).map({ abs($0 - $1) }).max()! > 40 else {
            throw captureProbeError("Synthetic collage color samples are not sufficiently distinguishable")
        }
        print("CAPTURE_COLLAGE_IDENTITY_PASS two distinct selected current sources match their visible collage cells")
    }

    private func emitStoreScreenshot(_ screen: String) throws {
        XCTAssertFalse(app.alerts.firstMatch.exists, "No permission or error prompt may cover a store capture")
        Thread.sleep(forTimeInterval: 1)
        let capture = XCUIScreen.main.screenshot()
        let image = capture.image
        let pixels = try XCTUnwrap(image.cgImage)
        let width = pixels.width, height = pixels.height
        let isPhone = UIDevice.current.userInterfaceIdiom == .phone
        let accepted = isPhone ? [(1260,2736),(1290,2796),(1320,2868)] : [(2064,2752),(2048,2732)]
        XCTAssertTrue(accepted.contains { $0.0 == width && $0.1 == height }, "Unaccepted native pixels \(width)x\(height)")
        // Encoding only: no resize, cropping, drawing, retouching, or overlays.
        // JPEG has no alpha. Fail visibly if an acceptable-quality native file cannot fit the approved bridge.
        var data: Data?
        var quality: CGFloat = 1
        for q in [CGFloat(1), 0.95, 0.90, 0.85, 0.80] {
            if let candidate = image.jpegData(compressionQuality: q), candidate.count <= 786432 {
                data = candidate; quality = q; break
            }
        }
        let jpeg = try XCTUnwrap(data, "Native capture exceeds 786432-byte bridge at quality >=0.80; request approved artifact bridge")
        let name = "celluloid-zh-Hans-\(isPhone ? "iphone-6.9" : "ipad-13")-\(screen).jpg"
        let hash = SHA256.hash(data: jpeg).map { String(format: "%02x", $0) }.joined()
        print("CELLULOID_STORE_META name=\(name) width=\(width) height=\(height) bytes=\(jpeg.count) sha256=\(hash) quality=\(quality) source=XCUIScreen.main configuration=Release")
        // Retain native JPEG bytes, then emit after test completion. Streaming
        // screenshot data inside XCTest can stall remote accessibility queries.
        let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("CELLULOID_STORE_ATTACHED:" + name)
    }

    private func attachHostScreenshot(_ name: String) {
        guard let jpeg = XCUIScreen.main.screenshot().image.jpegData(compressionQuality: 0.55), jpeg.count <= 500_000 else {
            XCTFail("Host evidence must remain a bounded native JPEG"); return
        }
        let attachment = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg")
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        do { try persistHostEvidence(jpeg, name: name) }
        catch { XCTFail("Could not retain bounded synthetic host evidence: \(error)") }
    }

    func testPhotosHostAssessment() throws {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        let evidenceDirectory = hostEvidenceDirectory()
        // This exact test-owned ephemeral directory contains only synthetic JPEGs.
        if FileManager.default.fileExists(atPath: evidenceDirectory.path) { try FileManager.default.removeItem(at: evidenceDirectory) }
        let authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        print("PHOTOS_HOST_AUTHORIZATION_PREREQUISITE raw=\(authorization.rawValue) expected=authorized scope=ephemeral_UI_test_runner")
        XCTAssertEqual(authorization, .authorized)
        let baselineSources = try captureFixtureIdentities("before-host")
        let expectedResources = ["celluloid-fixture-a.png": "90ce9a3adb8b98b667d6cd9fcd4c092b748744c2b49b20c15ef7d50317d6686d",
                                 "celluloid-fixture-b.png": "8daf8dec2b9de9cb70bd74943369e7a4b948545117b773b9d0aff3f70a1d1c86"]
        for fixture in baselineSources {
            XCTAssertEqual(fixture.originalFileSHA, expectedResources[fixture.resourceFilename], "Exact intended generated resource")
            XCTAssertEqual(fixture.currentPixelSHA, fixture.originalPixelSHA, "No inherited prior edit")
        }
        print("PHOTOS_HOST_PRISTINE_FIXTURES_VERIFIED count=2 unique_identifiers=true exact_resource_hashes=true current_pixels_equal_original=true")
        let hostBaseline = baselineSources[0]
        guard hostBaseline.creationDate > baselineSources[1].creationDate else { throw captureProbeError("Newest synthetic asset must have an unambiguous creation date") }
        try logSelection(hostBaseline, phase: "photos-host-newest")
        let photos = XCUIApplication(bundleIdentifier: "com.apple.mobileslideshow")
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let notificationTitle = "“Photos” Would Like to Send You Notifications"
        func declineObservedNotification(_ alert: XCUIElement) -> Bool {
            guard alert.exists && alert.label == notificationTitle else { return false }
            let deny = alert.buttons.matching(NSPredicate(format: "label IN %@", ["Don’t Allow", "Don't Allow"]))
            guard deny.count == 1, deny.element.isEnabled, deny.element.isHittable else { return false }
            print("PHOTOS_EXPECTED_NOTIFICATION_DECLINED label=\(alert.label)")
            deny.element.tap()
            let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: alert)
            return XCTWaiter.wait(for: [gone], timeout: 10) == .completed
        }
        func haltForUnexpectedAlert(_ reason: String) -> Never {
            // No UI action, XCTFail, or throwable recorder here: XCTest may catch
            // a test failure inside its callback. A Never-returning process abort
            // cannot fall through to the default permission-accepting monitor.
            // The bounded text is the diagnostic; it contains no account values.
            print("PHOTOS_HOST_FAIL_CLOSED_ABORT " + String(reason.prefix(300)))
            fatalError("Photos-host test stopped before any unknown alert action")
        }
        hostInterruption = addUIInterruptionMonitor(withDescription: "Decline only observed Photos notifications; abort on every other interruption") { alert in
            if declineObservedNotification(alert) { return true }
            haltForUnexpectedAlert("Interruption was not the single supported Photos notification decline")
        }
        func promptFree() -> Bool {
            let notification = system.alerts[notificationTitle]
            if notification.exists && !declineObservedNotification(notification) {
                haltForUnexpectedAlert("Observed Photos notification could not be explicitly declined")
            }
            guard !system.alerts.firstMatch.exists && !photos.alerts.firstMatch.exists else {
                haltForUnexpectedAlert("Unexpected alert before host interaction or pixel capture")
            }
            return true
        }
        // Install the fail-closed monitor before the first app launch, and keep
        // it installed through tearDown's last app action.
        launchChinese()
        app.terminate()
        photos.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        photos.launch()
        Thread.sleep(forTimeInterval: 3)
        func hierarchy(_ stage: String) {
            print("PHOTOS_HOST_HIERARCHY_BEGIN:\(stage)")
            print(String(photos.debugDescription.prefix(24000)))
            print("PHOTOS_HOST_HIERARCHY_END:\(stage)")
        }
        func tapLabel(_ labels: [String]) -> Bool {
            guard promptFree() else { return false }
            for label in labels {
                for control in photos.buttons.matching(NSPredicate(format: "label == %@", label)).allElementsBoundByIndex {
                    if control.exists && control.isEnabled && control.isHittable { control.tap(); return true }
                }
            }
            return false
        }
        func waitReady(_ control: XCUIElement, timeout: TimeInterval = 10) -> Bool {
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND enabled == true AND hittable == true"), object: control)
            guard XCTWaiter.wait(for: [ready], timeout: timeout) == .completed else {
                if control.exists {
                    print("PHOTOS_HOST_CONTROL_NOT_READY label=\(control.label) exists=true enabled=\(control.isEnabled) hittable=\(control.isHittable) frame=\(control.frame)")
                } else { print("PHOTOS_HOST_CONTROL_NOT_READY exists=false") }
                return false
            }
            return true
        }
        func tapReady(_ control: XCUIElement, timeout: TimeInterval = 10) -> Bool {
            guard promptFree(), waitReady(control, timeout: timeout) else { return false }
            control.tap()
            return true
        }
        func visiblePhotoMatches(_ expected: UIImage, label: String, phase: String, cropEditor: Bool = false) throws -> Bool {
            let source = try XCTUnwrap(expected.cgImage)
            // Inspect the observed one-up image, never a toolbar thumbnail. The
            // 3x3 interior samples avoid borders and system controls. The small
            // display tolerance accommodates scaling/color conversion, not a
            // different filter. Full-resource pixel oracles remain unchanged.
            let deadline = Date().addingTimeInterval(10)
            var attempt = 0
            repeat {
                attempt += 1
                guard promptFree() else { return false }
                let images = cropEditor ? [photos.otherElements["cropView"].firstMatch] :
                    photos.images.matching(NSPredicate(format: "label == %@", label)).allElementsBoundByIndex
                let candidates = images.filter {
                    let frame = $0.frame
                    return $0.exists && frame.width > photos.frame.width * 0.7 &&
                        frame.height > 100 && photos.frame.contains(frame)
                }
                if candidates.count == 1 {
                    let frame = candidates[0].frame
                    let screen = XCUIScreen.main.screenshot().image
                    let raster = try XCTUnwrap(screen.cgImage)
                    let scaleX = CGFloat(raster.width) / photos.frame.width
                    let scaleY = CGFloat(raster.height) / photos.frame.height
                    let sourceAspect = CGFloat(source.width) / CGFloat(source.height)
                    guard abs(frame.width / frame.height - sourceAspect) < 0.01 else {
                        throw captureProbeError("Observed one-up image is not the unzoomed synthetic raster")
                    }
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
                    try captureJSON("PHOTOS_HOST_VISIBLE_PIXEL_PROBE", ["phase": phase, "attempt": attempt,
                        "frame": [frame.minX, frame.minY, frame.width, frame.height], "samples": samples,
                        "maximum_delta": maximum, "display_tolerance": 12])
                    if maximum <= 12 { return true }
                } else {
                    print("PHOTOS_HOST_VISIBLE_IMAGE_NOT_READY phase=\(phase) attempt=\(attempt) candidateCount=\(candidates.count)")
                }
                Thread.sleep(forTimeInterval: 1)
            } while Date() < deadline
            return false
        }
        func openExtensionsPicker(_ stage: String) -> Bool {
            guard tapReady(photos.buttons["edit.moreButton"].firstMatch) else {
                hierarchy(stage + "-more-unavailable"); return false
            }
            // This exact submenu button was observed in the previous actual Photos hierarchy.
            guard tapReady(photos.buttons["扩展"].firstMatch) else {
                hierarchy(stage + "-submenu-unavailable"); return false
            }
            return true
        }
        func enterCelluloid(_ stage: String) -> Bool {
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
        hierarchy("launch")
        _ = tapLabel(["图库", "Library", "所有照片", "All Photos"])
        // In the observed iOS 27 host, Library presents What's New after launch.
        // Wait for that actual sheet instead of probing too early and leaving it over the grid.
        let welcomeContinue = photos.buttons["继续"].firstMatch
        let welcomeTitle = photos.staticTexts["“照片”新功能"].firstMatch
        if welcomeContinue.waitForExistence(timeout: 10) {
            guard welcomeTitle.exists else {
                hierarchy("unexpected-continue-screen")
                print("PHOTOS_HOST_RESULT:BLOCKED Continue exists outside the observed What's New sheet; no account or permission dialog accepted")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
                return
            }
            let tappable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "hittable == true"), object: welcomeContinue)
            guard XCTWaiter.wait(for: [tappable], timeout: 10) == .completed else {
                hierarchy("welcome-not-hittable")
                print("PHOTOS_HOST_RESULT:BLOCKED observed Photos welcome Continue never became hittable")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
                return
            }
            welcomeContinue.tap()
            let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: welcomeContinue)
            guard XCTWaiter.wait(for: [dismissed], timeout: 10) == .completed else {
                hierarchy("welcome-not-dismissed")
                print("PHOTOS_HOST_RESULT:BLOCKED observed Photos welcome remained after Continue")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
                return
            }
        }
        let welcomeGone = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !welcomeTitle.exists && !welcomeContinue.exists
        }, object: nil)
        guard XCTWaiter.wait(for: [welcomeGone], timeout: 10) == .completed else {
            hierarchy("welcome-still-present")
            print("PHOTOS_HOST_RESULT:BLOCKED actual What's New title or Continue still exists; fixture selection withheld")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        let lastGridImage = photos.images.matching(identifier: "PXGGridLayout-Info").element(boundBy: max(0, photos.images.matching(identifier: "PXGGridLayout-Info").count - 1))
        let gridReady = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND hittable == true"), object: lastGridImage)
        guard XCTWaiter.wait(for: [gridReady], timeout: 10) == .completed else {
            hierarchy("grid-not-ready")
            print("PHOTOS_HOST_RESULT:BLOCKED observed Photos grid not ready after welcome handling")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        hierarchy("library")
        // Observed iOS 27 Photos hierarchy exposes Images, not CollectionView Cells.
        // Six simulator stock images predate the two fixtures added during this job.
        let images = photos.images.matching(identifier: "PXGGridLayout-Info").allElementsBoundByIndex.filter { $0.exists && $0.isHittable }
        print("PHOTOS_HOST_GRID_LABELS: " + images.map { $0.label }.joined(separator: " | "))
        let latest = Array(images.suffix(2))
        let seededDatePatterns = baselineSources.map { source -> String in
            let date = Calendar.current.dateComponents([.month, .day], from: source.creationDate)
            return "\\b\(date.month!)月0?\(date.day!)日"
        }
        guard latest.count == 2,
              latest.allSatisfy({ image in seededDatePatterns.contains { image.label.range(of: $0, options: .regularExpression) != nil } }),
              let fixture = latest.last else {
            print("PHOTOS_HOST_RESULT:BLOCKED latest two accessible Photos grid images cannot be verified against the actual seeded creation dates")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        guard !welcomeTitle.exists && !welcomeContinue.exists && fixture.isHittable else {
            hierarchy("fixture-not-ready")
            print("PHOTOS_HOST_RESULT:BLOCKED identified synthetic fixture is not hittable after confirmed welcome dismissal")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        print("PHOTOS_HOST_READY welcomeTitleExists=false continueExists=false syntheticFixtureHittable=true")
        let fixtureLabel = fixture.label
        print("PHOTOS_HOST_SELECTED_SEEDED_FIXTURE: " + fixtureLabel)
        fixture.tap()
        Thread.sleep(forTimeInterval: 2)
        hierarchy("selected-photo")
        guard tapLabel(["编辑", "Edit"]) else {
            print("PHOTOS_HOST_RESULT:BLOCKED selected Photos content exposes no accessible Edit action")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        Thread.sleep(forTimeInterval: 2)
        hierarchy("editing")
        guard openExtensionsPicker("open") else {
            print("PHOTOS_HOST_RESULT:BLOCKED observed More-to-Extensions path was not ready; inspect recorded hierarchy")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        guard enterCelluloid("open") else {
            print("PHOTOS_HOST_RESULT:BLOCKED actual Extensions picker has no accessible named Celluloid entry; inspect recorded hierarchy")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        let filter = photos.buttons["tool-filter"]
        // Actual failed-run pixels show Photos loading the extension here. Wait
        // for its real semantic control rather than assuming a3-second launch.
        guard waitReady(filter, timeout: 30) else {
            hierarchy("celluloid-not-ready")
            print("PHOTOS_HOST_RESULT:BLOCKED extension entry selected but Celluloid editor not accessible")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        hierarchy("celluloid")
        filter.tap()
        let preset = photos.collectionViews.cells.element(boundBy: 1)
        guard preset.waitForExistence(timeout: 5) && preset.isHittable else {
            print("PHOTOS_HOST_RESULT:BLOCKED extension filter selector not accessible")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        preset.tap()
        Thread.sleep(forTimeInterval: 2)
        hierarchy("filtered")
        guard tapLabel(["完成", "Done"]) else {
            print("PHOTOS_HOST_RESULT:BLOCKED no accessible extension completion action")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        let sepiaReturned = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: photos.buttons["tool-filter"])
        guard XCTWaiter.wait(for: [sepiaReturned], timeout: 30) == .completed else {
            hierarchy("sepia-extension-render-not-finished")
            XCTFail("Extension did not return its rendered Sepia result"); return
        }
        hierarchy("rendered")
        guard tapReady(photos.buttons["完成"].firstMatch), photos.buttons["编辑"].firstMatch.waitForExistence(timeout: 15) else {
            hierarchy("sepia-save-not-finished")
            XCTFail("Photos did not finish saving the Sepia result"); return
        }
        hierarchy("saved")
        let persistedSepia = try captureHostIntegrity(hostBaseline, phase: "after-host-save")
        let sepiaImmediate = try visiblePhotoMatches(persistedSepia, label: fixtureLabel, phase: "immediately-after-save")
        try captureCurrentPhotoRepresentations(hostBaseline, expected: persistedSepia, phase: "after-extension-save")
        let sepiaAfterRepresentationProbe = try visiblePhotoMatches(persistedSepia, label: fixtureLabel, phase: "after-PhotoKit-representation-probe")
        var sepiaDisplayVerified = sepiaAfterRepresentationProbe
        var libraryReopenPerformed = false
        if !sepiaDisplayVerified {
            hierarchy("saved-preview-not-refreshed")
            // One normal close/reopen distinguishes an in-place Photos preview
            // refresh delay from a persisted rendering failure. Do not resave,
            // reimport or change the current resource to manufacture a pass.
            guard tapReady(photos.buttons["BackButton"].firstMatch), tapReady(lastGridImage) else {
                hierarchy("saved-preview-reopen-unavailable")
                XCTFail("Could not reopen the same newest synthetic photo for preview diagnosis"); return
            }
            libraryReopenPerformed = true
            sepiaDisplayVerified = try visiblePhotoMatches(persistedSepia, label: fixtureLabel, phase: "after-library-reopen")
            try captureHostIntegrity(hostBaseline, phase: "after-preview-reopen")
        }
        try captureJSON("PHOTOS_HOST_SEPIA_DISPLAY_RESULT", ["immediate_matches": sepiaImmediate,
            "after_representation_probe_matches": sepiaAfterRepresentationProbe,
            "library_reopen_performed": libraryReopenPerformed, "final_display_matches": sepiaDisplayVerified])
        print("PHOTOS_HOST_SEPIA_DISPLAY_VERIFIED \(sepiaDisplayVerified)")
        guard promptFree() else { return }
        attachHostScreenshot("celluloid-host-saved-sepia")
        guard tapLabel(["编辑", "Edit"]) else {
            print("PHOTOS_HOST_RESULT:PARTIAL extension rendering attempted; save/reopen not established")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        Thread.sleep(forTimeInterval: 2)
        guard openExtensionsPicker("reopen") else {
            print("PHOTOS_HOST_RESULT:PARTIAL Photos Edit reopened but observed More-to-Extensions path was not ready")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        guard enterCelluloid("reopen") else {
            print("PHOTOS_HOST_RESULT:PARTIAL editing reopened but accessible Celluloid entry was not established")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        guard waitReady(photos.buttons["tool-filter"], timeout: 30) else {
            hierarchy("reopened-not-ready")
            print("PHOTOS_HOST_RESULT:PARTIAL extension action selected during reopen but editor presence not established")
                XCTFail("Photos-host qualification did not reach the required restoration gate; see observed hierarchy")
            return
        }
        hierarchy("reopened")
        try captureHostIntegrity(hostBaseline, phase: "after-host-reopen")
        print("PHOTOS_HOST_PERSISTED_METADATA_VERIFIED hosted Sepia save/reopen and original resource integrity")
        // A toolbar alone cannot prove non-destructive restoration: if the
        // extension reopened flattened Sepia, choosing Original would stay Sepia.
        photos.buttons["tool-filter"].tap()
        let originalPreset = photos.collectionViews.cells.element(boundBy: 0)
        guard tapReady(originalPreset) else {
            hierarchy("original-filter-unavailable")
            XCTFail("Reopened host must expose the observed Original preset"); return
        }
        hierarchy("restored-original-in-extension")
        guard tapLabel(["完成", "Done"]) else {
            XCTFail("Original edit could not finish in extension"); return
        }
        // Wait for extension teardown before resolving the identically titled
        // Photos control; two rapid Done taps must not target the same extension.
        let extensionGone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: photos.buttons["tool-filter"])
        guard XCTWaiter.wait(for: [extensionGone], timeout: 30) == .completed else {
            hierarchy("original-extension-render-not-finished")
            XCTFail("Extension did not return its rendered Original result"); return
        }
        guard tapReady(photos.buttons["完成"].firstMatch) else {
            hierarchy("original-photos-save-unavailable")
            XCTFail("Photos must save the Original result from the reopened extension"); return
        }
        guard photos.buttons["编辑"].firstMatch.waitForExistence(timeout: 15) else {
            hierarchy("original-save-not-finished")
            XCTFail("Photos did not return to the saved asset"); return
        }
        try captureHostRestoredOriginal(hostBaseline)
        print("PHOTOS_HOST_EDITOR_RESTORATION_VERIFIED hosted Sepia reopen then Original/save matches original pixels within explicit JPEG tolerance")
        guard tapReady(photos.buttons["编辑"].firstMatch),
              tapReady(photos.navigationBars["PUPhotoEditView"].buttons["复原"].firstMatch) else {
            hierarchy("system-revert-unavailable")
            XCTFail("Photos system Revert command is a separate required host gate"); return
        }
        hierarchy("system-revert-confirmation")
        // Resolve only the real confirmation sheet/alert opened by that observed
        // Photos Revert action. Never accept an unrelated account/permission UI.
        let confirmation = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            photos.sheets.firstMatch.exists || photos.alerts.firstMatch.exists
        }, object: nil)
        guard XCTWaiter.wait(for: [confirmation], timeout: 10) == .completed else {
            hierarchy("system-revert-confirmation-not-observed")
            XCTFail("Photos Revert confirmation was not exposed as a sheet or alert"); return
        }
        let containers = photos.sheets.allElementsBoundByIndex + photos.alerts.allElementsBoundByIndex
        let candidates = containers.flatMap { $0.buttons.allElementsBoundByIndex }.filter {
            ($0.label.contains("复原") || $0.label.lowercased().contains("revert")) && $0.isHittable
        }
        guard candidates.count == 1 else {
            hierarchy("ambiguous-system-revert-confirmation")
            XCTFail("Expected one observed Revert confirmation action, not a guessed tap"); return
        }
        print("PHOTOS_HOST_SYSTEM_REVERT_CONFIRMATION label=\(candidates[0].label)")
        candidates[0].tap()
        let closed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !photos.sheets.firstMatch.exists && !photos.alerts.firstMatch.exists
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [closed], timeout: 15), .completed)
        try captureHostSystemRevertedOriginal(hostBaseline)
        hierarchy("after-system-revert")
        let remainsInNativeEditor = photos.navigationBars["PUPhotoEditView"].exists && photos.otherElements["cropView"].firstMatch.exists
        let revertedDisplayVerified = try visiblePhotoMatches(hostBaseline.originalImage, label: fixtureLabel,
            phase: "after-system-revert", cropEditor: remainsInNativeEditor)

        // Actual retained pixels show Revert leaves the native crop editor open.
        // Verify its original raster, then use its existing Filters control. The
        // previously ineffective native Cancel action is not claimed as passed.
        if !remainsInNativeEditor && !tapReady(photos.buttons["编辑"].firstMatch) {
            hierarchy("after-revert-edit-unavailable")
            XCTFail("Neither observed native editor nor one-up Edit is available"); return
        }
        // Controlled system-Photos edit on the same verified synthetic asset.
        guard tapReady(photos.buttons["edit.tool.filters"].firstMatch) else {
            hierarchy("native-filter-control-unavailable")
            XCTFail("Observed Photos filter tool was unavailable"); return
        }
        hierarchy("native-filter-options")
        let monochromeLabels = ["单色", "黑白", "银色", "Mono", "Silvertone", "Noir", "MONO", "SILVERTONE", "NOIR"]
        let controls = photos.descendants(matching: .any).matching(NSPredicate(format: "label IN %@", monochromeLabels))
        var selectedNativeFilter: String?
        if let individual = controls.allElementsBoundByIndex.first(where: { $0.exists && $0.isEnabled && $0.isHittable }) {
            guard tapReady(individual) else { XCTFail("Observed native filter is not actionable"); return }
            selectedNativeFilter = individual.label
        } else {
            // Actual206 hierarchy exposes this single semantic adjustable strip,
            // not CollectionView cells. Gesture on that observed control and
            // inspect its selected value; never guess a thumbnail index/position.
            let pickers = photos.otherElements.matching(NSPredicate(format: "label == %@", "滤镜选取器"))
            guard pickers.count == 1, waitReady(pickers.element) else {
                hierarchy("native-filter-picker-unavailable")
                XCTFail("Expected the single observed native filter picker"); return
            }
            let picker = pickers.element
            for attempt in 0..<10 {
                guard promptFree() else { return }
                let value = picker.value as? String ?? ""
                print("NATIVE_PHOTOS_FILTER_PICKER_STATE attempt=\(attempt) label=\(picker.label) value=\(value) frame=\(picker.frame)")
                if monochromeLabels.contains(value) { selectedNativeFilter = value; break }
                guard attempt < 9, picker.isEnabled, picker.isHittable,
                      picker.frame.width > picker.frame.height * 2, picker.frame.height < 220,
                      photos.frame.contains(picker.frame) else { break }
                picker.swipeLeft()
                let changed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                    (picker.value as? String) != value
                }, object: nil)
                guard XCTWaiter.wait(for: [changed], timeout: 5) == .completed else {
                    hierarchy("native-filter-picker-no-value-change"); break
                }
            }
        }
        guard let selectedNativeFilter = selectedNativeFilter else {
            hierarchy("native-monochrome-control-not-observed")
            XCTFail("No observed selected monochrome Photos filter after bounded semantic gestures"); return
        }
        print("NATIVE_PHOTOS_FILTER_SELECTED value=\(selectedNativeFilter)")
        hierarchy("native-filter-applied")
        guard tapReady(photos.buttons["完成"].firstMatch), waitReady(photos.buttons["编辑"].firstMatch) else {
            hierarchy("native-filter-save-unavailable")
            XCTFail("Native Photos filter could not be saved normally"); return
        }
        let nativeCurrent = try XCTUnwrap(captureFixtureIdentities("after-native-filter-save").first { $0.assetIdentifier == hostBaseline.assetIdentifier })
        XCTAssertEqual(nativeCurrent.originalFileSHA, hostBaseline.originalFileSHA)
        XCTAssertEqual(nativeCurrent.originalPixelSHA, hostBaseline.originalPixelSHA)
        XCTAssertNotEqual(nativeCurrent.currentPixelSHA, hostBaseline.originalPixelSHA)
        let nativeCG = try XCTUnwrap(nativeCurrent.currentImage.cgImage)
        let nativeSample = try capturePixel(nativeCurrent.currentImage, x: nativeCG.width / 4, y: nativeCG.height * 3 / 4)
        XCTAssertLessThanOrEqual((nativeSample.max() ?? 255) - (nativeSample.min() ?? 0), 4, "The native control must genuinely render monochrome")
        let nativeImmediate = try visiblePhotoMatches(nativeCurrent.currentImage, label: fixtureLabel, phase: "native-immediately-after-save")
        try captureCurrentPhotoRepresentations(hostBaseline, expected: nativeCurrent.currentImage, phase: "after-native-filter-save")
        guard tapReady(photos.buttons["BackButton"].firstMatch), tapReady(lastGridImage) else {
            hierarchy("native-filter-reopen-unavailable")
            XCTFail("Native filtered asset could not be reopened normally"); return
        }
        let nativeReopened = try visiblePhotoMatches(nativeCurrent.currentImage, label: fixtureLabel, phase: "native-after-library-reopen")
        guard promptFree() else { return }
        attachHostScreenshot("celluloid-host-native-filter")
        try captureJSON("NATIVE_PHOTOS_DISPLAY_CONTROL_RESULT", ["same_asset_identifier": hostBaseline.assetIdentifier,
            "rendered_monochrome_sample": nativeSample, "current_pixel_sha256": nativeCurrent.currentPixelSHA,
            "immediate_display_matches": nativeImmediate, "reopened_display_matches": nativeReopened,
            "extension_sepia_display_matches": sepiaDisplayVerified])
        XCTAssertTrue(sepiaDisplayVerified, "Actual Photos one-up view must display the saved Sepia resource")
        XCTAssertTrue(revertedDisplayVerified, "Actual Photos one-up view must display the system-reverted original")
        XCTAssertTrue(nativeImmediate && nativeReopened, "Native Photos filter control must display its own persisted output")
        guard sepiaDisplayVerified && revertedDisplayVerified && nativeImmediate && nativeReopened else {
            print("PHOTOS_HOST_RESULT:DATA_ROUNDTRIP_PASSED_DISPLAY_UNVERIFIED"); return
        }
        print("PHOTOS_HOST_RESULT:VERIFIED_EDITOR_AND_SYSTEM_REVERT editable Original restoration then actual Photos Revert clears adjustments and restores exact original pixels")
        photos.terminate()
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
private func persistHostEvidence(_ jpeg: Data, name: String) throws {
    let allowed = ["celluloid-capture-failure", "celluloid-host-saved-sepia", "celluloid-host-native-filter"]
    guard allowed.contains(name), jpeg.count <= 500_000 else { throw captureProbeError("Unexpected host image or byte count") }
    let directory = hostEvidenceDirectory()
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let existing = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).filter { $0.pathExtension == "jpg" }
    let slot: Int
    if name == "celluloid-capture-failure" {
        guard existing.count < 2 else { return }
        slot = FileManager.default.fileExists(atPath: directory.appendingPathComponent("host-evidence-1.jpg").path) ? 2 : 1
    } else { slot = name == "celluloid-host-saved-sepia" ? 1 : 2 }
    let destination = directory.appendingPathComponent("host-evidence-\(slot).jpg")
    let pixels = try XCTUnwrap(UIImage(data: jpeg)?.cgImage)
    let metadata: [String: Any] = ["slot": slot, "name": name, "bytes": jpeg.count,
        "width": pixels.width, "height": pixels.height, "sha256": captureDigest(jpeg),
        "scope": "ephemeral_test_runner_cache_only", "source": "native_XCUIScreen_JPEG_no_resize"]
    try jpeg.write(to: destination, options: .atomic)
    try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(
        to: directory.appendingPathComponent("host-evidence-\(slot).json"), options: .atomic)
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
        guard let resource = resources.first(where: { $0.type == .photo && $0.originalFilename.hasPrefix("celluloid-fixture-") }) else { continue }
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
