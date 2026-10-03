import XCTest

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
        let photo = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'tv.photo.'")).firstMatch
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
        try select(app.buttons["tv.keep-recipe"], in: app)
        try select(app.buttons["tv.save-photos"], in: app)
        XCTAssertTrue(app.staticTexts["Saved to Photos and verified by reading the image back."].waitForExistence(timeout: 30))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-tv-photos-export-verified"; shot.lifetime = .keepAlways; add(shot)
        print("TV_NATIVE_PHOTOS_E2E real focus/import/filter/Photos-write-refetch proof completed")
        if #available(tvOS 27.0, *) { try app.performAccessibilityAudit(for: .all) { issue in
            print("NATIVE_ACCESSIBILITY_ISSUE description=\(issue.compactDescription) detail=\(issue.detailedDescription) element=\(issue.element?.debugDescription ?? "none")")
            return false // Report every real issue; this callback suppresses nothing.
        } }
    }
    @MainActor private func select(_ target: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let remote = XCUIRemote.shared
        var attempted: [String: Set<String>] = [:]
        for _ in 0..<60 {
            if target.hasFocus { remote.press(.select); return }
            let button = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
            let focused = button.exists ? button : app.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let destination = target.frame, current = focused.frame
                // PineBoard exposes the focused inner button and outer query with
                // identical title and geometry. Match that exact visible choice.
                if focused.label == target.label && abs(destination.midX-current.midX) < 1 && abs(destination.midY-current.midY) < 1 && abs(destination.width-current.width) < 1 && abs(destination.height-current.height) < 1 {
                    remote.press(.select); return
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
