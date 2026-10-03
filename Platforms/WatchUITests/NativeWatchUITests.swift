import XCTest

final class NativeWatchUITests: XCTestCase {
    func testNativeOfflineGalleryControlsAndPrivacy() {
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
        // Real system Photos selection and paired-phone file transport are separate gates.
    }
}
