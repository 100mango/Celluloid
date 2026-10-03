import XCTest

final class NativeTVUITests: XCTestCase {
    @MainActor func testFocusPhotoImportFilterAndVerifiedPhotosSave() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch(); defer { app.terminate() }
        try select(app.buttons["tv.choose-photos"], in: app)
        let alert = app.alerts.firstMatch
        if alert.waitForExistence(timeout: 4) {
            print("TV_PHOTOS_PERMISSION_AX " + alert.debugDescription)
            let allow = alert.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Allow' AND NOT label CONTAINS[c] 'Don’t' AND NOT label CONTAINS[c] 'Do Not'")).firstMatch
            XCTAssertTrue(allow.exists, "Inspect actual authorization options before adapting")
            try select(allow, in: app)
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
        if #available(tvOS 27.0, *) { try app.performAccessibilityAudit(for: .all) }
    }
    @MainActor private func select(_ target: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let remote = XCUIRemote.shared
        for _ in 0..<30 {
            if target.hasFocus { remote.press(.select); return }
            let focused = app.descendants(matching: .any).matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.exists {
                let deltaX = target.frame.midX - focused.frame.midX
                let deltaY = target.frame.midY - focused.frame.midY
                if abs(deltaY) > 25 { remote.press(deltaY > 0 ? .down : .up) }
                else { remote.press(deltaX > 0 ? .right : .left) }
            } else { remote.press(.down) }
        }
        print("TV_FOCUS_FAILURE_AX " + app.debugDescription)
        XCTFail("Could not focus target through actual remote navigation: " + target.identifier)
    }
}
