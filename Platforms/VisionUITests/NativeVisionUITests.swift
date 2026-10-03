import XCTest

final class NativeVisionUITests: XCTestCase {
    func testNativeDocumentBrowserLaunchAndNewDocument() {
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
    }
}
