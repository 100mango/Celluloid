import XCTest
import UIKit

final class NativeTVUITests: XCTestCase {
    override func tearDownWithError() throws {
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
        let photo = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'tv.photo.' AND label BEGINSWITH 'CelluloidSource-1.png,'")).firstMatch
        let found = photo.waitForExistence(timeout: 15)
        if !found {
            print("TV_PHOTOS_IMPORT_FAILURE_AX " + app.debugDescription)
            let state = XCTAttachment(screenshot: app.screenshot()); state.name = "tv-photos-import-failure"; state.lifetime = .keepAlways; add(state)
        }
        XCTAssertTrue(found, "Simulator must contain the seeded synthetic Photos asset")
        try select(photo, in: app)
        try select(app.buttons["tv.edit-selected"], in: app)
        XCTAssertTrue(app.images["tv.preview"].waitForExistence(timeout: 15))
        try select(app.buttons["tv.filters"], in: app)
        try select(app.buttons["tv.filter.Fade"], in: app)
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
            let target = app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH 'tv.photo.' AND label BEGINSWITH %@",filename+",")).firstMatch
            XCTAssertTrue(target.waitForExistence(timeout:15),app.debugDescription)
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
        try select(app.buttons["tv.asset.32"],in:app)
        for _ in 0..<12 { try select(app.buttons["tv.layer.x.decrease"],in:app) }
        try select(app.buttons["tv.layer.mirror"],in:app)
        XCTAssertEqual(app.buttons["tv.layer.mirror"].value as? String, "On")
        try select(app.buttons["tv.panel.done"],in:app)
        try select(app.buttons["tv.bubbles"],in:app)
        try select(app.buttons["tv.asset.say1"],in:app)
        let field = app.textFields["tv.bubble-text"]
        XCTAssertTrue(field.waitForExistence(timeout:10))
        var text = "Hello", keyboard = false
        #if CELLULOID_TV_TYPETEXT_SUPPORTED
        if #available(tvOS 27.0, *) {
            try select(field,in:app)
            print("TV_NATIVE_KEYBOARD_AX " + String(app.debugDescription.prefix(24000)))
            app.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:5)+"TV 世界")
            XCUIRemote.shared.press(.menu)
            XCTAssertTrue(field.waitForExistence(timeout:10));XCTAssertEqual(field.value as? String,"TV 世界")
            text = "TV 世界"; keyboard = true
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
    @MainActor private func select(_ target: XCUIElement, in app: XCUIApplication) throws {
        try focus(target,in:app); XCUIRemote.shared.press(.select)
    }
    @MainActor private func focus(_ target: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let remote = XCUIRemote.shared
        var attempted: [String: Set<String>] = [:]
        for _ in 0..<60 {
            if target.hasFocus { return }
            let button = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let focused = button.exists ? button : app.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let destination = target.frame, current = focused.frame
                // PineBoard exposes the focused inner button and outer query with
                // identical title and geometry. Match that exact visible choice.
                if focused.label == target.label && abs(destination.midX-current.midX) < 1 && abs(destination.midY-current.midY) < 1 && abs(destination.width-current.width) < 1 && abs(destination.height-current.height) < 1 {
                    return
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
                switch next { case "up": remote.press(.up); case "down": remote.press(.down); case "left": remote.press(.left); default: remote.press(.right) }
            } else { remote.press(.down) }
        }
        print("TV_FOCUS_FAILURE_AX " + app.debugDescription)
        XCTFail("Could not focus target through actual remote navigation: " + target.identifier)
    }
}
