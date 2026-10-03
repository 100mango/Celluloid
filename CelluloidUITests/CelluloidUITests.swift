import XCTest
import UIKit
import CryptoKit

final class CelluloidUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUp() { super.setUp(); continueAfterFailure = false; app = XCUIApplication() }
    override func tearDown() { XCUIDevice.shared.orientation = .portrait; app.terminate(); super.tearDown() }
    private func launch(_ arguments: [String] = [], language: String = "en") {
        app.launchArguments = arguments + ["-AppleLanguages", "(\(language))", "-AppleLocale", language == "zh-Hans" ? "zh_CN" : "en_US"]
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 10))
    }
    func testHomeChoiceGeometryInEnglishAndChineseAcrossRotation() {
        for language in ["en", "zh-Hans"] {
            var normalFooterHeight: CGFloat = 0
            for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
                XCUIDevice.shared.orientation = .portrait
                launch(["-UIPreferredContentSizeCategoryName", category.rawValue], language: language)
                let initialFooterHeight = app.buttons["privacy-policy"].frame.height
                if category == .large { normalFooterHeight = initialFooterHeight }
                else { XCTAssertGreaterThan(initialFooterHeight, normalFooterHeight, "The largest text setting must actually affect the app") }
                for orientation in [UIDeviceOrientation.portrait, .landscapeLeft] {
                    XCUIDevice.shared.orientation = orientation
                    let edit = app.buttons["edit-photo"]
                    let collage = app.buttons["make-collage"]
                    let footer = app.buttons["privacy-policy"]
                    XCTAssertTrue(edit.isHittable && collage.isHittable && footer.isHittable)
                    XCTAssertGreaterThanOrEqual(edit.frame.height, 120)
                    XCTAssertGreaterThanOrEqual(collage.frame.height, 120)
                    XCTAssertFalse(edit.frame.intersects(collage.frame), "Primary choices must not collapse together")
                    XCTAssertGreaterThanOrEqual(footer.frame.minY + 1, max(edit.frame.maxY, collage.frame.maxY))
                    XCTAssertLessThan(footer.frame.height, app.frame.height * 0.40)
                }
                app.terminate()
            }
        }
    }

    func testPrivacyPolicyEntryRemainsAccessibleAndCanClose() {
        launch()
        let policy = app.buttons["privacy-policy"]
        XCTAssertTrue(policy.isHittable)
        XCTAssertEqual(policy.label, "Privacy Policy")
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(policy.isHittable)
        policy.tap()
        // The browser's Close action is available even when external networking is offline.
        let close = app.buttons["Close"]
        let visible = close.waitForExistence(timeout: 15)
        if !visible {
            print("PRIVACY_ACCESSIBILITY_BEGIN")
            print(String(app.debugDescription.prefix(18000)))
            print("PRIVACY_ACCESSIBILITY_END")
        }
        XCTAssertTrue(visible, "The policy browser must provide its explicit Close control")
        close.tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
        XCTAssertTrue(policy.isHittable)
    }

    func testDeniedPhotosShowsRecoveryAndCanCancelRepeatedly() {
        launch(["--photos-denied"])
        for _ in 0..<2 {
            app.buttons["edit-photo"].tap()
            let state = app.staticTexts["photos-state"]
            XCTAssertTrue(state.waitForExistence(timeout: 5))
            XCTAssertTrue(state.label.contains("Settings"))
            XCTAssertFalse(app.buttons["picker-done"].isEnabled)
            app.buttons["Cancel"].tap()
            XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
        }
    }
    func testLimitedEmptyPhotosHasManagementAndAdaptiveLayout() {
        launch(["--photos-limited-empty"])
        app.buttons["make-collage"].tap()
        XCTAssertTrue(app.buttons["manage-photos"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["photos-state"].label.contains("No photos"))
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(app.buttons["Cancel"].isHittable)
        app.buttons["Cancel"].tap()
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }
    func testSeededPhotoEditingSaveAndReopen() {
        launch()
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 15), "CI must seed Photos and grant simulator Photos permission")
        app.descendants(matching: .any)["photo-0"].tap()
        app.buttons["picker-done"].tap()
        let done = app.buttons["editor-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 15))
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: done)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        app.buttons["tool-filter"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.element(boundBy: 1).tap()
        // Picker selection dismisses its sheet; the editor should survive backgrounding.
        if app.buttons["Cancel"].exists && !done.isHittable { app.buttons["Cancel"].tap() }
        app.buttons["tool-sticker"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        app.buttons["tool-bubble"].tap()
        XCTAssertTrue(app.collectionViews.cells.firstMatch.waitForExistence(timeout: 5))
        app.collectionViews.cells.firstMatch.tap()
        let text = app.textViews["bubble-text"]
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        text.tap()
        text.typeText("Hello")
        app.buttons["bubble-text-done"].tap()
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        let bubble = app.images.matching(identifier: "attachment-image").allElementsBoundByIndex.last
        if let bubble = bubble, bubble.isHittable {
            let start = bubble.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            start.press(forDuration: 0.2, thenDragTo: start.withOffset(CGVector(dx: 100, dy: 30)))
        }
        emitScreenshot("edited-fixture")
        XCUIDevice.shared.press(.home)
        app.activate()
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        XCUIDevice.shared.orientation = .landscapeLeft
        let shareDone = app.buttons["share-done"]
        XCTAssertTrue(shareDone.isHittable, "Saved-photo dismissal must remain visible in compact landscape")
        XCTAssertTrue(app.frame.contains(shareDone.frame))
        shareDone.tap()
        XCUIDevice.shared.orientation = .portrait
        app.buttons["edit-photo"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-0"].waitForExistence(timeout: 10))
        app.descendants(matching: .any)["photo-0"].tap()
        app.buttons["picker-done"].tap()
        XCTAssertTrue(app.buttons["editor-done"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["tool-bubble"].isHittable)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 5))
    }
    func testTwoPhotoCollageZoomRotateAndSave() {
        launch()
        app.buttons["make-collage"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["photo-1"].waitForExistence(timeout: 15))
        app.descendants(matching: .any)["photo-0"].tap()
        app.descendants(matching: .any)["photo-1"].tap()
        app.buttons["picker-done"].tap()
        let done = app.buttons["collage-done"]
        XCTAssertTrue(done.waitForExistence(timeout: 10))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: done)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        let image = app.scrollViews["collage-image"].firstMatch
        XCTAssertTrue(image.waitForExistence(timeout: 5))
        image.pinch(withScale: 1.5, velocity: 1)
        image.swipeLeft()
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(done.isHittable)
        XCUIDevice.shared.orientation = .portrait
        emitScreenshot("collage-preview")
        done.tap()
        XCTAssertTrue(app.staticTexts["photo-saved"].waitForExistence(timeout: 20))
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(app.buttons["share-done"].isHittable)
        app.buttons["share-done"].tap()
        XCTAssertTrue(app.buttons["make-collage"].waitForExistence(timeout: 5))
    }

    private func emitScreenshot(_ name: String) {
        // Two bounded screenshots per CI job, from the iPhone run and synthetic data only.
        guard UIDevice.current.userInterfaceIdiom == .phone,
              UIScreen.main.bounds.width < 400,
              UIScreen.main.traitCollection.userInterfaceStyle == .dark,
              let image = UIImage(data: app.screenshot().pngRepresentation),
              let jpeg = image.jpegData(compressionQuality: 0.55), jpeg.count <= 500_000 else { return }
        let base64 = jpeg.base64EncodedString()
        print("SCREENSHOT_BEGIN:\(name)")
        var index = base64.startIndex
        while index < base64.endIndex {
            let end = base64.index(index, offsetBy: 4000, limitedBy: base64.endIndex) ?? base64.endIndex
            print(String(base64[index..<end]))
            index = end
        }
        print("SCREENSHOT_END:\(name)")
    }

}


// Isolated App Store capture suite. The shipping app and Release settings are unchanged.
final class CelluloidCaptureTests: XCTestCase {
    private var app = XCUIApplication()
    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
    }
    override func tearDown() { app.terminate(); super.tearDown() }

    private func launchChinese() {
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        XCTAssertTrue(app.buttons["edit-photo"].waitForExistence(timeout: 15))
    }
    private func ready(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        let predicate = NSPredicate(format: "enabled == true AND hittable == true")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: element)], timeout: 15), .completed)
    }
    func testStoreScreenshots() throws {
        launchChinese()
        for (identifier, label) in [("edit-photo", "美化"), ("make-collage", "拼图"), ("privacy-policy", "隐私政策")] {
            XCTAssertEqual(app.buttons[identifier].label, label)
            XCTAssertTrue(app.buttons[identifier].isHittable)
        }
        let editFrame = app.buttons["edit-photo"].frame
        let collageFrame = app.buttons["make-collage"].frame
        let footerFrame = app.buttons["privacy-policy"].frame
        XCTAssertGreaterThanOrEqual(editFrame.height, 120)
        XCTAssertGreaterThanOrEqual(collageFrame.height, 120)
        XCTAssertFalse(editFrame.intersects(collageFrame), "Primary home choices must not overlap")
        XCTAssertGreaterThanOrEqual(footerFrame.minY + 1, max(editFrame.maxY, collageFrame.maxY))
        XCTAssertLessThan(footerFrame.height, app.frame.height * 0.40)
        XCTAssertTrue(app.frame.contains(editFrame) && app.frame.contains(collageFrame) && app.frame.contains(footerFrame))
        print("STORE_HOME_GEOMETRY edit=\(editFrame) collage=\(collageFrame) footer=\(footerFrame)")
        try emitStoreScreenshot("01-home")

        app.buttons["edit-photo"].tap()
        let photo = app.descendants(matching: .any)["photo-0"]
        ready(photo); photo.tap()
        app.buttons["picker-done"].tap()
        let editDone = app.buttons["editor-done"]
        ready(editDone)
        app.buttons["tool-filter"].tap()
        ready(app.collectionViews.cells.element(boundBy: 1))
        app.collectionViews.cells.element(boundBy: 1).tap()
        if app.buttons["取消"].exists && !editDone.isHittable { app.buttons["取消"].tap() }
        app.buttons["tool-sticker"].tap()
        ready(app.collectionViews.cells.firstMatch)
        app.collectionViews.cells.firstMatch.tap()
        ready(editDone)
        XCTAssertTrue(app.buttons["tool-filter"].isHittable)
        XCTAssertTrue(app.buttons["tool-sticker"].isHittable)
        try emitStoreScreenshot("02-edited-fixture")
        app.buttons["取消"].tap()
        ready(app.buttons["make-collage"])

        app.buttons["make-collage"].tap()
        ready(app.descendants(matching: .any)["photo-1"])
        app.descendants(matching: .any)["photo-0"].tap()
        app.descendants(matching: .any)["photo-1"].tap()
        app.buttons["picker-done"].tap()
        ready(app.buttons["collage-done"])
        XCTAssertTrue(app.scrollViews["collage-image"].firstMatch.waitForExistence(timeout: 5))
        try emitStoreScreenshot("03-collage")
    }

    private func emitStoreScreenshot(_ screen: String) throws {
        XCTAssertFalse(app.alerts.firstMatch.exists, "No permission or error prompt may cover a store capture")
        Thread.sleep(forTimeInterval: 1)
        let capture = XCUIScreen.main.screenshot()
        let image = capture.image
        let pixels = try XCTUnwrap(image.cgImage)
        let width = pixels.width, height = pixels.height
        let isPhone = UIDevice.current.userInterfaceIdiom == .phone
        let accepted = isPhone ? [(1260,2736),(1290,2796),(1320,2868)] : [(2064,2752),(2048,2732)]
        XCTAssertTrue(accepted.contains { $0.0 == width && $0.1 == height }, "Unaccepted native pixels \(width)x\(height)")
        // Encoding only: no resize, cropping, drawing, retouching, or overlays.
        // JPEG has no alpha. Fail visibly if an acceptable-quality native file cannot fit the approved bridge.
        var data: Data?
        var quality: CGFloat = 1
        for q in [CGFloat(1), 0.95, 0.90, 0.85, 0.80] {
            if let candidate = image.jpegData(compressionQuality: q), candidate.count <= 786432 {
                data = candidate; quality = q; break
            }
        }
        let jpeg = try XCTUnwrap(data, "Native capture exceeds 786432-byte bridge at quality >=0.80; request approved artifact bridge")
        let name = "celluloid-zh-Hans-\(isPhone ? "iphone-6.9" : "ipad-13")-\(screen).jpg"
        let hash = SHA256.hash(data: jpeg).map { String(format: "%02x", $0) }.joined()
        print("CELLULOID_STORE_META name=\(name) width=\(width) height=\(height) bytes=\(jpeg.count) sha256=\(hash) quality=\(quality) source=XCUIScreen.main configuration=Release")
        print("CELLULOID_STORE_BEGIN:\(name)")
        let base64 = jpeg.base64EncodedString()
        var index = base64.startIndex
        while index < base64.endIndex {
            let end = base64.index(index, offsetBy: 4000, limitedBy: base64.endIndex) ?? base64.endIndex
            print(String(base64[index..<end])); index = end
        }
        print("CELLULOID_STORE_END:\(name)")
    }

    func testPhotosHostAssessment() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        let photos = XCUIApplication(bundleIdentifier: "com.apple.mobileslideshow")
        photos.launchArguments = ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        photos.launch()
        Thread.sleep(forTimeInterval: 3)
        func hierarchy(_ stage: String) {
            print("PHOTOS_HOST_HIERARCHY_BEGIN:\(stage)")
            print(String(photos.debugDescription.prefix(24000)))
            print("PHOTOS_HOST_HIERARCHY_END:\(stage)")
        }
        func tapLabel(_ labels: [String]) -> Bool {
            for label in labels {
                let control = photos.buttons[label].firstMatch
                if control.exists && control.isHittable { control.tap(); return true }
            }
            return false
        }
        hierarchy("launch")
        _ = tapLabel(["图库", "Library", "所有照片", "All Photos"])
        // In the observed iOS 27 host, Library presents What's New after launch.
        // Wait for that actual sheet instead of probing too early and leaving it over the grid.
        let welcomeContinue = photos.buttons["继续"].firstMatch
        let welcomeTitle = photos.staticTexts["“照片”新功能"].firstMatch
        if welcomeContinue.waitForExistence(timeout: 10) {
            guard welcomeTitle.exists else {
                hierarchy("unexpected-continue-screen")
                print("PHOTOS_HOST_RESULT:BLOCKED Continue exists outside the observed What's New sheet; no account or permission dialog accepted")
                return
            }
            let tappable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "hittable == true"), object: welcomeContinue)
            guard XCTWaiter.wait(for: [tappable], timeout: 10) == .completed else {
                hierarchy("welcome-not-hittable")
                print("PHOTOS_HOST_RESULT:BLOCKED observed Photos welcome Continue never became hittable")
                return
            }
            welcomeContinue.tap()
            let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: welcomeContinue)
            guard XCTWaiter.wait(for: [dismissed], timeout: 10) == .completed else {
                hierarchy("welcome-not-dismissed")
                print("PHOTOS_HOST_RESULT:BLOCKED observed Photos welcome remained after Continue")
                return
            }
        }
        let welcomeGone = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            !welcomeTitle.exists && !welcomeContinue.exists
        }, object: nil)
        guard XCTWaiter.wait(for: [welcomeGone], timeout: 10) == .completed else {
            hierarchy("welcome-still-present")
            print("PHOTOS_HOST_RESULT:BLOCKED actual What's New title or Continue still exists; fixture selection withheld")
            return
        }
        let lastGridImage = photos.images.matching(identifier: "PXGGridLayout-Info").element(boundBy: max(0, photos.images.matching(identifier: "PXGGridLayout-Info").count - 1))
        let gridReady = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND hittable == true"), object: lastGridImage)
        guard XCTWaiter.wait(for: [gridReady], timeout: 10) == .completed else {
            hierarchy("grid-not-ready")
            print("PHOTOS_HOST_RESULT:BLOCKED observed Photos grid not ready after welcome handling")
            return
        }
        hierarchy("library")
        // Observed iOS 27 Photos hierarchy exposes Images, not CollectionView Cells.
        // Six simulator stock images predate the two fixtures added during this job.
        let images = photos.images.matching(identifier: "PXGGridLayout-Info").allElementsBoundByIndex.filter { $0.exists && $0.isHittable }
        print("PHOTOS_HOST_GRID_LABELS: " + images.map { $0.label }.joined(separator: " | "))
        let latest = Array(images.suffix(2))
        let today = Calendar.current.dateComponents([.month, .day], from: Date())
        let datePattern = "\\b\(today.month!)月0?\(today.day!)日"
        guard latest.count == 2,
              latest.allSatisfy({ $0.label.range(of: datePattern, options: .regularExpression) != nil }),
              let fixture = latest.last else {
            print("PHOTOS_HOST_RESULT:BLOCKED latest two accessible Photos grid images cannot be verified as today's seeded fixtures")
            return
        }
        guard !welcomeTitle.exists && !welcomeContinue.exists && fixture.isHittable else {
            hierarchy("fixture-not-ready")
            print("PHOTOS_HOST_RESULT:BLOCKED identified synthetic fixture is not hittable after confirmed welcome dismissal")
            return
        }
        print("PHOTOS_HOST_READY welcomeTitleExists=false continueExists=false syntheticFixtureHittable=true")
        print("PHOTOS_HOST_SELECTED_SEEDED_FIXTURE: " + fixture.label)
        fixture.tap()
        Thread.sleep(forTimeInterval: 2)
        hierarchy("selected-photo")
        guard tapLabel(["编辑", "Edit"]) else {
            print("PHOTOS_HOST_RESULT:BLOCKED selected Photos content exposes no accessible Edit action")
            return
        }
        Thread.sleep(forTimeInterval: 2)
        hierarchy("editing")
        _ = tapLabel(["更多", "More", "扩展", "Extensions", "更多选项", "More options"])
        Thread.sleep(forTimeInterval: 2)
        hierarchy("extensions")
        guard tapLabel(["CelluloidPhotoExtension", "Celluloid"]) else {
            print("PHOTOS_HOST_RESULT:BLOCKED Photos Edit does not expose accessible Celluloid extension after bounded normal UI attempt")
            return
        }
        Thread.sleep(forTimeInterval: 3)
        hierarchy("celluloid")
        let filter = photos.buttons["tool-filter"]
        guard filter.exists && filter.isHittable else {
            print("PHOTOS_HOST_RESULT:BLOCKED extension entry selected but Celluloid editor not accessible")
            return
        }
        filter.tap()
        let preset = photos.collectionViews.cells.element(boundBy: 1)
        guard preset.waitForExistence(timeout: 5) && preset.isHittable else {
            print("PHOTOS_HOST_RESULT:BLOCKED extension filter selector not accessible")
            return
        }
        preset.tap()
        Thread.sleep(forTimeInterval: 2)
        hierarchy("filtered")
        guard tapLabel(["完成", "Done"]) else {
            print("PHOTOS_HOST_RESULT:BLOCKED no accessible extension completion action")
            return
        }
        Thread.sleep(forTimeInterval: 3)
        hierarchy("rendered")
        _ = tapLabel(["完成", "Done"])
        Thread.sleep(forTimeInterval: 2)
        hierarchy("saved")
        guard tapLabel(["编辑", "Edit"]) else {
            print("PHOTOS_HOST_RESULT:PARTIAL extension rendering attempted; save/reopen not established")
            return
        }
        Thread.sleep(forTimeInterval: 2)
        _ = tapLabel(["更多", "More", "扩展", "Extensions", "更多选项", "More options"])
        Thread.sleep(forTimeInterval: 2)
        guard tapLabel(["CelluloidPhotoExtension", "Celluloid"]) else {
            hierarchy("reopen-blocked")
            print("PHOTOS_HOST_RESULT:PARTIAL editing reopened but extension state restoration not established")
            return
        }
        Thread.sleep(forTimeInterval: 3)
        hierarchy("reopened")
        guard photos.buttons["tool-filter"].exists && photos.buttons["tool-filter"].isHittable else {
            print("PHOTOS_HOST_RESULT:PARTIAL extension action selected during reopen but editor presence not established")
            return
        }
        print("PHOTOS_HOST_RESULT:REOPENED extension UI reopened through actual Photos; adjustment/pixel integrity requires separate visual review")
    }
}
