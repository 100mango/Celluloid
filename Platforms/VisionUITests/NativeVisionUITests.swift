import XCTest

final class NativeVisionUITests: XCTestCase {
    func testNativeDocumentBrowserLaunchAndNewDocument() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        defer { app.terminate() }
        print("VISION_NATIVE_UI_AX " + app.debugDescription)
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "native-vision-launch"; capture.lifetime = .keepAlways; add(capture)
        let editor = app.buttons["editor.import-files"]
        if !editor.exists {
            let create = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Create' OR label CONTAINS[c] 'New Document'")).firstMatch
            XCTAssertTrue(create.waitForExistence(timeout: 15), "Inspect native launch capture before adapting document-browser controls")
            create.tap()
        }
        XCTAssertTrue(editor.waitForExistence(timeout: 15))
        XCTAssertTrue(editor.isHittable)
        print("VISION_NATIVE_EDITOR_AX " + app.debugDescription)
        let editorCapture = XCTAttachment(screenshot: app.screenshot()); editorCapture.name = "native-vision-editor-ready"; editorCapture.lifetime = .keepAlways; add(editorCapture)
        if #available(visionOS 27.0, *) { try app.performAccessibilityAudit(for: .all) }
    }
}

extension NativeVisionUITests {
    func testRealFilesImportBubbleAndPNGExport() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch(); defer { app.terminate() }
        let importButton = app.buttons["editor.import-files"]
        if !importButton.exists {
            let create = app.buttons["FullDocumentManagerViewControllerNavigationBarCreateButtonIdentifier"]
            XCTAssertTrue(create.waitForExistence(timeout: 20)); create.tap()
        }
        XCTAssertTrue(importButton.waitForExistence(timeout: 20)); importButton.tap()
        print("VISION_FILES_PICKER_AX " + app.debugDescription)
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
        XCTAssertTrue(text.waitForExistence(timeout: 10)); text.tap(); text.typeText("Vision 世界")
        capture(app, name: "vision-imported-editable-bubble")
        app.buttons["editor.export"].tap()
        let png = app.buttons["PNG…"]; XCTAssertTrue(png.waitForExistence(timeout: 10)); png.tap()
        print("VISION_EXPORT_PICKER_AX " + app.debugDescription)
        let save = app.buttons.matching(NSPredicate(format: "label == 'Export' OR label == 'Save' OR label == 'Move'")).firstMatch
        XCTAssertTrue(save.waitForExistence(timeout: 15)); save.tap()
        let verified = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Exported and verified '")).firstMatch
        let completed = verified.waitForExistence(timeout: 20)
        if !completed { capture(app, name: "vision-export-readback-failure"); print("VISION_EXPORT_RESULT_AX " + app.debugDescription) }
        XCTAssertTrue(completed)
        capture(app, name: "vision-png-export-verified")
        if #available(visionOS 27.0, *) { try app.performAccessibilityAudit(for: .all) }
    }
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
