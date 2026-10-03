import XCTest
import AppKit
@testable import CelluloidMac

final class NativeBrandAndPrivacyTests: XCTestCase {
    func testOriginalBrandIconIsBundled() throws {
        let icon = try XCTUnwrap(Bundle.main.url(forResource: "AppIcon", withExtension: "icns"))
        XCTAssertNotNil(NSImage(contentsOf: icon))
        XCTAssertEqual(Bundle.main.infoDictionary?["CFBundleIconFile"] as? String, "AppIcon")
    }
    func testOfflinePrivacyUsesRequiredBilingualDeletionAndPermissionText() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "PrivacyPolicy", withExtension: "txt"))
        let policy = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(policy.contains("本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。"))
        XCTAssertTrue(policy.contains("Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings."))
        XCTAssertFalse(policy.lowercased().contains("uninstall"))
        XCTAssertFalse(policy.contains("卸载"))
    }
}
