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
        app.launch(); defer { app.terminate() }
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
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        importButton.click()
        app.typeKey("g", modifierFlags: [.command, .shift])
        let pathField = app.windows.textFields.firstMatch
        XCTAssertTrue(pathField.waitForExistence(timeout: 5))
        pathField.typeText(fixture.path); app.typeKey(.return, modifierFlags: [])
        let open = app.windows.buttons["Open"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5)); open.click()
        XCTAssertTrue(app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 10))
        let bubble = app.descendants(matching: .any)["editor.add-bubble"].firstMatch
        XCTAssertTrue(bubble.isHittable); bubble.click()
        app.menuItems["say1"].click()
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
