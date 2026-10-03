import XCTest
import AppKit
import CoreGraphics
import CoreImage
import ApplicationServices
import CryptoKit
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
        XCTAssertTrue(say1.waitForExistence(timeout: 5)); try auditOrdinary(app, state: "bubble-picker"); say1.click()
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
        try auditOrdinary(app, state: "edited-multilingual-resized")
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
        app.launchEnvironment["CELLULOID_UNDO_DIAGNOSTICS"] = "YES"
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
        // Invoke the real document shortcut while text input is still focused;
        // the production transform command must relinquish that text responder.
        XCTAssertEqual(text.value as? String, "Saved 世界")
        let modelLayer = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'layer.'")).firstMatch
        print("NATIVE_MAC_TEXT_BEFORE_TRANSFORM field=\(text.value ?? "missing") modelLayer=\(modelLayer.label)")
        app.typeKey(.rightArrow, modifierFlags: [.command, .option])
        let horizontal = app.staticTexts["editor.layer.value.Horizontal position"]
        expectation(for: NSPredicate(format: "value == '0.51'"), evaluatedWith: horizontal)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        XCTAssertEqual(modelLayer.label, "Select layer: Saved 世界")
        // Undo the first transform before any second command can hide a late
        // native text commit. Both Unicode and unchanged rotation must survive.
        let firstRotation = app.staticTexts["editor.layer.value.Rotation"]
        XCTAssertEqual(firstRotation.value as? String, "0.00")
        app.typeKey("z", modifierFlags: .command)
        expectation(for: NSPredicate(format: "value == '0.50'"), evaluatedWith: horizontal)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        XCTAssertEqual(modelLayer.label, "Select layer: Saved 世界")
        XCTAssertEqual(firstRotation.value as? String, "0.00")
        app.typeKey("z", modifierFlags: [.command, .shift])
        expectation(for: NSPredicate(format: "value == '0.51'"), evaluatedWith: horizontal)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        XCTAssertEqual(modelLayer.label, "Select layer: Saved 世界")
        XCTAssertEqual(firstRotation.value as? String, "0.00")
        print("NATIVE_MAC_FIRST_TRANSFORM_UNDO_REDO exact Unicode and geometry verified")
        app.typeKey("]", modifierFlags: [.command, .option])
        let rotation = app.staticTexts["editor.layer.value.Rotation"]
        expectation(for: NSPredicate(format: "value == '15.00'"), evaluatedWith: rotation)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        app.typeKey("z", modifierFlags: .command)
        print("NATIVE_MAC_KEYBOARD_UNDO_RESULT rotation=\(rotation.value ?? "missing") horizontal=\(horizontal.value ?? "missing") text=\(text.value ?? "missing")")
        let undoShot = XCTAttachment(screenshot: app.screenshot()); undoShot.name = "native-mac-keyboard-undo-result"; undoShot.lifetime = .keepAlways; add(undoShot)
        app.menuBarItems["Edit"].click()
        print("NATIVE_MAC_KEYBOARD_UNDO_EDIT_MENU " + String(app.menus.debugDescription.prefix(20000)))
        app.typeKey(.escape, modifierFlags: [])
        expectation(for: NSPredicate(format: "value == '0.00'"), evaluatedWith: rotation)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        app.typeKey("z", modifierFlags: [.command, .shift])
        expectation(for: NSPredicate(format: "value == '15.00'"), evaluatedWith: rotation)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(text.value as? String, "Saved 世界")
        print("NATIVE_MAC_KEYBOARD_TRANSFORMS actual nudge/rotate/Undo/Redo exact text and geometry verified")
        app.typeKey("s", modifierFlags: .command)
        try save(in: folder, app: app)
        let documentURL = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil).first { $0.pathExtension == "celluloid" })
        let savedBytes = try Data(contentsOf: documentURL.appendingPathComponent("recipe.json"))
        let saved = try EditRecipe.decode(savedBytes)
        XCTAssertLessThanOrEqual(savedBytes.count, 8192)
        print("NATIVE_UI_SAVED_RECIPE sha256=\(SHA256.hash(data: savedBytes).map { String(format: "%02x", $0) }.joined()) json=\(String(decoding: savedBytes, as: UTF8.self))")
        XCTAssertEqual(saved.overlays.first?.text, "Saved 世界")
        XCTAssertEqual(try XCTUnwrap(saved.overlays.first?.centerX), 0.51, accuracy: 0.000_001)
        XCTAssertEqual(try XCTUnwrap(saved.overlays.first?.rotation), 15, accuracy: 0.000_001)
        XCTAssertEqual(saved.sources.count, 1)
        XCTAssertEqual(try Data(contentsOf: documentURL.appendingPathComponent(saved.sources[0].filename)), try Data(contentsOf: fixture))
        app.typeKey("w", modifierFlags: .command)
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: modelLayer)
        waitForExpectations(timeout: 5)
        XCTAssertFalse(app.windows.buttons["Cancel"].firstMatch.exists, "Saved document must actually close without an unsaved-changes sheet")
        print("NATIVE_MAC_SAVED_DOCUMENT_CLOSED layer absent before genuine Open")
        app.typeKey("o", modifierFlags: .command); try goTo(documentURL, in: app)
        let reopen = app.windows.buttons["OKButton"].firstMatch
        XCTAssertTrue(reopen.waitForExistence(timeout: 5)); reopen.click()
        let layerID = try XCTUnwrap(saved.overlays.first?.id.uuidString)
        let restoredLayer = app.buttons["layer." + layerID]
        XCTAssertTrue(restoredLayer.waitForExistence(timeout: 10)); restoredLayer.click()
        let restoredText = app.descendants(matching: .any)["editor.bubble-text"].firstMatch
        XCTAssertTrue(restoredText.waitForExistence(timeout: 5))
        XCTAssertEqual(restoredText.value as? String, "Saved 世界")
        XCTAssertEqual(app.staticTexts["editor.layer.value.Horizontal position"].value as? String, "0.51")
        XCTAssertEqual(app.staticTexts["editor.layer.value.Rotation"].value as? String, "15.00")
        XCTAssertEqual(restoredLayer.label, "Select layer: Saved 世界")
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
    @MainActor func testRealClipboardPasteUndoRedoAndRejectedReplacement() throws {
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path))
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        if ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" { app.launchEnvironment["CELLULOID_SANDBOX_DIAGNOSTICS"] = "YES" }
        try launch(app); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]
        if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        XCTAssertTrue(app.descendants(matching: .any)["editor.import-files"].firstMatch.waitForExistence(timeout: 10))
        try assertSandboxIfRequested(app)
        let fixture = try makeFixture(); defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        let board = NSPasteboard.general
        board.clearContents(); XCTAssertTrue(board.setData(try Data(contentsOf: fixture), forType: .png))
        defer { board.clearContents() }
        app.typeKey("v", modifierFlags: .command)
        let dimensions = app.staticTexts["1200 × 800 px"]
        XCTAssertTrue(dimensions.waitForExistence(timeout: 10))
        app.typeKey("z", modifierFlags: .command)
        XCTAssertTrue(app.staticTexts["No photos imported"].waitForExistence(timeout: 10))
        app.typeKey("z", modifierFlags: [.command, .shift])
        XCTAssertTrue(dimensions.waitForExistence(timeout: 10))
        board.clearContents(); XCTAssertTrue(board.setData(Data("unreadable synthetic image".utf8), forType: .png))
        app.typeKey("v", modifierFlags: .command)
        // Restrict to real windows: app-wide buttons also includes Touch Bar OK.
        let ok = app.windows.buttons["OK"].firstMatch
        XCTAssertTrue(ok.waitForExistence(timeout: 10))
        print("NATIVE_MODAL_CONTAINMENT dimensionsExposed=\(app.staticTexts["editor.dimensions"].exists) importExposed=\(app.descendants(matching: .any)["editor.import-files"].firstMatch.exists) foregroundOK=\(ok.exists)")
        XCTAssertFalse(app.staticTexts["editor.dimensions"].exists, "Dimmed document content must not remain in the modal accessibility task")
        XCTAssertFalse(app.descendants(matching: .any)["editor.import-files"].firstMatch.exists)
        try auditOrdinary(app, state: "unreadable-image-error"); ok.click()
        XCTAssertTrue(dimensions.exists, "Rejected clipboard replacement must preserve the current original")
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-mac-paste-undo-redo-rejected-replacement"; shot.lifetime = .keepAlways; add(shot)
        print("NATIVE_MAC_CLIPBOARD_E2E actual Paste/Undo/Redo/unreadable rejection preserves original dimensions")
    }
    @MainActor func testRealPhotosLibraryImportAndSystemPicker() throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] == "YES" else { throw XCTSkip("Real local Photos library flow runs once in the sandbox lane") }
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path))
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        app.launchEnvironment["CELLULOID_SANDBOX_DIAGNOSTICS"] = "YES"
        try launch(app); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]
        if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        XCTAssertTrue(app.descendants(matching: .any)["editor.import-files"].firstMatch.waitForExistence(timeout: 10))
        try assertSandboxIfRequested(app)
        let fixture = try makeFixture(); defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        photos.launch(); defer { photos.terminate() }
        // Normal disposable local-library setup only. No account, iCloud, TCC
        // database modification or blanket system permission acceptance.
        if photos.buttons["Get Started"].waitForExistence(timeout: 5) { photos.buttons["Get Started"].click() }
        print("NATIVE_MAC_PHOTOS_INITIAL_AX " + photos.debugDescription)
        let fileMenu = photos.menuBarItems["File"]
        XCTAssertTrue(fileMenu.waitForExistence(timeout: 15)); fileMenu.click()
        let importMenu = photos.menuItems["_NS:1096"] // Exact Import… identifier observed in Photos27.
        XCTAssertTrue(importMenu.exists); XCTAssertTrue(importMenu.isEnabled); importMenu.click()
        photos.typeKey("g", modifierFlags: [.command, .shift])
        photos.typeKey("a", modifierFlags: .command); photos.typeText(fixture.path); photos.typeKey(.return, modifierFlags: [])
        print("NATIVE_MAC_PHOTOS_IMPORT_PANEL_AX " + photos.debugDescription)
        let open = photos.sheets["open-panel"].buttons["OKButton"]
        XCTAssertTrue(open.waitForExistence(timeout: 10)); open.click()
        let review = photos.buttons["Review for Import"]
        if review.waitForExistence(timeout: 3) { review.click() }
        let importAll = photos.buttons["Import All New Photos"]
        // Photos27 imports a single selected PNG directly. A multi-item review
        // can expose Import All; neither route is completion until a real asset exists.
        if importAll.waitForExistence(timeout: 3) { importAll.click() }
        let imported = photos.collectionViews["photos_collection_view"].descendants(matching: .any)["mediaKind_asset"].firstMatch
        XCTAssertTrue(imported.waitForExistence(timeout: 20), photos.debugDescription)
        XCTAssertFalse(photos.sheets["open-panel"].exists)
        let seeded = XCTAttachment(screenshot: photos.screenshot()); seeded.name = "native-mac-photos-library-seeded"; seeded.lifetime = .keepAlways; add(seeded)
        print("NATIVE_MAC_PHOTOS_IMPORTED_AX " + photos.debugDescription)
        app.activate()
        app.descendants(matching: .any)["editor.import-photos"].firstMatch.click()
        print("NATIVE_MAC_PHOTOS_PICKER_AX " + app.debugDescription)
        let image = app.images["PXGGridLayout-Info"].firstMatch
        let found = image.waitForExistence(timeout: 30)
        if !found {
            // Empty app AX is not evidence of empty pixels or an empty library.
            let screen = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screen.name = "native-mac-photos-picker-failure-full-screen"; screen.lifetime = .keepAlways; add(screen)
            print("NATIVE_MAC_PHOTOS_PICKER_FAILURE_AX " + app.debugDescription)
            inspectPhotosHelpers()
        }
        if found {
            image.click()
            let addButton = app.buttons["Add"].firstMatch
            XCTAssertTrue(addButton.waitForExistence(timeout: 10), app.debugDescription); addButton.click()
        } else {
            try selectObservedSyntheticPhoto(in: app)
        }
        XCTAssertTrue(app.staticTexts["1200 × 800 px"].waitForExistence(timeout: 20), app.debugDescription)
        // Persist the actual imported document through the real save panel, then
        // verify its original pixels against the independently seeded PNG.
        app.typeKey("s", modifierFlags: .command)
        try save(in: fixture.deletingLastPathComponent(), app: app)
        let savedURL = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: fixture.deletingLastPathComponent(), includingPropertiesForKeys: nil).first { $0.pathExtension == "celluloid" })
        let recipe = try EditRecipe.decode(Data(contentsOf: savedURL.appendingPathComponent("recipe.json")))
        XCTAssertEqual(recipe.sources.count, 1)
        let owned = try Data(contentsOf: savedURL.appendingPathComponent(recipe.sources[0].filename))
        let decoded = try XCTUnwrap(NSBitmapImageRep(data: owned))
        let original = try XCTUnwrap(NSBitmapImageRep(data: Data(contentsOf: fixture)))
        XCTAssertEqual(decoded.pixelsWide, original.pixelsWide); XCTAssertEqual(decoded.pixelsHigh, original.pixelsHigh)
        for y in stride(from: 0, to: original.pixelsHigh, by: 79) { for x in stride(from: 0, to: original.pixelsWide, by: 119) {
            let expected = try XCTUnwrap(original.colorAt(x: x, y: y)?.usingColorSpace(.sRGB))
            let actual = try XCTUnwrap(decoded.colorAt(x: x, y: y)?.usingColorSpace(.sRGB))
            XCTAssertEqual(actual.redComponent, expected.redComponent, accuracy: 2.0 / 255)
            XCTAssertEqual(actual.greenComponent, expected.greenComponent, accuracy: 2.0 / 255)
            XCTAssertEqual(actual.blueComponent, expected.blueComponent, accuracy: 2.0 / 255)
        } }
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-mac-real-system-photos-import"; shot.lifetime = .keepAlways; add(shot)
        print("NATIVE_MAC_PHOTOS_E2E normal local-library seed and real system picker import completed")
    }
    @MainActor private func selectObservedSyntheticPhoto(in app: XCUIApplication) throws {
        // Photos27's hosted sheet has real pixels but omits its children from the
        // app-scoped AX snapshot. Match only our unique, known synthetic thumbnail
        // in the currently observed sheet. No hard-coded click or private API.
        let sheet = app.sheets.firstMatch
        XCTAssertTrue(sheet.exists)
        let frame = sheet.frame, screen = try XCTUnwrap(NSScreen.main)
        XCTAssertEqual(NSScreen.screens.count, 1, "Visual test requires one observed display")
        let capture = XCUIScreen.main.screenshot()
        let bitmap = try XCTUnwrap(NSBitmapImageRep(data: capture.pngRepresentation))
        XCTAssertLessThanOrEqual(bitmap.pixelsWide * bitmap.pixelsHigh, 4_000_000)
        let source = try XCTUnwrap(CIImage(data: capture.pngRepresentation))
        let read = CIContext(), space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        XCTAssertEqual(source.extent, CGRect(x: 0, y: 0, width: bitmap.pixelsWide, height: bitmap.pixelsHigh))
        let red = CIImage(color: CIColor(red: 1, green: 0, blue: 0)).cropped(to: CGRect(x: 0, y: 0, width: 2, height: 1))
        let blue = CIImage(color: CIColor(red: 0, green: 0, blue: 1)).cropped(to: CGRect(x: 0, y: 1, width: 2, height: 1))
        var calibration = [UInt8](repeating: 0, count: 16)
        calibration.withUnsafeMutableBytes { read.render(blue.composited(over: red), toBitmap: $0.baseAddress!, rowBytes: 8, bounds: CGRect(x: 0, y: 0, width: 2, height: 2), format: .RGBA8, colorSpace: space) }
        let topDown = Array(calibration[0..<4]) == [0, 0, 255, 255]
        XCTAssertTrue(topDown ? Array(calibration[8..<12]) == [255, 0, 0, 255] : Array(calibration[0..<4]) == [255, 0, 0, 255] && Array(calibration[8..<12]) == [0, 0, 255, 255])
        var samples = [UInt8](repeating: 0, count: bitmap.pixelsWide * bitmap.pixelsHigh * 4)
        samples.withUnsafeMutableBytes { read.render(source, toBitmap: $0.baseAddress!, rowBytes: bitmap.pixelsWide * 4, bounds: source.extent, format: .RGBA8, colorSpace: space) }
        // Match screenshot scale to the same XCTest coordinate space as the
        // observed sheet. NSImage/NSScreen point sizes can describe a different
        // backing scale; retain them as diagnostics, not as the click transform.
        let menuFrame = app.menuBars.firstMatch.frame
        XCTAssertEqual(menuFrame.minX, 0, accuracy: 0.1); XCTAssertGreaterThan(menuFrame.width, 0)
        let sx = CGFloat(bitmap.pixelsWide) / menuFrame.width, sy = sx
        let region = CGRect(x: frame.minX + frame.width * 0.24, y: frame.minY + frame.height * 0.20,
                            width: frame.width * 0.72, height: frame.height * 0.67)
        let strideSize = 3, columns = (bitmap.pixelsWide + 2) / 3
        var points = Set<Int>()
        var closest = Double.infinity, closestColor = "none"
        let deadline = Date().addingTimeInterval(8)
        for y in stride(from: max(0, Int(region.minY * sy)), to: min(bitmap.pixelsHigh, Int(region.maxY * sy)), by: strideSize) {
            guard Date() < deadline else { throw NSError(domain: "SyntheticPhotosVisualMatch", code: 1) }
            for x in stride(from: max(0, Int(region.minX * sx)), to: min(bitmap.pixelsWide, Int(region.maxX * sx)), by: strideSize) {
                let row = topDown ? y : bitmap.pixelsHigh - 1 - y, offset = (row * bitmap.pixelsWide + x) * 4
                let r = Double(samples[offset]) / 255, g = Double(samples[offset + 1]) / 255, b = Double(samples[offset + 2]) / 255
                let distance = abs(r - 0.1) + abs(g - 0.6) + abs(b - 0.9)
                if distance < closest { closest = distance; closestColor = "x=\(x) y=\(y) RGB=\(r),\(g),\(b)" }
                if abs(r - 0.1) < 0.055 && abs(g - 0.6) < 0.055 && abs(b - 0.9) < 0.055 {
                    points.insert((y / strideSize) * columns + x / strideSize)
                }
            }
        }
        let matchedPixels = points.count
        var matches: [CGRect] = [], components: [String] = []
        while let first = points.first {
            var queue = [first], index = 0; points.remove(first)
            var minX = first % columns, maxX = minX, minY = first / columns, maxY = minY
            while index < queue.count {
                let current = queue[index]; index += 1
                minX = min(minX, current % columns); maxX = max(maxX, current % columns)
                minY = min(minY, current / columns); maxY = max(maxY, current / columns)
                for next in [current - 1, current + 1, current - columns, current + columns] where points.remove(next) != nil { queue.append(next) }
            }
            let box = CGRect(x: CGFloat(minX * 3) / sx, y: CGFloat(minY * 3) / sy, width: CGFloat((maxX - minX + 1) * 3) / sx, height: CGFloat((maxY - minY + 1) * 3) / sy)
            if queue.count >= 20 && components.count < 8 { components.append("pixels=\(queue.count),box=\(box)") }
            if queue.count >= 200 && (45...180).contains(box.width) && (45...180).contains(box.height) { matches.append(box) }
        }
        print("NATIVE_MAC_PHOTOS_VISUAL_SCAN sheet=\(frame) screen=\(screen.frame) screenshotPoints=\(capture.image.size) menu=\(menuFrame) scale=\(sx) region=\(region) topDown=\(topDown) matchedPixels=\(matchedPixels) components=\(components) closest=\(closestColor)")
        XCTAssertEqual(matches.count, 1, "Exactly one bounded synthetic thumbnail must be observed: \(matches)")
        let match = try XCTUnwrap(matches.first), center = CGPoint(x: match.midX, y: match.midY)
        print("NATIVE_MAC_PHOTOS_VISUAL_MATCH sheet=\(frame) thumbnail=\(match) screenPixels=\(bitmap.pixelsWide)x\(bitmap.pixelsHigh)")
        if AXIsProcessTrusted() {
            let root = AXUIElementCreateSystemWide(); AXUIElementSetMessagingTimeout(root, 0.2)
            var hit: AXUIElement?
            let result = AXUIElementCopyElementAtPosition(root, Float(center.x), Float(center.y), &hit)
            if result == .success, let hit {
                var pid: pid_t = 0; AXUIElementGetPid(hit, &pid)
                var role: CFTypeRef?; AXUIElementCopyAttributeValue(hit, kAXRoleAttribute as CFString, &role)
                print("NATIVE_MAC_PHOTOS_HIT_OWNER pid=\(pid) role=\(String(describing: role))")
            } else { print("NATIVE_MAC_PHOTOS_HIT_OWNER error=\(result.rawValue)") }
        }
        sheet.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: center.x - frame.minX, dy: center.y - frame.minY)).click()
        let selected = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); selected.name = "native-mac-photos-thumbnail-selected"; selected.lifetime = .keepAlways; add(selected)
        // Return invokes the visible system picker's default Add action. A wrong
        // selection cannot pass: the sheet must close and original pixels match.
        app.typeKey(.return, modifierFlags: [])
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: sheet)
        waitForExpectations(timeout: 15)
    }
    @MainActor private func inspectPhotosHelpers() {
        // Read only public AX APIs for actual observed PIDs. A bundle identifier
        // can resolve a different instance or an unavailable XPC app in XCTest.
        // Never prompt for trust or modify TCC if this diagnostic is unavailable.
        let trusted = AXIsProcessTrusted()
        print("NATIVE_MAC_PHOTOS_AX_TRUST \(trusted)")
        let helpers = NSWorkspace.shared.runningApplications.filter {
            ($0.bundleIdentifier?.hasPrefix("com.apple.") == true) &&
            (($0.bundleIdentifier?.localizedCaseInsensitiveContains("photo") == true) ||
             ($0.localizedName?.localizedCaseInsensitiveContains("photo") == true) ||
             ($0.localizedName?.localizedCaseInsensitiveContains("Celluloid") == true))
        }.prefix(12)
        let deadline = Date().addingTimeInterval(5)
        for helper in helpers {
            print("NATIVE_MAC_PHOTOS_HELPER bundle=\(helper.bundleIdentifier ?? "nil") name=\(helper.localizedName ?? "nil") pid=\(helper.processIdentifier) active=\(helper.isActive) hidden=\(helper.isHidden)")
            guard trusted, Date() < deadline else { continue }
            let root = AXUIElementCreateApplication(helper.processIdentifier)
            AXUIElementSetMessagingTimeout(root, 0.2)
            var visited = Set<CFHashCode>(), count = 0
            func read(_ node: AXUIElement, depth: Int) {
                guard depth <= 6, count < 64, Date() < deadline, visited.insert(CFHash(node)).inserted else { return }
                count += 1
                func attribute(_ key: String) -> CFTypeRef? {
                    var value: CFTypeRef?
                    let result = AXUIElementCopyAttributeValue(node, key as CFString, &value)
                    return result == .success ? value : nil
                }
                let keys = [kAXRoleAttribute, kAXSubroleAttribute, kAXTitleAttribute, kAXDescriptionAttribute, kAXIdentifierAttribute]
                let values = keys.map { key in "\(key)=\(String(describing: attribute(key)).prefix(160))" }.joined(separator: " ")
                var actions: CFArray?
                let result = AXUIElementCopyActionNames(node, &actions)
                print("NATIVE_MAC_PHOTOS_PID_AX pid=\(helper.processIdentifier) depth=\(depth) \(values) actions=\(result == .success ? String(describing: actions) : String(result.rawValue))")
                if let children = attribute(kAXChildrenAttribute) as? [AXUIElement] {
                    for child in children.prefix(32) { read(child, depth: depth + 1) }
                }
            }
            read(root, depth: 0)
        }
    }
    @MainActor func testAccessibilityOfNativeEmptyEditor() throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] != "YES" else { throw XCTSkip("The audit runs on the ordinary UI lane without the debug sandbox diagnostic overlay") }
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let report = FileManager.default.temporaryDirectory.appendingPathComponent("Celluloid-AX-" + UUID().uuidString + ".jsonl")
        defer { try? FileManager.default.removeItem(at: report) }
        let app = XCUIApplication(url: URL(fileURLWithPath: path)); app.launchEnvironment["CELLULOID_AX_REPORT"] = report.path
        app.launch(); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]; if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let control = app.descendants(matching: .any)["editor.import-files"].firstMatch
        XCTAssertTrue(control.waitForExistence(timeout: 10)); XCTAssertTrue(control.isHittable)
        if let size = try? report.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 64_000,
           let data = try? String(contentsOf: report, encoding: .utf8) {
            for line in data.split(separator: "\n") { print("NATIVE_APPKIT_AX " + line) }
        } else { print("NATIVE_APPKIT_AX report unavailable; issue.element hierarchy remains required") }
        try auditOrdinary(app, state: "empty-editor")
    }
    @MainActor func testZDiagnosticNativeAppKitAuditControls() throws { try auditControl(mode: "YES", state: "diagnostic-appkit-control") }
    @MainActor func testZDiagnosticNativeSwiftUIAuditControls() throws { try auditControl(mode: "SWIFTUI", state: "diagnostic-swiftui-control") }
    @MainActor private func auditControl(mode: String, state: String) throws {
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] != "YES" else { throw XCTSkip("The isolated diagnostic runs only in the ordinary lane") }
        continueAfterFailure = false
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"])
        let app = XCUIApplication(url: URL(fileURLWithPath: path))
        app.launchEnvironment["CELLULOID_NATIVE_AUDIT_CONTROL"] = mode
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        app.launch(); defer { app.terminate() }
        let cancel = app.windows["open-panel"].buttons["CancelButton"]; if cancel.waitForExistence(timeout: 3) { cancel.click() }
        app.typeKey("n", modifierFlags: .command)
        let action = app.buttons["probe.action"]
        XCTAssertTrue(action.waitForExistence(timeout: 10)); XCTAssertTrue(app.sliders["probe.slider"].exists)
        print("NATIVE_AUDIT_CONTROL_AX " + String(app.debugDescription.prefix(24000)))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-mac-audit-control-" + mode; shot.lifetime = .keepAlways; add(shot)
        try auditOrdinary(app, state: state)
        action.click(); XCTAssertEqual(app.staticTexts["probe.status"].value as? String, "Action completed")
    }
    @MainActor private func auditOrdinary(_ app: XCUIApplication, state: String) throws {
        // The external sandbox lane retains its own real document operations;
        // do not audit the deliberately visible Debug entitlement probe overlay.
        guard ProcessInfo.processInfo.environment["CELLULOID_EXPECT_SANDBOX"] != "YES" else { return }
        if NSWorkspace.shared.frontmostApplication?.bundleIdentifier != "Mango.Celluloid" { app.activate() }
        let front = NSWorkspace.shared.frontmostApplication
        print("NATIVE_AUDIT_FRONTMOST state=\(state) bundle=\(front?.bundleIdentifier ?? "nil") pid=\(front?.processIdentifier ?? 0) appState=\(app.state.rawValue)")
        XCTAssertEqual(front?.bundleIdentifier, "Mango.Celluloid")
        let screen = XCUIScreen.main.screenshot(), bytes = screen.pngRepresentation
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        print("NATIVE_AUDIT_SCREEN state=\(state) sha256=\(digest)")
        let linked = XCTAttachment(data: bytes, uniformTypeIdentifier: "public.png")
        linked.name = "native-mac-audit-state-" + state; linked.lifetime = .keepAlways; add(linked)
        if state == "unreadable-image-error" {
            print("NATIVE_MODAL_WINDOWS_AX " + String(app.windows.debugDescription.prefix(24_000)))
            print("NATIVE_MODAL_DIALOGS_AX " + String(app.dialogs.debugDescription.prefix(12_000)))
            print("NATIVE_MODAL_SHEETS_AX " + String(app.sheets.debugDescription.prefix(12_000)))
        }
        // Record every reported issue in this audit, without turning any of them
        // into an ignore. UI action assertions outside the audit still stop early.
        let previous = continueAfterFailure; continueAfterFailure = true
        defer { continueAfterFailure = previous }
        if #available(macOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE state=\(state) description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false
        } }
        print("NATIVE_ACCESSIBILITY_AUDIT state=\(state) completed")
    }
    @MainActor private func launch(_ app: XCUIApplication) throws {
        // The sandbox Debug app is independently signed with exact source permissions
        // plus get-task-allow only. XCTest supplies arguments through its supported
        // launch service; NSWorkspace drops them when its test-runner caller is sandboxed.
        app.launch()
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
