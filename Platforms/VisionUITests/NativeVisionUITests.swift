import XCTest

final class NativeVisionUITests: XCTestCase {
    override func tearDownWithError() throws {
        let app = XCUIApplication(); if app.state != .notRunning { app.terminate() }
        try super.tearDownWithError()
    }
    func testNativeDocumentBrowserLaunchAndNewDocument() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        defer { app.terminate() }
        print("VISION_NATIVE_LAUNCH state=\(app.state.rawValue)")
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "native-vision-launch"; capture.lifetime = .keepAlways; add(capture)
        try openEditor(in:app)
        let editor = app.buttons["editor.import-files"]
        XCTAssertTrue(editor.isHittable)
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
        XCTAssertTrue(text.waitForExistence(timeout: 10)); text.tap()
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
        XCTAssertTrue(layer.waitForExistence(timeout: 10)); layer.tap()
        XCTAssertTrue(text.waitForExistence(timeout: 10)); XCTAssertEqual(text.value as? String, "Vision 世界")
        capture(app, name: "vision-saved-document-reopened")
        print("VISION_NATIVE_DOCUMENT_REOPEN real process relaunch restored source dimensions and exact bubble text")
        if #available(visionOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
    }
    private func openEditor(in app:XCUIApplication) throws {
        let editor = app.buttons["editor.import-files"]
        if editor.exists { return }
        let create = app.buttons["FullDocumentManagerViewControllerNavigationBarCreateButtonIdentifier"]
        if !create.exists {
            // The exact f9 hierarchy showed the native No Document shell, with
            // a Documents navigation button. Opening that real browser is a
            // required user action, not an arbitrary additional wait for Create.
            let documents = app.navigationBars.buttons["Documents"].firstMatch
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
