import XCTest
import UIKit

/// Geometry/design coverage only. The existing picker-entry gate separately
/// covers Photos presentation timing; these tests never request library access.
final class PhoneEntryDesignUITests: XCTestCase {
    private let app = XCUIApplication()
    private var failClosedMonitor: NSObjectProtocol?

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        failClosedMonitor = installFailClosedSystemAlertMonitor()
    }

    override func tearDown() {
        XCUIDevice.shared.orientation = .portrait
        app.terminate()
        if let monitor = failClosedMonitor { removeUIInterruptionMonitor(monitor) }
        super.tearDown()
    }

    func testOriginalEntranceGeometryInBothLanguagesAndTextSizes() {
        for language in ["en", "zh-Hans"] {
            var normalFooterHeights: [Bool: CGFloat] = [:]
            for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
                XCUIDevice.shared.orientation = .portrait
                app.launchArguments = ["-AppleLanguages", "(\(language))", "-AppleLocale",
                    language == "zh-Hans" ? "zh_CN" : "en_US",
                    "-UIPreferredContentSizeCategoryName", category.rawValue]
                app.launch()
                for orientation in [UIDeviceOrientation.portrait, .landscapeLeft] {
                    XCUIDevice.shared.orientation = orientation
                    assertSettledOriginalGeometry(horizontal: orientation.isLandscape)
                    let footerHeight = app.buttons["privacy-policy"].frame.height
                    if category == .large {
                        normalFooterHeights[orientation.isLandscape] = footerHeight
                    } else if let normal = normalFooterHeights[orientation.isLandscape] {
                        XCTAssertGreaterThan(footerHeight, normal, "Pinned privacy must still accommodate the larger Dynamic Type text")
                    }
                    let capture = XCTAttachment(screenshot: app.screenshot())
                    capture.name = "entrance-design-\(language)-\(category.rawValue)-\(orientation.rawValue)"
                    capture.lifetime = .keepAlways
                    add(capture)
                }
                app.terminate()
            }
        }
    }

    func testPrivacyStaysPinnedAndReturnsToTheSameHome() {
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        assertSettledOriginalGeometry(horizontal: false)
        let before = app.buttons["privacy-policy"].frame
        app.buttons["privacy-policy"].tap()
        XCTAssertTrue(app.buttons["privacy-policy-close"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["privacy-policy-body"].exists)
        XCTAssertEqual(app.webViews.count, 0)
        app.buttons["privacy-policy-close"].tap()
        assertSettledOriginalGeometry(horizontal: false)
        XCTAssertEqual(app.buttons["privacy-policy"].frame.minY, before.minY, accuracy: 1)
    }

    private func assertSettledOriginalGeometry(horizontal: Bool, file: StaticString = #filePath, line: UInt = #line) {
        let names = ["phone-entry-safe-area", "phone-entry-primary-area", "edit-photo", "make-collage", "privacy-policy"]
        var prior: [CGRect] = []
        var frames: [String: CGRect] = [:]
        var stableSince = ProcessInfo.processInfo.systemUptime
        let settled = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            guard let root = try? self.app.snapshot(), (root.frame.width > root.frame.height) == horizontal else { return false }
            func descendants(_ value: XCUIElementSnapshot) -> [XCUIElementSnapshot] {
                [value] + value.children.flatMap { descendants($0) }
            }
            let nodes = descendants(root)
            let current = names.compactMap { name in nodes.first { $0.identifier == name }?.frame }
            guard current.count == names.count, current.allSatisfy({ $0.width > 0 && $0.height > 0 }) else { return false }
            frames = Dictionary(uniqueKeysWithValues: zip(names, current))
            let stable = prior.count == current.count && zip(prior, current).allSatisfy { pair in
                let (old, new) = pair
                return abs(old.minX - new.minX) < 0.5 && abs(old.minY - new.minY) < 0.5 &&
                abs(old.width - new.width) < 0.5 && abs(old.height - new.height) < 0.5
            }
            if stable { return ProcessInfo.processInfo.systemUptime - stableSince >= 0.4 }
            prior = current
            stableSince = ProcessInfo.processInfo.systemUptime
            return false
        }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [settled], timeout: 8), .completed, file: file, line: line)
        guard let safe = frames[names[0]], let main = frames[names[1]], let first = frames[names[2]],
              let second = frames[names[3]], let footer = frames[names[4]] else {
            return XCTFail("Missing public home geometry: " + String(app.debugDescription.prefix(6000)), file: file, line: line)
        }
        XCTAssertEqual(app.scrollViews.count, 0, "The original fixed home must not become a scrolling feed", file: file, line: line)
        XCTAssertTrue(app.buttons["edit-photo"].isHittable && app.buttons["make-collage"].isHittable && app.buttons["privacy-policy"].isHittable,
                      "Both choices and pinned privacy remain reachable without scrolling", file: file, line: line)
        XCTAssertEqual(main.minX, safe.minX, accuracy: 1, file: file, line: line)
        XCTAssertEqual(main.maxX, safe.maxX, accuracy: 1, file: file, line: line)
        XCTAssertEqual(main.minY, safe.minY, accuracy: 1, file: file, line: line)
        XCTAssertEqual(footer.minY - main.maxY, 4, accuracy: 1, file: file, line: line)
        XCTAssertEqual(safe.maxY - footer.maxY, 4, accuracy: 1, file: file, line: line)
        XCTAssertEqual(footer.minX - safe.minX, 16, accuracy: 1, file: file, line: line)
        XCTAssertEqual(safe.maxX - footer.maxX, 16, accuracy: 1, file: file, line: line)
        XCTAssertGreaterThanOrEqual(footer.height, 44, file: file, line: line)
        XCTAssertEqual(first.width, second.width, accuracy: 1, file: file, line: line)
        XCTAssertEqual(first.height, second.height, accuracy: 1, file: file, line: line)
        if horizontal {
            XCTAssertEqual(first.maxX, second.minX, accuracy: 1, file: file, line: line)
            XCTAssertEqual(first.height, main.height, accuracy: 1, file: file, line: line)
        } else {
            XCTAssertEqual(first.maxY, second.minY, accuracy: 1, file: file, line: line)
            XCTAssertEqual(first.width, main.width, accuracy: 1, file: file, line: line)
        }
        print("ENTRANCE_DESIGN_GEOMETRY horizontal=\(horizontal) safe=\(safe) main=\(main) first=\(first) second=\(second) footer=\(footer)")
    }
}
