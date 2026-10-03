#if DEBUG
import Foundation
import Security

/// Only enabled by the disposable CI runtime test. No network, account or user data.
/// The Release build does not contain this diagnostic or its temporary write.
enum SandboxDiagnostics {
    static let enabled = ProcessInfo.processInfo.environment["CELLULOID_SANDBOX_DIAGNOSTICS"] == "YES"
    static let report: String = makeReport()
    private static func makeReport() -> String {
        guard enabled else { return "" }
        var record: [String: Any] = ["bundle": Bundle.main.bundleURL.path, "home": NSHomeDirectory(), "passed": false]
        do {
            var code: SecCode?
            guard SecCodeCopySelf(SecCSFlags(), &code) == errSecSuccess, let code else { throw CocoaError(.fileReadNoPermission) }
            var raw: CFDictionary?
            guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &raw) == errSecSuccess,
                  let info = raw as? [String: Any],
                  let entitlements = info[kSecCodeInfoEntitlementsDict as String] as? [String: Any] else { throw CocoaError(.fileReadNoPermission) }
            let keys = Set(entitlements.keys)
            record["entitlements"] = entitlements
            guard entitlements["com.apple.security.app-sandbox"] as? Bool == true,
                  entitlements["com.apple.security.files.user-selected.read-write"] as? Bool == true,
                  keys.isSubset(of: ["com.apple.security.app-sandbox", "com.apple.security.files.user-selected.read-write"]) else {
                throw CocoaError(.fileReadNoPermission)
            }
            let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                       appropriateFor: nil, create: true)
            record["applicationSupport"] = support.path
            guard NSHomeDirectory().contains("/Containers/"), support.path.hasPrefix(NSHomeDirectory() + "/") else {
                throw CocoaError(.fileReadNoPermission)
            }
            let folder = support.appendingPathComponent("Celluloid-Sandbox-Check-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: folder) }
            let url = folder.appendingPathComponent("synthetic.txt")
            let data = Data("Celluloid synthetic container readback".utf8)
            try data.write(to: url, options: .atomic)
            guard try Data(contentsOf: url) == data else { throw CocoaError(.fileReadCorruptFile) }
            record["passed"] = true
        } catch { record["error"] = error.localizedDescription }
        guard let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
              let result = String(data: data, encoding: .utf8) else { return "{\"passed\":false}" }
        return result
    }
}
#endif
