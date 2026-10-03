import XCTest

final class NativeWatchUITests: XCTestCase {
    @MainActor func testNativeOfflineGalleryControlsAndPrivacy() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)"]
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.descendants(matching: .any)["watch.import-photo"].firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.descendants(matching: .any)["watch.import-photo"].firstMatch.isHittable)
        let photo = app.descendants(matching: .any)["watch.photo.A2E0E7B0-0A3B-47D3-94E5-309F3614E54A"].firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 10)); photo.tap()
        XCTAssertTrue(app.images["watch.preview"].waitForExistence(timeout: 10))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "native-watch-offline-photo"; shot.lifetime = .keepAlways; add(shot)
        print("WATCH_NATIVE_UI_AX " + app.debugDescription)
        if #available(watchOS 27.0, *) { try app.performAccessibilityAudit(for: .all) }
        // Real system Photos selection and paired-phone file transport are separate gates.
    }
    func testSystemPhotosPickerReportsSimulatorLimitationAndCloses() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-AppleLanguages", "(en)"]
        app.launch(); defer { app.terminate() }
        let picker = app.descendants(matching: .any)["watch.import-photo"].firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 20)); picker.tap()
        let unavailable = app.staticTexts["Unable to Load Photos in Simulator"]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["You need to use an Apple Watch."].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "watch-system-photos-simulator-limitation"; shot.lifetime = .keepAlways; add(shot)
        let close = app.buttons["Close"]; XCTAssertTrue(close.isHittable); close.tap()
        XCTAssertTrue(picker.waitForExistence(timeout: 10))
        print("WATCH_NATIVE_PICKER_LIMITATION system PhotosPicker reports physical Apple Watch required; no import-success claim")
    }

}
