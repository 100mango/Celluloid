import XCTest
import Foundation
@testable import CelluloidMac

final class LaunchProvenanceTests: XCTestCase {
    func testNativeBundlePackagesEnglishAndChineseStrings() throws {
        XCTAssertTrue(Bundle.main.localizations.contains("en"))
        XCTAssertTrue(Bundle.main.localizations.contains("zh-Hans"))
        let url = try XCTUnwrap(Bundle.main.url(forResource: "Localizable", withExtension: "strings", subdirectory: nil, localization: "zh-Hans"))
        let chinese = try XCTUnwrap(Bundle(url: url.deletingLastPathComponent()))
        XCTAssertEqual(chinese.localizedString(forKey: "Native photo editor", value: nil, table: nil), "原生照片编辑器")
        print("NATIVE_BUNDLE_LOCALIZATIONS languages=\(Bundle.main.localizations) chinese_table=\(url.path)")
    }

    func testActualHostedAppIsTheExpectedDebugProduct() throws {
        let expected = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_EXPECTED_APP_PATH"],
                                     "The scheme must pass the exact expected built-product path")
        let expectedURL = URL(fileURLWithPath: expected).standardizedFileURL.resolvingSymlinksInPath()
        let actualURL = Bundle.main.bundleURL.standardizedFileURL.resolvingSymlinksInPath()
        let executable = try XCTUnwrap(Bundle.main.executableURL).standardizedFileURL.resolvingSymlinksInPath()
        XCTAssertEqual(actualURL.path, expectedURL.path)
        XCTAssertEqual(executable.path, expectedURL.appendingPathComponent("Contents/MacOS/CelluloidMac").path)
        XCTAssertTrue(actualURL.path.contains("/Debug/"))
        XCTAssertEqual(Bundle.main.bundleIdentifier, "Mango.Celluloid")
        print("CELLULOID_LAUNCH_PROVENANCE expected=\(expectedURL.path) actual=\(actualURL.path) executable=\(executable.path) process=\(ProcessInfo.processInfo.arguments.first ?? "")")
    }
}
