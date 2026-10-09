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
            if !app.launchArguments.contains("--picker-entry-observation") {
                print("UI_FAILURE_APP_BEGIN " + String(app.debugDescription.prefix(24000)))
                print("UI_FAILURE_APP_END")
            } else {
                // Avoid a full AX-tree request in the timing observation flow.
                // The original xcresult still retains the native runner events.
                print("PICKER_UI_FAILURE_TREE_OMITTED observation_only=true")
            }
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

    /// Product timing is validated from actual app-action and genuine native
    /// PHPicker lifecycle events after xcresult export. Whole-XCTest duration
    /// remains a separate diagnostic, including its historical 3-second misses.
    func testBeautifyOpensSystemPickerAndCancelsRepeatedly() {
        observeSystemPicker(phase: "stock", selectLast: false)
    }

    /// Same compiled app/simulator, after the verified synthetic-library phase.
    /// Cold means a new app launch; Photos storage is already initialized.
    func testSeededBeautifyColdOpenReopenAndOriginalSelection() {
        observeSystemPicker(phase: "seeded", selectLast: true)
    }

    private func observeSystemPicker(phase: String, selectLast: Bool) {
        let run = UUID().uuidString
        app.launchEnvironment["CELLULOID_PICKER_TRACE_RUN"] = run
        let arguments = ["--picker-entry-observation"] + (selectLast ? ["--picker-seeded-identity"] : [])
        launch(arguments, diagnostics: false)
        func trace(_ event: String, iteration: Int, details: String = "") {
            let uptime = ProcessInfo.processInfo.systemUptime
            let wall = Date().timeIntervalSince1970
            // NSLog supplies a genuine native runner clock anchor. The receipt
            // checks it against wall/uptime rather than assuming common clocks.
            NSLog("%@", "PICKER_UI_TRACE run=\(run) phase=\(phase) iteration=\(iteration) event=\(event) uptime_seconds=\(uptime) wall_seconds=\(wall) \(details)")
        }
        trace("run-begin", iteration: 0)
        let previousContinueAfterFailure = continueAfterFailure
        continueAfterFailure = true
        defer {
            trace("run-end", iteration: 0)
            continueAfterFailure = previousContinueAfterFailure
        }
        for iteration in 1...3 {
            let edit = app.buttons["edit-photo"]
            XCTAssertTrue(edit.isHittable)
            XCTAssertFalse(app.buttons["Cancel"].exists)
            let started = ProcessInfo.processInfo.systemUptime
            trace("tap-command-start", iteration: iteration)
            edit.tap()
            trace("tap-command-returned", iteration: iteration)
            let cancel = app.buttons["Cancel"]
            var firstExistsElapsed: TimeInterval?
            var firstHittableElapsed: TimeInterval?
            func measured(_ property: String, _ read: () -> Bool) -> Bool {
                let begin = ProcessInfo.processInfo.systemUptime
                let value = read()
                let end = ProcessInfo.processInfo.systemUptime
                let wall = Date().timeIntervalSince1970
                NSLog("%@", "PICKER_AX_QUERY run=\(run) iteration=\(iteration) property=\(property) value=\(value) duration_seconds=\(end - begin) end_uptime_seconds=\(end) wall_seconds=\(wall)")
                return value
            }
            let usablePicker = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                guard measured("exists", { cancel.exists }) else { return false }
                if firstExistsElapsed == nil { firstExistsElapsed = ProcessInfo.processInfo.systemUptime - started }
                guard measured("isEnabled", { cancel.isEnabled }) else { return false }
                guard measured("isHittable", { cancel.isHittable }) else { return false }
                firstHittableElapsed = ProcessInfo.processInfo.systemUptime - started
                return true
            }, object: nil)
            // Preserve the same real queries, predicate and 3-second waiter.
            // Receipt acceptance separately starts at the actual app action.
            let outcome = XCTWaiter.wait(for: [usablePicker], timeout: 3)
            let elapsed = ProcessInfo.processInfo.systemUptime - started
            print("PICKER_AUTOMATION_DIAGNOSTIC run=\(run) iteration=\(iteration) elapsed_seconds=\(elapsed) historical_budget_seconds=3 historical_within_budget=\(elapsed <= 3) result=\(outcome.rawValue) acceptance_source=native-receipt")
            print("PICKER_OBSERVATION run=\(run) iteration=\(iteration) first_exists_seconds=\(String(describing: firstExistsElapsed)) first_hittable_seconds=\(String(describing: firstHittableElapsed)) library_ready=unmeasured")
            XCTAssertNotNil(firstExistsElapsed, "Observable system control presentation was not established")
            XCTAssertEqual(outcome, .completed, "The real PHPicker Cancel action must become usable")
            XCTAssertNotNil(firstHittableElapsed, "Control visibility cannot establish interactivity")
            // Screenshots and safe recovery occur only after the observation.
            // Native receipt absence or an upper-bound overrun still blocks the
            // job, even if this test later returns home successfully.
            let evidence = XCTAttachment(screenshot: app.screenshot())
            evidence.name = "celluloid-picker-\(phase)-observation-\(iteration)"
            evidence.lifetime = .keepAlways
            add(evidence)
            if outcome != .completed {
                let recoveryStarted = ProcessInfo.processInfo.systemUptime
                let recovered = cancel.waitForExistence(timeout: 10) && cancel.isEnabled && cancel.isHittable
                print("PICKER_POST_BUDGET_RECOVERY run=\(run) iteration=\(iteration) recovered=\(recovered) elapsed_seconds=\(ProcessInfo.processInfo.systemUptime - recoveryStarted) gate_remains_failed=true")
                guard recovered else {
                    XCTFail("Cannot safely cancel the real picker after the failed observation")
                    return
                }
            }
            XCTAssertFalse(app.buttons["photos-allow-originals"].exists)
            XCTAssertFalse(app.buttons["editor-done"].exists)
            XCTAssertFalse(app.alerts.firstMatch.exists, "Opening the system picker must not request PhotoKit access")
            let selecting = selectLast && iteration == 3
            if selecting {
                trace("selection-command-start", iteration: iteration)
                selectSystemPhotos(app, indices: [0])
                let done = app.buttons["editor-done"]
                let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                    done.exists && done.isEnabled && done.isHittable
                }, object: nil)
                XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed,
                               "The real selected original must finish loading into an editable session")
                let exists = done.exists, enabled = done.isEnabled, hittable = done.isHittable
                // Both picker and editor expose a localized Cancel title. Test
                // visible grid candidates only. Genuine native ViewDidDisappear
                // is required separately by the receipt as teardown proof.
                let pickerCandidatesExist = !systemPhotoCandidates(app).isEmpty
                trace("editor-interactive-after-selection", iteration: iteration,
                      details: "editor_exists=\(exists) editor_enabled=\(enabled) editor_hittable=\(hittable) picker_candidates_exist=\(pickerCandidatesExist)")
                XCTAssertTrue(exists && enabled && hittable)
                XCTAssertFalse(pickerCandidatesExist)
                let editorCancel = app.buttons["editor-cancel"]
                guard editorCancel.exists && editorCancel.isHittable else {
                    XCTFail("Selected original editor could not be cancelled without saving"); return
                }
                editorCancel.tap()
            } else {
                trace("cancel-command-start", iteration: iteration)
                cancel.tap()
            }
            let homeExists = edit.waitForExistence(timeout: 5)
            let homeHittable = edit.isHittable
            let pickerExists = cancel.exists
            trace("home-interactive-after-dismiss", iteration: iteration,
                  details: "via=\(selecting ? "editor" : "cancel") home_exists=\(homeExists) home_hittable=\(homeHittable) picker_exists=\(pickerExists)")
            XCTAssertTrue(homeExists && homeHittable)
            XCTAssertFalse(pickerExists)
        }
    }

    func testAccessibilityHomeAndDeniedPicker() {
        launch(["--photos-denied"], diagnostics: false)
        audit("home")
        app.buttons["edit-photo"].tap()
        selectSystemPhotos(app, indices: [0])
        XCTAssertTrue(app.staticTexts["photos-state"].waitForExistence(timeout: 5))
        waitForStableLayout(["photos-state", "photos-settings"])
        audit("denied-picker")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }

    func testAccessibilityGrantedPickerEditorAndSaved() {
        launch(diagnostics: false, photosAccess: true)
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(waitForSystemPhotoPicker(app))
        audit("system-picker")
        selectSystemPhotos(app, indices: [0])
        allowOriginalEditingIfRequested(app)
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
                    // SwiftUI preserves Dynamic Type with scrolling on the
                    // smallest/landscape viewports rather than clipping titles.
                    XCTAssertTrue(edit.exists && collage.exists && footer.exists)
                    if !edit.isHittable { app.swipeDown() }
                    XCTAssertTrue(edit.isHittable)
                    XCTAssertGreaterThanOrEqual(edit.frame.height, 120)
                    XCTAssertGreaterThanOrEqual(collage.frame.height, 120)
                    XCTAssertFalse(edit.frame.intersects(collage.frame), "Primary choices must not collapse together")
                    XCTAssertGreaterThanOrEqual(footer.frame.minY + 1, max(edit.frame.maxY, collage.frame.maxY))
                    XCTAssertLessThan(footer.frame.height, app.frame.height * 0.40)
                    if !footer.isHittable { app.swipeUp() }
                    XCTAssertTrue(footer.isHittable)
                    app.swipeDown()
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
        for orientation in [UIDeviceOrientation.landscapeLeft, .portrait] {
            rotate(orientation, observing: ["privacy-policy"])
            XCTAssertTrue(policy.isHittable)
            policy.tap()
            let body = app.descendants(matching: .any).matching(identifier: "privacy-policy-body").firstMatch
            let close = app.buttons["privacy-policy-close"]
            let browser = app.buttons["privacy-policy-external-browser"]
            XCTAssertTrue(body.waitForExistence(timeout: 5), "The bundled policy must appear without loading a website")
            XCTAssertTrue(close.isHittable)
            XCTAssertEqual(close.label, "Close")
            XCTAssertTrue(browser.isHittable)
            XCTAssertEqual(browser.label, "Open in External Browser")
            let publicText = [body.value as? String, Optional(body.label)].compactMap { $0 }
            let text = publicText.first {
                $0.contains("This policy is available offline.") && $0.contains("Privacy questions: 100mango@gmail.com")
            }
            XCTAssertNotNil(text, "The native text view must expose the complete offline policy in its public value or label")
            for phrase in ["available offline", "Core Image", "iCloud", "Sharing", "GitHub Pages", "IP address", "does not delete", "100mango@gmail.com"] {
                XCTAssertTrue(text?.contains(phrase) == true, "The offline body must include: \(phrase)")
            }
            XCTAssertEqual(app.webViews.count, 0)
            XCTAssertEqual(app.state, .runningForeground)
            body.swipeUp()
            XCTAssertTrue(close.isHittable && browser.isHittable, "Scrolling must keep both explicit actions accessible")
            // The unit test captures the browser action's URL. This UI flow must
            // never launch a browser or contact the external website.
            close.tap()
            XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
            XCTAssertTrue(policy.isHittable)
            XCTAssertFalse(body.exists)
        }
    }

    func testDeniedPhotosShowsRecoveryAndCanCancelRepeatedly() {
        launch(["--photos-denied"])
        for _ in 0..<2 {
            app.buttons["edit-photo"].tap()
            selectSystemPhotos(app, indices: [0])
            let state = app.staticTexts["photos-state"]
            XCTAssertTrue(state.waitForExistence(timeout: 5))
            XCTAssertTrue(app.buttons["photos-settings"].isHittable)
            XCTAssertFalse(app.buttons["editor-done"].exists)
            app.buttons["Cancel"].tap()
            XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
        }
    }
    func testLimitedEmptyPhotosHasManagementAndAdaptiveLayout() {
        launch(["--photos-limited-empty"])
        app.buttons["make-collage"].tap()
        selectSystemPhotos(app, indices: [0])
        XCTAssertTrue(app.buttons["manage-photos"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["photos-state"].label.contains("unavailable"))
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
        selectSystemPhotos(app, indices: [0])
        allowOriginalEditingIfRequested(app)
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
        selectSystemPhotos(app, indices: [0])
        allowOriginalEditingIfRequested(app)
        XCTAssertTrue(app.buttons["editor-done"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["tool-bubble"].isHittable)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }
    func testTwoPhotoCollageZoomRotateAndSave() {
        launch(photosAccess: true)
        app.buttons["make-collage"].tap()
        selectSystemPhotos(app, indices: [0, 1])
        allowOriginalEditingIfRequested(app)
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
    /// The disposable CI simulator adds controlled fixtures dated today; stock
    /// simulator photos may also exist. Match only public dated content here.
    /// Match public user-visible content, never Photos' private identifiers.
    func systemPhotoCandidates(_ app: XCUIApplication) -> [XCUIElement] {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.dateFormat = "MMMM d"
        let date = formatter.string(from: Date())
        formatter.dateFormat = "MMMM dd"
        let paddedDate = formatter.string(from: Date())
        return app.images.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@ OR label CONTAINS[c] %@", date, paddedDate, "Today"))
            .allElementsBoundByIndex.filter { $0.isHittable && $0.frame.width >= 40 && $0.frame.height >= 40 }
    }

    func waitForSystemPhotoPicker(_ app: XCUIApplication) -> Bool {
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !self.systemPhotoCandidates(app).isEmpty
        }, object: nil)
        return XCTWaiter.wait(for: [ready], timeout: 15) == .completed
    }

    @discardableResult
    func selectSystemPhotos(_ app: XCUIApplication, indices: [Int], file: StaticString = #filePath, line: UInt = #line) -> [String] {
        XCTAssertTrue(waitForSystemPhotoPicker(app), "The real PHPicker must expose public synthetic-photo labels", file: file, line: line)
        let candidates = systemPhotoCandidates(app)
        guard let maximum = indices.max(), maximum < candidates.count else {
            XCTFail("Missing synthetic picker fixtures: " + String(app.debugDescription.prefix(6000)), file: file, line: line)
            return []
        }
        let selected = indices.map { candidates[$0] }
        let labels = selected.map(\.label)
        for photo in selected { photo.tap() }
        // Single selection may finish immediately; multiple selection has a
        // visible Add/Done confirmation. Only those public actions are allowed.
        let transitioned = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            if app.buttons["editor-done"].exists || app.buttons["collage-done"].exists || app.staticTexts["photos-state"].exists { return true }
            let done = app.navigationBars.buttons.matching(NSPredicate(format: "label == 'Done' OR label == 'Add' OR label BEGINSWITH 'Add ('"))
            if done.count == 1, done.element.isEnabled, done.element.isHittable { done.element.tap(); return true }
            return false
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [transitioned], timeout: 10), .completed, file: file, line: line)
        return labels
    }

    func allowOriginalEditingIfRequested(_ app: XCUIApplication) {
        let allow = app.buttons["photos-allow-originals"]
        if allow.waitForExistence(timeout: 3) { allow.tap() }
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let title = "Allow “Celluloid” to access your photo library?"
        let completed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            if app.buttons["editor-done"].exists || app.buttons["collage-done"].exists { return true }
            if let alert = [system.alerts[title], app.alerts[title]].first(where: { $0.exists }) {
                let actions = alert.buttons.matching(NSPredicate(format: "label IN %@", ["Allow Full Access", "Allow Access to All Photos"]))
                guard actions.count == 1, actions.element.isEnabled, actions.element.isHittable else { return false }
                actions.element.tap()
            }
            return false
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [completed], timeout: 15), .completed)
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
