import XCTest
import UIKit
import CryptoKit

final class NativeTVUITests: XCTestCase {
    private var failClosedInterruption: NSObjectProtocol?
    override func setUpWithError() throws {
        try super.setUpWithError()
        // Install before every launch. Known consent/dialog controls are handled
        // explicitly by the test; every otherwise-unhandled interruption stops
        // this process without returning to XCTest's default auto-handler.
        failClosedInterruption = addUIInterruptionMonitor(withDescription: "Abort every unhandled native system interruption") { _ in
            // No UI query, XCTest failure recorder or throwable callback work:
            // none may fail and fall through to another monitor/default action.
            print("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=tv")
            fatalError("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT platform=tv; unexpected interruption; no alert action taken")
        }
    }
    override func tearDownWithError() throws {
        defer {
            if let monitor = failClosedInterruption { removeUIInterruptionMonitor(monitor) }
            failClosedInterruption = nil
        }
        // XCTest assertion aborts may bypass a Swift defer. Close the waiting
        // app explicitly so Photos prompts do not hold test-session teardown.
        let app = XCUIApplication()
        if app.state != .notRunning { app.terminate() }
        try super.tearDownWithError()
    }
    @MainActor func testFocusPhotoImportFilterAndVerifiedPhotosSave() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchEnvironment["CELLULOID_TV_OUTPUT_PROOF"] = "YES"
        app.launch(); defer { app.terminate() }
        try select(app.buttons["tv.choose-photos"], in: app)
        print("TV_PHOTOS_AFTER_SELECT_AX " + app.debugDescription)
        let system = XCUIApplication(bundleIdentifier: "com.apple.PineBoard")
        let allow = system.buttons["Allow All Photos"].firstMatch
        if allow.waitForExistence(timeout: 8) {
            let namesThisApp = system.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Celluloid'")).firstMatch
            XCTAssertTrue(namesThisApp.exists, "Only approve this disposable app's synthetic Photos test prompt")
            print("TV_PHOTOS_PERMISSION_AX " + system.debugDescription)
            try select(allow, in: system)
        }
        let photo = try revealPhoto("CelluloidSource-1.png", in: app)
        try select(photo, in: app)
        try select(app.buttons["tv.edit-selected"], in: app)
        XCTAssertTrue(app.images["tv.preview"].waitForExistence(timeout: 15))
        try select(app.buttons["tv.filters"], in: app)
        let panel = app.otherElements["tv.editor.panel"].firstMatch
        XCTAssertTrue(panel.waitForExistence(timeout: 5))
        let done = app.buttons["tv.panel.done"], fade = app.buttons["tv.filter.Fade"]
        print("TV_FOCUS_MINIMAL_FADE panel=\(panel.frame) done=\(done.frame) fade=\(fade.frame)")
        XCTAssertTrue(panel.frame.contains(done.frame), "The fixed Done header must remain inside the actual sheet")
        try focus(fade, in: app)
        XCTAssertTrue(panel.frame.contains(fade.frame), "The actual focused Fade choice must be inside the sheet")
        XCUIRemote.shared.press(.select)
        XCTAssertEqual(app.buttons["tv.filters"].label, "Fade", "The selected non-default filter must reach visible editor state")
        try select(app.buttons["tv.keep-recipe"], in: app)
        try select(app.buttons["tv.save-photos"], in: app)
        XCTAssertTrue(app.staticTexts["Saved to Photos and verified by reading the image back."].waitForExistence(timeout: 30))
        let jpeg = try XCTUnwrap(app.screenshot().image.jpegData(compressionQuality: 0.55))
        XCTAssertLessThanOrEqual(jpeg.count, 2_000_000)
        let shot = XCTAttachment(data: jpeg, uniformTypeIdentifier: "public.jpeg"); shot.name = "native-tv-photos-export-verified"; shot.lifetime = .keepAlways; add(shot)
        print("TV_NATIVE_PHOTOS_E2E real focus/import/Photos-write-refetch completed; independent requested-filter oracle runs on host")
        if #available(tvOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
        // The kept recipe must restore the chosen state after actual process relaunch.
        app.terminate(); app.launch()
        try select(app.buttons["tv.reopen-recipe"], in: app)
        XCTAssertTrue(app.staticTexts["Editable recipe reopened from Photos sources."].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["tv.filters"].label, "Fade")
        try select(app.buttons["tv.filters"], in: app)
        try select(app.buttons["tv.filter.Chrome"], in: app)
        XCTAssertEqual(app.buttons["tv.filters"].label, "Chrome")
        try select(app.buttons["tv.save-photos"], in: app)
        XCTAssertTrue(app.staticTexts["Saved to Photos and verified by reading the image back."].waitForExistence(timeout: 30))
        print("TV_NATIVE_RELAUNCH_CHANGED_FILTER actual saved Fade restore then second Chrome save completed")
    }
    @MainActor func testRemoteCollageTwoSources() throws { try collage(count:2) }
    @MainActor func testRemoteCollageThreeSources() throws { try collage(count:3) }
    @MainActor func testRemoteCollageFourSources() throws { try collage(count:4) }
    @MainActor func testSimplifiedChinesePhotoFilterReopenAndLargeText() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); defer { app.terminate() }
        var ordinaryHeight: CGFloat = 0
        for large in [false, true] {
            if app.state != .notRunning { app.terminate() }
            app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-UIPreferredContentSizeCategoryName",
                                   large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch()
            let choose = app.buttons["tv.choose-photos"]
            XCTAssertTrue(choose.waitForExistence(timeout: 15)); XCTAssertEqual(choose.label, "选择照片")
            let instruction = app.staticTexts["选择一张照片进行编辑，或选择 2–4 张制作拼图。"]
            XCTAssertTrue(instruction.exists); let height = instruction.frame.height
            if large {
                continueAfterFailure = true
                XCTAssertGreaterThan(height, ordinaryHeight, "A large-text argument alone does not establish actual TV typography coverage")
                continueAfterFailure = false
            } else { ordinaryHeight = height }
            try select(choose, in: app)
            let system = XCUIApplication(bundleIdentifier: "com.apple.PineBoard")
            let allow = system.buttons.matching(NSPredicate(format: "label == 'Allow All Photos' OR label == '允许访问所有照片' OR label == '允许所有照片'")).firstMatch
            if allow.waitForExistence(timeout: 4) {
                XCTAssertTrue(system.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Celluloid'")).firstMatch.exists)
                print("TV_ZH_HANS_PERMISSION_AX " + String(system.debugDescription.prefix(16000)))
                try select(allow, in: system)
            }
            if large { try panelDiagnostic(app, state: "large-text-photos", image: true) }
            let photo = try revealPhoto("CelluloidSource-1.png", in: app)
            try select(photo, in: app); try select(app.buttons["tv.edit-selected"], in: app)
            XCTAssertTrue(app.images["tv.preview"].waitForExistence(timeout: 20))
            XCTAssertEqual(app.buttons["tv.filters"].label, "原片")
            try select(app.buttons["tv.filters"], in: app)
            XCTAssertEqual(app.buttons["tv.filter.Fade"].label, "褪色")
            try select(app.buttons["tv.filter.Fade"], in: app)
            XCTAssertEqual(app.buttons["tv.filters"].label, "褪色")
            XCTAssertEqual(app.buttons["tv.keep-recipe"].label, "保留可编辑记录")
            try select(app.buttons["tv.keep-recipe"], in: app)
            app.terminate(); app.launch()
            try select(app.buttons["tv.reopen-recipe"], in: app)
            XCTAssertTrue(app.staticTexts["已通过照片图库中的原图重新打开可编辑记录。"].waitForExistence(timeout: 20))
            XCTAssertEqual(app.buttons["tv.filters"].label, "褪色")
            try focus(app.buttons["tv.filters"], in: app)
            let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = large ? "native-tv-zh-Hans-large-reopened" : "native-tv-zh-Hans-reopened"; shot.lifetime = .keepAlways; add(shot)
            print("TV_ZH_HANS_REOPEN requestedLarge=\(large) instructionHeight=\(height) ordinaryHeight=\(ordinaryHeight) localized filter persisted")
            if #available(tvOS 27.0, *) {
                let previous = continueAfterFailure; continueAfterFailure = true
                defer { continueAfterFailure = previous }
                try app.performAccessibilityAudit(for: .all) { issue in
                print("NATIVE_ACCESSIBILITY_ISSUE state=tv-zh-Hans requestedLarge=\(large) description=\(issue.compactDescription) element=\(issue.element?.debugDescription ?? "none")"); return false
                }
            }
        }
    }
    @MainActor func testTVKeyboardAutomationAvailability() throws {
        #if !CELLULOID_TV_TYPETEXT_SUPPORTED
        throw XCTSkip("The exact SDK did not expose typeText for tvOS; remote-only multilingual keyboard entry remains an explicit open gate")
        #endif
    }
    @MainActor private func collage(count:Int) throws {
        continueAfterFailure = false
        let app = XCUIApplication();app.launchArguments = ["-AppleLanguages","(en)","-AppleLocale","en_US"]
        app.launchEnvironment["CELLULOID_TV_COMPOSITION_PROOF"] = String(count)
        app.launch(); defer { app.terminate() }
        try select(app.buttons["tv.choose-photos"],in:app)
        let system = XCUIApplication(bundleIdentifier:"com.apple.PineBoard")
        let allow = system.buttons["Allow All Photos"].firstMatch
        if allow.waitForExistence(timeout:4) {
            XCTAssertTrue(system.staticTexts.matching(NSPredicate(format:"label CONTAINS 'Celluloid'")).firstMatch.exists)
            try select(allow,in:system)
        }
        var intended: [[String:String]] = []
        for (order,index) in Array((0..<count).reversed()).enumerated() {
            let filename = "CelluloidSource-\(index+1).png"
            let target = try revealPhoto(filename, in: app)
            let identifier = String(target.identifier.dropFirst("tv.photo.".count))
            XCTAssertFalse(identifier.isEmpty); intended.append(["assetID":identifier,"filename":filename])
            try select(target,in:app)
            XCTAssertEqual(target.value as? String,"Selected \(order+1)")
        }
        XCTAssertEqual(Set(intended.compactMap { $0["assetID"] }).count,count)
        try select(app.buttons["tv.edit-selected"],in:app)
        XCTAssertTrue(app.images["tv.preview"].waitForExistence(timeout:20))
        try select(app.buttons["tv.sources"],in:app)
        let template = [2:"compose_2_2",3:"compose_3_10_1s",4:"compose_4_10"][count]!
        try select(app.buttons["tv.template."+template],in:app)
        try select(app.buttons["tv.source.0.zoom.increase"],in:app)
        try select(app.buttons["tv.source.0.zoom.increase"],in:app)
        try select(app.buttons["tv.source.0.crop-x.decrease"],in:app)
        try select(app.buttons["tv.source.0.crop-y.increase"],in:app)
        try select(app.buttons["tv.source.0.later"],in:app)
        try select(app.buttons["tv.panel.done"],in:app)
        try select(app.buttons["tv.stickers"],in:app)
        if count == 4 {
            try focus(app.buttons["tv.asset.32"], in: app)
            try revealArtwork("54", initiallyDown: true, in: app)
            try focus(app.buttons["tv.asset.54"], in: app)
            try revealArtwork("32", initiallyDown: false, in: app)
        }
        try select(app.buttons["tv.asset.32"],in:app)
        for _ in 0..<12 { try select(app.buttons["tv.layer.x.decrease"],in:app) }
        try select(app.buttons["tv.layer.mirror"],in:app)
        XCTAssertEqual(app.buttons["tv.layer.mirror"].value as? String, "On")
        try select(app.buttons["tv.panel.done"],in:app)
        try select(app.buttons["tv.bubbles"],in:app)
        try panelDiagnostic(app, state: "bubbles-after-layers-\(count)", image: count == 4)
        try select(app.buttons["tv.asset.say1"],in:app)
        let field = app.textFields["tv.bubble-text"]
        XCTAssertTrue(field.waitForExistence(timeout:10))
        var text = "Hello", keyboard = false
        #if CELLULOID_TV_TYPETEXT_SUPPORTED
        if #available(tvOS 27.0, *) {
            try select(field,in:app)
            print("TV_NATIVE_KEYBOARD_AX " + String(app.debugDescription.prefix(24000)))
            app.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:5))
            app.typeText("T"); app.typeText("V")
            XCUIRemote.shared.press(.menu)
            XCTAssertTrue(field.waitForExistence(timeout:10));XCTAssertEqual(field.value as? String,"TV")
            print("TV_NATIVE_KEYBOARD_ASCII actual system keyboard committed TV from two ordinary key events")
            text = "TV"; keyboard = true
            // The two-source end-to-end case retains ASCII through recipe
            // relaunch/export even if a separate Unicode keyboard case fails.
            if count > 2 {
                try select(field,in:app)
                app.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:2)+"TV 世界")
                XCUIRemote.shared.press(.menu)
                XCTAssertTrue(field.waitForExistence(timeout:10));XCTAssertEqual(field.value as? String,"TV 世界")
                print("TV_NATIVE_KEYBOARD_UNICODE actual system keyboard committed full multilingual text")
                text = "TV 世界"
            }
        }
        #endif
        try select(app.buttons["tv.layer.rotation.increase"],in:app)
        try select(app.buttons["tv.panel.done"],in:app)
        try select(app.buttons["tv.undo"],in:app) // Undo exactly the final rotation, retaining text and both layers.
        try select(app.buttons["tv.keep-recipe"],in:app)
        app.terminate();app.launch()
        try select(app.buttons["tv.reopen-recipe"],in:app)
        XCTAssertTrue(app.staticTexts["Editable recipe reopened from Photos sources."].waitForExistence(timeout:20))
        try select(app.buttons["tv.save-photos"],in:app)
        XCTAssertTrue(app.staticTexts["Saved to Photos and verified by reading the image back."].waitForExistence(timeout:30))
        try focus(app.buttons["tv.filters"],in:app) // Clean visible top control, without opening another sheet.
        let jpeg = try XCTUnwrap(app.screenshot().image.jpegData(compressionQuality:0.45));XCTAssertLessThanOrEqual(jpeg.count,1_500_000)
        let capture = XCTAttachment(data:jpeg,uniformTypeIdentifier:"public.jpeg");capture.name = "native-tv-collage-\(count)-photos-output";capture.lifetime = .keepAlways;add(capture)
        let expected: [String:Any] = ["count":count,"initialSources":intended,"template":template,"bubbleText":text,"keyboardExercised":keyboard]
        let encoded = try JSONSerialization.data(withJSONObject:expected,options:[.sortedKeys])
        print("TV_NATIVE_COMPOSITION_EXPECTED " + String(decoding:encoded,as:UTF8.self))
        if #available(tvOS 27.0, *) { try app.performAccessibilityAudit(for:.all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE state=tv-collage-\(count) description=\(issue.compactDescription) element=\(issue.element?.debugDescription ?? "none")");return false
        } }
    }
    private static var diagnosticImages = Set<String>()
    @MainActor private func panelDiagnostic(_ app: XCUIApplication, state: String, image: Bool) throws {
        let panel = app.otherElements["tv.editor.panel"].firstMatch
        let presented = panel.waitForExistence(timeout: 5)
        let focused = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
        print("TV_NATIVE_PANEL_DIAGNOSTIC state=\(state) presented=\(presented) panelLabel=\(presented ? panel.label : "missing") panelFrame=\(presented ? String(describing: panel.frame) : "missing") focused=\(focused.exists ? focused.identifier : "missing")")
        print("TV_NATIVE_PANEL_DIAGNOSTIC_AX state=\(state) " + String(app.debugDescription.prefix(18000)))
        guard image, Self.diagnosticImages.count < 2, Self.diagnosticImages.insert(state).inserted else { return }
        // Exactly two named synthetic checkpoints, bounded before stdout. The
        // existing NATIVE_ log selector retains this ordinary screenshot envelope
        // even if Xcode never finalizes the failed result bundle. Artifact caps
        // remain unchanged; no script change or unbounded screenshot loop.
        let screenshot = app.screenshot().image
        let ratio = min(1, 960 / max(screenshot.size.width, screenshot.size.height))
        let size = CGSize(width: (screenshot.size.width * ratio).rounded(), height: (screenshot.size.height * ratio).rounded())
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
        let resized = UIGraphicsImageRenderer(size: size, format: format).image { _ in screenshot.draw(in: CGRect(origin: .zero, size: size)) }
        let jpeg = try XCTUnwrap(resized.jpegData(compressionQuality: 0.22))
        guard jpeg.count <= 80_000 else {
            print("TV_NATIVE_PANEL_IMAGE_OMITTED state=\(state) bytes=\(jpeg.count) limit=80000"); return
        }
        let metadata: [String: Any] = ["name": state, "bytes": jpeg.count, "width": Int(size.width), "height": Int(size.height),
                                       "sha256": SHA256.hash(data: jpeg).map { String(format: "%02x", $0) }.joined()]
        let json = try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys])
        print("NATIVE_SCREENSHOT_BEGIN:" + state)
        print("NATIVE_SCREENSHOT_META " + String(decoding: json, as: UTF8.self))
        let encoded = Array(jpeg.base64EncodedString())
        for start in stride(from: 0, to: encoded.count, by: 1024) {
            print("NATIVE_SCREENSHOT_CHUNK:" + String(encoded[start..<min(start + 1024, encoded.count)]))
        }
        print("NATIVE_SCREENSHOT_END:" + state)
    }
    @MainActor private func revealArtwork(_ id: String, initiallyDown: Bool, in app: XCUIApplication) throws {
        let target = app.buttons["tv.asset." + id]
        for down in [initiallyDown, !initiallyDown] {
            for step in 0..<16 {
                if target.exists { return }
                let focused = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
                if focused.exists {
                    print("TV_ARTWORK_REVEAL target=\(id) step=\(step) direction=\(down ? "down" : "up") focused=\(focused.identifier) frame=\(focused.frame)")
                }
                XCUIRemote.shared.press(down ? .down : .up)
            }
        }
        print("TV_ARTWORK_REVEAL_FAILURE " + String(app.debugDescription.prefix(24000)))
        XCTFail("The known artwork asset was not reachable by the real remote: " + id)
    }
    @MainActor private func revealPhoto(_ filename: String, in app: XCUIApplication) throws -> XCUIElement {
        // LazyVGrid only exposes materialized rows. Search by the known synthetic
        // filename while genuinely scrolling; never substitute the first asset.
        let target = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'tv.photo.' AND label BEGINSWITH %@", filename + ",")).firstMatch
        let anyPhoto = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'tv.photo.'")).firstMatch
        XCTAssertTrue(anyPhoto.waitForExistence(timeout: 15), "The real Photos sheet must expose at least one imported asset")
        for direction in ["down", "up"] {
            for step in 0..<16 {
                if target.exists { return target }
                let focused = app.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
                if focused.exists {
                    print("TV_PHOTO_REVEAL filename=\(filename) direction=\(direction) step=\(step) focused=\(focused.identifier) label=\(focused.label) frame=\(focused.frame)")
                } else { print("TV_PHOTO_REVEAL filename=\(filename) direction=\(direction) step=\(step) focused=none") }
                if direction == "down" { XCUIRemote.shared.press(.down) } else { XCUIRemote.shared.press(.up) }
            }
        }
        print("TV_PHOTOS_IMPORT_FAILURE_AX " + app.debugDescription)
        let state = XCTAttachment(screenshot: app.screenshot()); state.name = "tv-photos-import-failure"; state.lifetime = .keepAlways; add(state)
        XCTFail("Known synthetic source was not reachable in the real Photos picker: " + filename)
        return target
    }
    @MainActor private func select(_ target: XCUIElement, in app: XCUIApplication) throws {
        try focus(target,in:app); XCUIRemote.shared.press(.select)
    }
    @MainActor private func assertFocusedControlFitsSheet(_ target: XCUIElement, in app: XCUIApplication) {
        let panel = app.otherElements["tv.editor.panel"].firstMatch
        guard panel.exists else { return }
        print("TV_FOCUS_CONTAINMENT target=\(target.identifier) frame=\(target.frame) sheet=\(panel.frame)")
        XCTAssertTrue(panel.frame.contains(target.frame), "A real focused sheet control must remain within the presented sheet")
    }
    @MainActor private func focus(_ target: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let remote = XCUIRemote.shared
        var attempted: [String: Set<String>] = [:]
        for attempt in 0..<60 {
            if target.hasFocus { assertFocusedControlFitsSheet(target, in: app); return }
            let button = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let focused = button.exists ? button : app.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let destination = target.frame, current = focused.frame
                // PineBoard exposes the focused inner button and outer query with
                // identical title and geometry. Match that exact visible choice.
                if focused.label == target.label && abs(destination.midX-current.midX) < 1 && abs(destination.midY-current.midY) < 1 && abs(destination.width-current.width) < 1 && abs(destination.height-current.height) < 1 {
                    assertFocusedControlFitsSheet(target, in: app); return
                }
                let state = focused.identifier.isEmpty ? focused.label : focused.identifier
                let vertical = destination.midY >= current.midY ? "down" : "up"
                let horizontal = destination.midX >= current.midX ? "right" : "left"
                let preferred = destination.minY >= current.maxY || destination.maxY <= current.minY ? [vertical,horizontal] : [horizontal,vertical]
                let directions = preferred + [horizontal == "right" ? "left" : "right", vertical == "down" ? "up" : "down"]
                let tried = attempted[state, default: []]
                let next = directions.first(where: { !tried.contains($0) }) ?? directions[0]
                if tried.count == 4 { attempted[state] = [] }
                attempted[state, default: []].insert(next)
                print("TV_FOCUS_STEP target=\(target.identifier) attempt=\(attempt) focused=\(state) frame=\(current) destination=\(destination) direction=\(next)")
                switch next { case "up": remote.press(.up); case "down": remote.press(.down); case "left": remote.press(.left); default: remote.press(.right) }
            } else { print("TV_FOCUS_STEP target=\(target.identifier) attempt=\(attempt) focused=none destination=\(target.frame) direction=down"); remote.press(.down) }
        }
        print("TV_FOCUS_FAILURE_AX " + app.debugDescription)
        XCTFail("Could not focus target through actual remote navigation: " + target.identifier)
    }
}
