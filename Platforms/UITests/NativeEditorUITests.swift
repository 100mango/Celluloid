import XCTest
import AppKit
import CoreGraphics
import CelluloidDomain
import CelluloidRendering

final class NativeEditorUITests: XCTestCase {
    @MainActor func testExactAppLaunchImportEditAndResize() throws {
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let expected = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
        let app = XCUIApplication(url: expected)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        if ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" { app.launchEnvironment["CELLULOID_SANDBOX_DIAGNOSTICS"] = "YES" }
        try launch(app); defer { app.terminate() }
        let candidates = NSRunningApplication.runningApplications(withBundleIdentifier: "Mango.Celluloid")
        let actual = try XCTUnwrap(candidates.first { $0.bundleURL?.standardizedFileURL.resolvingSymlinksInPath().path == expected.path })
        XCTAssertEqual(actual.bundleURL?.standardizedFileURL.resolvingSymlinksInPath().path, expected.path)
        XCTAssertEqual(actual.executableURL?.standardizedFileURL.resolvingSymlinksInPath().path, expected.appendingPathComponent("Contents/MacOS/CelluloidMac").path)
        print("CELLULOID_UI_LAUNCH expected=\(expected.path) actual=\(actual.bundleURL!.path) executable=\(actual.executableURL!.path) pid=\(actual.processIdentifier)")
        let startupCancel = app.windows["open-panel"].buttons["CancelButton"]
        if startupCancel.waitForExistence(timeout: 3) { startupCancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let importButton = app.descendants(matching: .any)["editor.import-files"].firstMatch
        XCTAssertTrue(importButton.waitForExistence(timeout: 10))
        try assertSandboxIfRequested(app)
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        importButton.click()
        app.typeKey("g", modifierFlags: [.command, .shift])
        let pathField = app.windows.textFields.firstMatch
        XCTAssertTrue(pathField.waitForExistence(timeout: 5))
        pathField.typeText(fixture.path); app.typeKey(.return, modifierFlags: [])
        let open = app.windows.buttons["OKButton"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5)); open.click()
        let imported = app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 10)
        if !imported {
            print("IMPORT_FAILURE_AX " + app.debugDescription)
            let state = XCTAttachment(screenshot: app.screenshot()); state.name = "import-dimension-failure"; state.lifetime = .keepAlways; add(state)
        }
        XCTAssertTrue(imported)
        let bubble = app.descendants(matching: .any)["editor.add-bubble"].firstMatch
        XCTAssertTrue(bubble.isHittable); bubble.click()
        let palette = XCTAttachment(screenshot: app.screenshot()); palette.name = "native-mac-visual-bubble-picker"; palette.lifetime = .keepAlways; add(palette)
        let say1 = app.buttons["asset.say1"]
        XCTAssertTrue(say1.waitForExistence(timeout: 5)); say1.click()
        let text = app.descendants(matching: .any)["editor.bubble-text"].firstMatch
        XCTAssertTrue(text.waitForExistence(timeout: 5)); text.click()
        app.typeKey("a", modifierFlags: .command); text.typeText("Hello 世界")
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = "native-mac-imported-bubble"; screenshot.lifetime = .keepAlways; add(screenshot)
        let window = app.windows.firstMatch
        XCTAssertGreaterThanOrEqual(window.frame.width, 640)
        // Native resize from the actual window's observed bottom-right corner.
        let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 1)).withOffset(CGVector(dx: -3, dy: -3))
        corner.click(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: 180, dy: 120)))
        XCTAssertTrue(importButton.isHittable); XCTAssertTrue(text.isHittable)
        let resized = XCTAttachment(screenshot: app.screenshot()); resized.name = "native-mac-resized"; resized.lifetime = .keepAlways; add(resized)
        // Closing an edited untitled document must offer saving or canceling.
        app.typeKey("w", modifierFlags: .command)
        let closeCancel = app.windows.buttons["Cancel"].firstMatch
        XCTAssertTrue(closeCancel.waitForExistence(timeout: 5))
        closeCancel.click()
        XCTAssertTrue(text.waitForExistence(timeout: 5))
    }
    @MainActor func testSaveReopenAndVerifiedPNGJPEGExport() throws {
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path))
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        if ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" { app.launchEnvironment["CELLULOID_SANDBOX_DIAGNOSTICS"] = "YES" }
        try launch(app); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]
        if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let importButton = app.descendants(matching: .any)["editor.import-files"].firstMatch
        XCTAssertTrue(importButton.waitForExistence(timeout: 10))
        try assertSandboxIfRequested(app)
        let fixture = try makeFixture(), folder = fixture.deletingLastPathComponent()
        defer { try? FileManager.default.removeItem(at: folder) }
        importButton.click(); try goTo(fixture, in: app)
        let open = app.windows.buttons["OKButton"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5)); open.click()
        XCTAssertTrue(app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 10))
        app.descendants(matching: .any)["editor.add-bubble"].firstMatch.click()
        let bubble = app.buttons["asset.say1"]
        XCTAssertTrue(bubble.waitForExistence(timeout: 5)); bubble.click()
        let text = app.descendants(matching: .any)["editor.bubble-text"].firstMatch
        XCTAssertTrue(text.waitForExistence(timeout: 5)); text.click()
        app.typeKey("a", modifierFlags: .command); text.typeText("Saved 世界")
        app.typeKey("s", modifierFlags: .command)
        try save(in: folder, app: app)
        let documentURL = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil).first { $0.pathExtension == "celluloid" })
        let saved = try EditRecipe.decode(Data(contentsOf: documentURL.appendingPathComponent("recipe.json")))
        XCTAssertEqual(saved.overlays.first?.text, "Saved 世界")
        XCTAssertEqual(saved.sources.count, 1)
        XCTAssertEqual(try Data(contentsOf: documentURL.appendingPathComponent(saved.sources[0].filename)), try Data(contentsOf: fixture))
        app.typeKey("w", modifierFlags: .command)
        app.typeKey("o", modifierFlags: .command); try goTo(documentURL, in: app)
        let reopen = app.windows.buttons["OKButton"].firstMatch
        XCTAssertTrue(reopen.waitForExistence(timeout: 5)); reopen.click()
        let layerID = try XCTUnwrap(saved.overlays.first?.id.uuidString)
        let restoredLayer = app.buttons["layer." + layerID]
        XCTAssertTrue(restoredLayer.waitForExistence(timeout: 10)); restoredLayer.click()
        let restoredText = app.descendants(matching: .any)["editor.bubble-text"].firstMatch
        XCTAssertTrue(restoredText.waitForExistence(timeout: 5))
        XCTAssertEqual(restoredText.value as? String, "Saved 世界")
        for menuTitle in ["PNG…", "JPEG…"] {
            let menu = app.descendants(matching: .any)["editor.export"].firstMatch
            XCTAssertTrue(menu.waitForExistence(timeout: 5))
            expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: menu)
            waitForExpectations(timeout: 10); menu.click()
            app.menuItems[menuTitle].click(); try save(in: folder, app: app)
            let allowed = menuTitle == "PNG…" ? ["png"] : ["jpg", "jpeg"]
            let exported = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil).first { $0.lastPathComponent != fixture.lastPathComponent && allowed.contains($0.pathExtension.lowercased()) })
            let metadata = try RasterCodec.metadata(Data(contentsOf: exported))
            XCTAssertEqual(metadata.pixelWidth, 1200); XCTAssertEqual(metadata.pixelHeight, 800)
            XCTAssertTrue(app.staticTexts["Exported and verified " + exported.lastPathComponent].waitForExistence(timeout: 5))
            print("NATIVE_UI_EXPORT_VERIFIED type=\(menuTitle) path=\(exported.path) dimensions=1200x800")
        }
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = "native-mac-saved-reopened-exported"; screenshot.lifetime = .keepAlways; add(screenshot)
    }
    @MainActor func testAccessibilityOfNativeEmptyEditor() throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] != "YES" else { throw XCTSkip("The audit runs on the ordinary UI lane without the debug sandbox diagnostic overlay") }
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path)); app.launch(); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]; if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let control = app.descendants(matching: .any)["editor.import-files"].firstMatch
        XCTAssertTrue(control.waitForExistence(timeout: 10)); XCTAssertTrue(control.isHittable)
        if #available(macOS 27.0, *) { try app.performAccessibilityAudit(for: .all) }
    }
    @MainActor private func launch(_ app: XCUIApplication) throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" else { app.launch(); return }
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.arguments = app.launchArguments + ["--celluloid-sandbox-diagnostics"]
        configuration.environment = app.launchEnvironment
        configuration.createsNewApplicationInstance = true
        let opened = expectation(description: "Ordinary sandbox app launch without XCTest library injection")
        var launchError: Error?
        NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: path), configuration: configuration) { _, error in
            launchError = error; opened.fulfill()
        }
        wait(for: [opened], timeout: 15)
        if let launchError { throw launchError }
        // XCUIApplication is only an external accessibility client for this running process.
    }
    @MainActor private func assertSandboxIfRequested(_ app: XCUIApplication) throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" else { return }
        let probe = app.descendants(matching: .any)["sandbox.probe"].firstMatch
        let found = probe.waitForExistence(timeout: 10)
        if !found {
            print("NATIVE_SANDBOX_MISSING_PROBE_AX " + app.debugDescription)
            let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "sandbox-probe-missing"; shot.lifetime = .keepAlways; add(shot)
        }
        XCTAssertTrue(found)
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(probe.label.utf8)) as? [String: Any])
        XCTAssertEqual(value["passed"] as? Bool, true, probe.label)
        print("NATIVE_SANDBOX_RUNTIME " + probe.label)
    }
    @MainActor private func goTo(_ url: URL, in app: XCUIApplication) throws {
        app.typeKey("g", modifierFlags: [.command, .shift])
        // The Go To Folder control can be a combo box; the Save As text field
        // remains in the hierarchy behind it. Send text to the app’s focused control.
        app.typeKey("a", modifierFlags: .command); app.typeText(url.path)
        app.typeKey(.return, modifierFlags: [])
    }
    @MainActor private func save(in folder: URL, app: XCUIApplication) throws {
        let saveButton = app.windows.buttons["OKButton"].firstMatch
        let presented = saveButton.waitForExistence(timeout: 10)
        if !presented {
            print("EXPORT_PANEL_AX " + app.debugDescription)
            let state = XCTAttachment(screenshot: app.screenshot()); state.name = "missing-export-panel"; state.lifetime = .keepAlways; add(state)
        }
        XCTAssertTrue(presented)
        print("NATIVE_SAVE_PANEL prompt=\(saveButton.label)")
        try goTo(folder, in: app)
        XCTAssertTrue(saveButton.isEnabled); saveButton.click()
        let closed = NSPredicate(format: "exists == false")
        expectation(for: closed, evaluatedWith: saveButton)
        waitForExpectations(timeout: 10)
    }
    @MainActor func testSimplifiedChineseEditorAndVisualPicker() throws {
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path))
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-ApplePersistenceIgnoreState", "YES"]
        if ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" { app.launchEnvironment["CELLULOID_SANDBOX_DIAGNOSTICS"] = "YES" }
        try launch(app); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]
        if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let importButton = app.descendants(matching: .any)["editor.import-files"].firstMatch
        XCTAssertTrue(importButton.waitForExistence(timeout: 10))
        try assertSandboxIfRequested(app)
        XCTAssertTrue(app.staticTexts["原生照片编辑器"].exists)
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        importButton.click(); app.typeKey("g", modifierFlags: [.command, .shift])
        let field = app.windows.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5)); field.typeText(fixture.path)
        app.typeKey(.return, modifierFlags: [])
        let open = app.windows.buttons["OKButton"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5)); open.click()
        let imported = app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 10)
        if !imported {
            print("IMPORT_FAILURE_AX " + app.debugDescription)
            let state = XCTAttachment(screenshot: app.screenshot()); state.name = "import-dimension-failure"; state.lifetime = .keepAlways; add(state)
        }
        XCTAssertTrue(imported)
        app.descendants(matching: .any)["editor.add-bubble"].firstMatch.click()
        XCTAssertTrue(app.buttons["asset.say1"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["选择气泡"].exists)
        XCTAssertEqual(app.buttons["asset.say1"].label, "对话 1")
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = "native-mac-zh-Hans-visual-picker"; screenshot.lifetime = .keepAlways; add(screenshot)
    }
    private func makeFixture() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("CelluloidUI-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let context = try RasterCodec.bitmap(width: 1200, height: 800)
        context.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [0.1, 0.6, 0.9, 1])))
        context.fill(CGRect(x: 0, y: 0, width: 1200, height: 800))
        let url = folder.appendingPathComponent("Synthetic.png")
        try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png).write(to: url, options: .atomic)
        return url
    }
}
