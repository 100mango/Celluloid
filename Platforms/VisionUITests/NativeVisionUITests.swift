import XCTest

final class NativeVisionUITests: XCTestCase {
    private var failClosedInterruption: NSObjectProtocol?
    override func setUpWithError() throws {
        try super.setUpWithError()
        // Install before every launch. Known consent/dialog controls are handled
        // explicitly by the test; every otherwise-unhandled interruption stops
        // this process without returning to XCTest's default auto-handler.
        failClosedInterruption = addUIInterruptionMonitor(withDescription: "Abort every unhandled native system interruption") { _ in
            // No UI query, XCTest failure recorder or throwable callback work:
            // none may fail and fall through to another monitor/default action.
            print("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=vision")
            fatalError("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=vision; unexpected interruption; no alert action taken")
        }
    }
    override func tearDownWithError() throws {
        defer {
            if let monitor = failClosedInterruption { removeUIInterruptionMonitor(monitor) }
            failClosedInterruption = nil
        }
        let app = XCUIApplication(); if app.state != .notRunning { app.terminate() }
        try super.tearDownWithError()
    }
    func testNativeDocumentBrowserLaunchAndNewDocument() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        defer { app.terminate() }
        print("VISION_NATIVE_LAUNCH state=\(app.state.rawValue)")
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "native-vision-launch"; capture.lifetime = .keepAlways; add(capture)
        try openEditor(in:app)
        let editor = app.buttons["editor.import-files"]
        XCTAssertTrue(editor.isHittable)
        XCTAssertEqual(editor.label, "导入文件")
        XCTAssertTrue(app.staticTexts["原生照片编辑器"].exists)
        print("VISION_NATIVE_EDITOR_READY importHittable=\(editor.isHittable)")
        let editorCapture = XCTAttachment(screenshot: app.screenshot()); editorCapture.name = "native-vision-editor-ready"; editorCapture.lifetime = .keepAlways; add(editorCapture)
        if #available(visionOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
    }
}

extension NativeVisionUITests {
    func testRealFilesImportBubbleAndPNGExport() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch(); defer { app.terminate() }
        try openEditor(in:app)
        let documentName = app.navigationBars.firstMatch.identifier
        XCTAssertFalse(documentName.isEmpty)
        // VISION_FILES_DIAG_BEGIN:failure-receipts
        // Diagnostics observe this same document and never replace its original assertions.
        func filesDiagnosticFailure(_ stage: String) {
            let full = app.debugDescription
            let bytes = Array(full.utf8), cap = 65536
            let complete = bytes.count <= cap
            let bounded = complete ? full : String(decoding: bytes.prefix(cap / 2), as: UTF8.self)
                + "\n[bounded middle omission]\n" + String(decoding: bytes.suffix(cap / 2), as: UTF8.self)
            let attachment = XCTAttachment(string: bounded)
            attachment.name = "vision-files-diag-" + stage + "-ax"
            attachment.lifetime = .keepAlways; add(attachment)
            print("VISION_FILES_DIAGNOSTIC_AX stage=\(stage) complete=\(complete) fullBytes=\(bytes.count) retainedBytes=\(bounded.utf8.count)")
            capture(app, name: "vision-files-diag-" + stage + "-screen")
        }
        // VISION_FILES_DIAG_END:failure-receipts
        let importButton = app.buttons["editor.import-files"]
        importButton.tap()
        print("VISION_FILES_PICKER_REQUESTED state=\(app.state.rawValue)")
        let file = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'VisionSynthetic' OR label == 'VisionSynthetic.png'")).firstMatch
        if !file.waitForExistence(timeout: 4) {
            let browse = app.buttons["Browse"]
            if browse.exists { browse.tap() }
            let local = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'On My Apple Vision Pro' OR label == 'On My Vision Pro'")).firstMatch
            if local.waitForExistence(timeout: 4) { local.tap() }
            let folder = app.cells.matching(NSPredicate(format: "label BEGINSWITH 'Celluloid'")).firstMatch
            if folder.waitForExistence(timeout: 4) { folder.tap() }
        }
        let fileFound = file.waitForExistence(timeout: 10)
        if !fileFound { capture(app, name: "vision-files-location-failure"); print("VISION_FILES_LOCATION_AX " + app.debugDescription) }
        XCTAssertTrue(fileFound); file.tap()
        let open = app.buttons["Open"]
        if open.waitForExistence(timeout: 3) { open.tap() }
        XCTAssertTrue(app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 20))
        app.buttons["editor.add-bubble"].tap()
        let bubble = app.buttons["asset.say1"]; XCTAssertTrue(bubble.waitForExistence(timeout: 10)); bubble.tap()
        let text = app.descendants(matching: .any)["editor.bubble-text"].firstMatch
        // VISION_FILES_DIAG_BEGIN:fixture-identity
        XCTAssertTrue(text.waitForExistence(timeout: 10))
        let diagnosticLayers = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'layer.'"))
        if diagnosticLayers.count != 1 { filesDiagnosticFailure("identity") }
        XCTAssertEqual(diagnosticLayers.count, 1, "A fresh Files document must identify exactly its inserted layer")
        let diagnosticLayerIdentifier = diagnosticLayers.firstMatch.identifier
        XCTAssertTrue(diagnosticLayerIdentifier.hasPrefix("layer."))
        XCTAssertNotNil(UUID(uuidString: String(diagnosticLayerIdentifier.dropFirst(6))))
        let fixtureReceipt: [String: Any] = ["schema": "Celluloid.VisionFilesFixture.1", "document_name": documentName, "layer_identifier": diagnosticLayerIdentifier]
        let fixtureReceiptBytes = try JSONSerialization.data(withJSONObject: fixtureReceipt, options: [.sortedKeys])
        print("VISION_FILES_FIXTURE_JSON " + String(decoding: fixtureReceiptBytes, as: UTF8.self))
        text.tap()
        // VISION_FILES_DIAG_END:fixture-identity
        print("VISION_TEXT_FOCUS value=\(text.value ?? "none") hittable=\(text.isHittable)")
        // Two separate ordinary key events must survive without retapping the
        // field. Do not hide a first-keystroke focus/reset defect behind paste.
        text.typeText("A")
        let first = String(describing: text.value ?? "")
        text.typeText("B")
        let second = String(describing: text.value ?? "")
        print("VISION_SEQUENTIAL_TEXT first=\(first) second=\(second) element=\(text.debugDescription)")
        continueAfterFailure = true
        XCTAssertTrue(first.contains("A") && second.contains("AB"), "Sequential key events must retain text and focus")
        continueAfterFailure = false
        text.press(forDuration: 1.1)
        let selectMenu = app.menuItems["Select All"].firstMatch
        let selectButton = app.buttons["Select All"].firstMatch
        let hasMenu = selectMenu.waitForExistence(timeout: 3)
        let hasButton = !hasMenu && selectButton.waitForExistence(timeout: 3)
        if hasMenu { selectMenu.tap() } else if hasButton { selectButton.tap() }
        else { print("VISION_SELECT_ALL_AX " + String(app.debugDescription.prefix(20000))) }
        continueAfterFailure = true
        XCTAssertTrue(hasMenu || hasButton, "Use the real Select All action before replacing text")
        continueAfterFailure = false
        if hasMenu || hasButton { text.typeText("Vision 世界") }
        let completeText = NSPredicate(format: "value == %@", "Vision 世界")
        let entered = XCTWaiter.wait(for: [expectation(for: completeText, evaluatedWith: text)], timeout: 10) == .completed
        print("VISION_TEXT_AFTER_ENTRY value=\(text.value ?? "none") complete=\(entered)")
        // Retain a real text failure while allowing the independent export route
        // to establish whether its own observed Save control works.
        continueAfterFailure = true
        XCTAssertTrue(entered, "The real editor must retain the entire multilingual replacement")
        continueAfterFailure = false
        capture(app, name: "vision-imported-editable-bubble")
        app.buttons["editor.export"].tap()
        let png = app.buttons["PNG…"]; XCTAssertTrue(png.waitForExistence(timeout: 10)); png.tap()
        // Actual 9b hierarchy exposed this Save control in the system exporter.
        // A broad Export/Save query chose the obscured editor.export toolbar.
        let save = app.navigationBars["FullDocumentManagerViewControllerNavigationBar"].buttons["DOCPicker.actionButton"]
        let canSave = save.waitForExistence(timeout: 20)
        if !canSave { print("VISION_EXPORT_PICKER_AX " + String(app.debugDescription.prefix(24000))) }
        XCTAssertTrue(canSave); XCTAssertEqual(save.label, "Save"); XCTAssertTrue(save.isHittable)
        save.tap()
        let verified = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Exported and verified '")).firstMatch
        let completed = verified.waitForExistence(timeout: 20)
        if !completed { capture(app, name: "vision-export-readback-failure"); print("VISION_EXPORT_RESULT_AX " + app.debugDescription) }
        XCTAssertTrue(completed)
        capture(app, name: "vision-png-export-verified")
        let undo = app.buttons["editor.undo"], redo = app.buttons["editor.redo"]
        XCTAssertTrue(undo.isEnabled); undo.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 10), "Undoing the last text edit should keep its bubble")
        XCTAssertNotEqual(text.value as? String, "Vision 世界")
        XCTAssertTrue(redo.isEnabled); redo.tap()
        XCTAssertEqual(text.value as? String, "Vision 世界")
        // VISION_FILES_DIAG_BEGIN:post-redo-model
        let diagnosticModelRow = app.buttons.matching(identifier: diagnosticLayerIdentifier).firstMatch
        let diagnosticExpectedLabel = "Select layer: Vision 世界"
        let diagnosticModelMatched = XCTWaiter.wait(for: [expectation(for: NSPredicate(format: "exists == true AND label == %@", diagnosticExpectedLabel), evaluatedWith: diagnosticModelRow)], timeout: 10) == .completed
        let modelReceipt: [String: Any] = ["schema": "Celluloid.VisionFilesModel.1", "stage": "post-redo", "document_name": documentName, "layer_identifier": diagnosticLayerIdentifier, "expected_text": "Vision 世界", "matched": diagnosticModelMatched, "actual_label": diagnosticModelRow.exists ? String(diagnosticModelRow.label.prefix(256)) : "missing layer"]
        let modelReceiptBytes = try JSONSerialization.data(withJSONObject: modelReceipt, options: [.sortedKeys])
        print("VISION_FILES_MODEL_JSON " + String(decoding: modelReceiptBytes, as: UTF8.self))
        if !diagnosticModelMatched { filesDiagnosticFailure("post-redo") }
        XCTAssertTrue(diagnosticModelMatched, "The same recipe-backed layer UUID must retain exact multilingual text after Redo")
        // Documents exposes no observed disk-save completion. Keep the original
        // navigation/termination below; do not add a delay or claim a save barrier.
        // VISION_FILES_DIAG_END:post-redo-model
        print("VISION_NATIVE_UNDO_REDO real document controls restored exact multilingual text")
        let documents = app.navigationBars.buttons["Documents"].firstMatch
        XCTAssertTrue(documents.exists); documents.tap()
        app.terminate(); app.launch()
        if !app.buttons["editor.import-files"].waitForExistence(timeout: 5) {
            let browse = app.navigationBars.buttons["Documents"].firstMatch
            if browse.exists { browse.tap() }
            let saved = app.cells.matching(NSPredicate(format: "identifier BEGINSWITH %@", documentName + ",")).firstMatch
            let found = saved.waitForExistence(timeout: 30)
            if !found { print("VISION_REOPEN_BROWSER_AX " + String(app.debugDescription.prefix(24000))) }
            XCTAssertTrue(found); saved.tap()
        }
        XCTAssertTrue(app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 20))
        let layer = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'layer.' AND label == %@", "Select layer: Vision 世界")).firstMatch
        // VISION_FILES_DIAG_BEGIN:reopen-failure
        let diagnosticReopenedMatched = layer.waitForExistence(timeout: 10)
        if !diagnosticReopenedMatched { filesDiagnosticFailure("reopen-layer") }
        XCTAssertTrue(diagnosticReopenedMatched)
        if layer.identifier != diagnosticLayerIdentifier { filesDiagnosticFailure("reopen-identity") }
        XCTAssertEqual(layer.identifier, diagnosticLayerIdentifier, "Reopen must retain the same document layer identity")
        layer.tap()
        // VISION_FILES_DIAG_END:reopen-failure
        XCTAssertTrue(text.waitForExistence(timeout: 10)); XCTAssertEqual(text.value as? String, "Vision 世界")
        capture(app, name: "vision-saved-document-reopened")
        print("VISION_NATIVE_DOCUMENT_REOPEN real process relaunch restored source dimensions and exact bubble text")
        if #available(visionOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
    }
    func testSeededDocumentSequentialTextUndoRedoAndBrowserReopen() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); defer { app.terminate() }
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        try openRemainingDocument(in: app)
        XCTAssertTrue(app.staticTexts["120 × 80 px"].waitForExistence(timeout: 20))
        app.buttons["editor.add-bubble"].tap()
        let bubble = app.buttons["asset.say1"]
        XCTAssertTrue(bubble.waitForExistence(timeout: 10)); XCTAssertTrue(bubble.isHittable); bubble.tap()
        // Observe the real transition implicated by 9ff before the first tap.
        // Do not force focus, retry the tap or inject a final-text fixture.
        XCTAssertEqual(XCTWaiter.wait(for: [expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: bubble)], timeout: 10), .completed)
        print("VISION_REMAINING_PALETTE_DISMISSED real bubble insertion")
        let fields = app.textViews.matching(identifier: "editor.bubble-text")
        let text = fields.firstMatch
        XCTAssertTrue(text.waitForExistence(timeout: 10)); XCTAssertEqual(fields.count, 1)
        XCTAssertEqual(text.value as? String, "Hello"); XCTAssertTrue(text.isHittable)
        // The text view owns a local draft. Verify the independent recipe-backed
        // layer button at each boundary; a correct draft alone is not a model edit.
        let layers = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'layer.'"))
        XCTAssertEqual(layers.count, 1)
        let layerIdentifier = layers.firstMatch.identifier
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: "Hello", stage: "initial")
        print("VISION_REMAINING_PRE_TAP " + String(text.debugDescription.prefix(4000)))
        text.tap() // Exactly one ordinary tap; no scripted focus or text injection.
        text.typeText("A"); let first = String(describing: text.value ?? "")
        text.typeText("B"); let second = String(describing: text.value ?? "")
        print("VISION_REMAINING_SEQUENTIAL first=\(first) second=\(second)")
        XCTAssertTrue(first.contains("A") && second.contains("AB"), "Consecutive keys must retain focus without retapping")
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: second, stage: "sequential")
        text.press(forDuration: 1.1)
        let selectMenu = app.menuItems["Select All"].firstMatch
        let selectButton = app.buttons["Select All"].firstMatch
        if selectMenu.waitForExistence(timeout: 3) { selectMenu.tap() }
        else { XCTAssertTrue(selectButton.waitForExistence(timeout: 3)); selectButton.tap() }
        text.typeText("Vision 世界")
        XCTAssertEqual(XCTWaiter.wait(for: [expectation(for: NSPredicate(format: "value == %@", "Vision 世界"), evaluatedWith: text)], timeout: 10), .completed)
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: "Vision 世界", stage: "replacement")
        let undo = app.buttons["editor.undo"], redo = app.buttons["editor.redo"]
        XCTAssertTrue(undo.isEnabled); undo.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 10)); XCTAssertNotEqual(text.value as? String, "Vision 世界")
        let undoneText = try XCTUnwrap(text.value as? String)
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: undoneText, stage: "undo")
        XCTAssertTrue(redo.isEnabled); redo.tap(); XCTAssertEqual(text.value as? String, "Vision 世界")
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: "Vision 世界", stage: "redo")
        print("VISION_REMAINING_UNDO_REDO exact multilingual replacement restored")
        let documents = app.navigationBars.buttons["Documents"].firstMatch
        XCTAssertTrue(documents.exists); documents.tap()
        // The system Documents action exposes the browser. Its window layout
        // is evidence, not a save/close contract. Do not require a placeholder
        // from another window or terminate the process as a save barrier.
        print("VISION_REMAINING_BROWSER_TRANSITION editorExposed=\(app.buttons["editor.import-files"].exists) emptyShellObserved=\(app.staticTexts["No Document"].exists); neither observation proves close or completed save")
        recordRemainingBrowser(app, stage: "after-documents-before-browser-reopen")
        // Reselect through the already observed real Files route. This may use
        // cached document state; independent final disk readback remains required.
        try openRemainingDocument(in: app)
        XCTAssertTrue(app.staticTexts["120 × 80 px"].waitForExistence(timeout: 20))
        requireRemainingModelText(in: app, identifier: layerIdentifier, expected: "Vision 世界", stage: "reopen")
        let reopened = app.buttons.matching(identifier: layerIdentifier).firstMatch
        XCTAssertTrue(reopened.waitForExistence(timeout: 10)); reopened.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 10)); XCTAssertEqual(text.value as? String, "Vision 世界")
        print("VISION_REMAINING_BROWSER_REOPEN actual file reselection retained source dimensions and exact text; not a close/save-completion receipt")
    }
    private func requireRemainingModelText(in app: XCUIApplication, identifier: String, expected: String, stage: String) {
        XCTAssertTrue(identifier.hasPrefix("layer."))
        guard !expected.isEmpty else {
            XCTFail("DIAGNOSTIC BOUNDARY: An empty draft uses the bubble-title fallback label, so this label cannot prove the raw model text at \(stage)")
            return
        }
        let layer = app.buttons.matching(identifier: identifier).firstMatch
        let label = "Select layer: " + String(expected.prefix(80))
        let matched = XCTWaiter.wait(for: [expectation(for: NSPredicate(format: "exists == true AND label == %@", label), evaluatedWith: layer)], timeout: 10) == .completed
        print("VISION_REMAINING_MODEL stage=\(stage) identifier=\(identifier) expected=\(label) matched=\(matched)")
        if !matched { print("VISION_REMAINING_MODEL_FAILURE stage=\(stage) actual=" + (layer.exists ? layer.label : "missing layer")) }
        XCTAssertTrue(matched, "The recipe-backed layer must match the text draft at \(stage)")
    }
    private func recordRemainingBrowser(_ app: XCUIApplication, stage: String) {
        // Scan the whole snapshot first. The former prefix cut off the file region.
        let lines = app.debugDescription.components(separatedBy: "\n")
        var sidebar: [String] = [], content: [String] = []
        var sidebarDepth: Int?
        for line in lines {
            let depth = line.prefix(while: { $0 == " " }).count
            if let rootDepth = sidebarDepth, depth <= rootDepth { sidebarDepth = nil }
            if line.contains("DOC.sidebar.") || line.contains("DOCSidebarView") { sidebarDepth = depth }
            if sidebarDepth != nil { sidebar.append(line) } else { content.append(line) }
        }
        // Keep every node type outside the observed sidebar subtrees, including
        // Other containers. No semantic-type filter may discard a file node.
        for (name, values, cap) in [("sidebar", sidebar, 49152), ("content-and-shell", content, 98304)] {
            let text = values.joined(separator: "\n")
            if text.utf8.count <= cap {
                print("VISION_REMAINING_BROWSER_AX stage=\(stage) region=\(name) complete=true bytes=\(text.utf8.count)\n" + text)
            } else {
                let bytes = Array(text.utf8)
                let start = String(decoding: bytes.prefix(cap / 2), as: UTF8.self)
                let end = String(decoding: bytes.suffix(cap / 2), as: UTF8.self)
                print("VISION_REMAINING_BROWSER_AX stage=\(stage) region=\(name) complete=false fullBytes=\(bytes.count)\n" + start + "\n[bounded middle omission]\n" + end)
                XCTFail("Document-browser AX region exceeded its fixed evidence cap")
            }
        }
    }
    private func openRemainingDocument(in app: XCUIApplication) throws {
        let documents = app.navigationBars.buttons["Documents"].firstMatch
        if documents.exists && documents.isHittable { documents.tap() }
        recordRemainingBrowser(app, stage: "initial")
        // Normalize to the observed local root on both launch and real reopen.
        let locations = app.cells.matching(identifier: "DOC.sidebar.item.On My Apple Vision Pro")
        let local = locations.firstMatch
        let localReady = local.waitForExistence(timeout: 10)
        if !localReady || locations.count != 1 || !local.isHittable { recordRemainingBrowser(app, stage: "local-location-unavailable") }
        XCTAssertTrue(localReady); XCTAssertEqual(locations.count, 1); XCTAssertTrue(local.isHittable); local.tap()
        // Exact Cell and accessibility identifier observed in run37648299628.
        // A direct readiness query replaces the slow multi-query block predicate.
        let folders = app.cells.matching(identifier: "Celluloid, Container")
        let folder = folders.firstMatch
        let folderReady = folder.waitForExistence(timeout: 20)
        let titleMatches = folderReady && (folder.label == "Celluloid, 1 item" || folder.staticTexts["Celluloid"].exists)
        if !folderReady || folders.count != 1 || !titleMatches || !folder.isHittable { recordRemainingBrowser(app, stage: "owned-app-folder-unavailable") }
        XCTAssertTrue(folderReady); XCTAssertEqual(folders.count, 1); XCTAssertTrue(titleMatches)
        XCTAssertTrue(folder.isEnabled); XCTAssertTrue(folder.isHittable)
        print("VISION_REMAINING_BROWSER_ITEM stage=owned-app-folder identifier=\(folder.identifier) label=\(folder.label) frame=\(folder.frame)")
        folder.tap()
        // Exact Cell identifier and title observed in run37654222192. The
        // mutable timestamp/byte-count label is diagnostic only, never a key.
        let files = app.cells.matching(identifier: "VisionRemaining, celluloid")
        let document = files.firstMatch
        let documentReady = document.waitForExistence(timeout: 20)
        let documentTitleMatches = documentReady && document.staticTexts["VisionRemaining"].exists
        if !documentReady || files.count != 1 || !documentTitleMatches || !document.isHittable { recordRemainingBrowser(app, stage: "exact-seed-document") }
        XCTAssertTrue(documentReady); XCTAssertEqual(files.count, 1); XCTAssertTrue(documentTitleMatches)
        XCTAssertTrue(document.isEnabled); XCTAssertTrue(document.isHittable)
        print("VISION_REMAINING_BROWSER_ITEM stage=exact-seed-document identifier=\(document.identifier) label=\(document.label) frame=\(document.frame)")
        document.tap()
        XCTAssertTrue(app.buttons["editor.import-files"].waitForExistence(timeout: 30))
    }
    func testSimplifiedChineseDocumentPrivacyAndLargeText() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); defer { app.terminate() }
        var ordinaryHeight: CGFloat = 0
        for large in [false, true] {
            if app.state != .notRunning { app.terminate() }
            app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-UIPreferredContentSizeCategoryName",
                                   large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch(); try openEditor(in: app)
            XCTAssertEqual(app.buttons["editor.import-files"].label, "导入文件")
            let heading = app.staticTexts["原生照片编辑器"]
            XCTAssertTrue(heading.waitForExistence(timeout: 10)); let height = heading.frame.height
            if large {
                continueAfterFailure = true
                XCTAssertGreaterThan(height, ordinaryHeight, "The real Chinese editor must show an actual text-size change")
                continueAfterFailure = false
            } else { ordinaryHeight = height }
            let privacy = app.buttons["editor.privacy"]
            XCTAssertTrue(privacy.exists); XCTAssertEqual(privacy.label, "隐私政策")
            for _ in 0..<8 {
                if privacy.isHittable { break }
                let scroll = app.scrollViews.containing(.button, identifier: "editor.privacy").firstMatch
                XCTAssertTrue(scroll.exists); scroll.swipeUp()
            }
            XCTAssertTrue(privacy.isHittable); privacy.tap()
            let done = app.buttons["完成"].firstMatch
            XCTAssertTrue(done.waitForExistence(timeout: 10)); XCTAssertTrue(done.isHittable)
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。")).firstMatch.exists)
            // Keep one ordinary screenshot; the largest-text pass establishes
            // the actual policy/Done path without a second optional capture.
            if !large { capture(app, name: "vision-zh-Hans-privacy") }
            if #available(visionOS 27.0, *) {
                let previous = continueAfterFailure; continueAfterFailure = true
                defer { continueAfterFailure = previous }
                try app.performAccessibilityAudit(for: .all) { issue in
                print("NATIVE_ACCESSIBILITY_ISSUE state=vision-zh-Hans requestedLarge=\(large) description=\(issue.compactDescription) element=\(issue.element?.debugDescription ?? "none")"); return false
                }
            }
            done.tap(); XCTAssertTrue(app.buttons["editor.import-files"].isHittable)
            print("VISION_ZH_HANS_DOCUMENT_PRIVACY requestedLarge=\(large) headingHeight=\(height) ordinaryHeight=\(ordinaryHeight)")
        }
    }
    private func openEditor(in app:XCUIApplication) throws {
        let editor = app.buttons["editor.import-files"]
        if editor.exists { return }
        let create = app.buttons["FullDocumentManagerViewControllerNavigationBarCreateButtonIdentifier"]
        if !create.exists {
            // The exact f9 hierarchy showed the native No Document shell, with
            // a Documents navigation button. Opening that real browser is a
            // required user action, not an arbitrary additional wait for Create.
            let documents = app.navigationBars.buttons.matching(NSPredicate(format: "label == 'Documents' OR label == '文稿' OR label == '文档'")).firstMatch
            print("VISION_DOCUMENT_ROUTE documentsVisible=\(documents.exists) state=\(app.state.rawValue)")
            if documents.exists && documents.isHittable { documents.tap() }
        }
        let found = create.waitForExistence(timeout:45)
        if !found { capture(app,name:"vision-document-browser-create-failure");print("VISION_DOCUMENT_CREATE_FAILURE_AX " + String(app.debugDescription.prefix(40000))) }
        XCTAssertTrue(found);XCTAssertTrue(create.isHittable);create.tap()
        let ready = editor.waitForExistence(timeout:60)
        if !ready { capture(app,name:"vision-document-transition-failure");print("VISION_DOCUMENT_TRANSITION_FAILURE_AX " + String(app.debugDescription.prefix(40000))) }
        XCTAssertTrue(ready)
    }
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
