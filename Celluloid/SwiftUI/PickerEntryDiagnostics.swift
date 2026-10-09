import Foundation

/// Opt-in DEBUG scalar diagnostics. No library reads, IO or view-tree inspection.
/// Real PHPicker lifecycle comes from native XCTest events, never these markers.
enum PickerEntryDiagnostics {
    static func record(_ event: String, instance: String = "root", picker: String = "none", details: String = "") {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("--picker-entry-observation"),
              let run = ProcessInfo.processInfo.environment["CELLULOID_PICKER_TRACE_RUN"],
              UUID(uuidString: run) != nil else { return }
        let uptime = ProcessInfo.processInfo.systemUptime
        let wall = Date().timeIntervalSince1970
        print("PICKER_APP_TRACE run=\(run) event=\(event) instance=\(instance) picker=\(picker) pid=\(ProcessInfo.processInfo.processIdentifier) uptime_seconds=\(uptime) wall_seconds=\(wall) \(details)")
        #endif
    }

    /// Only the explicitly opted-in disposable synthetic-library test records
    /// identities; ordinary diagnostic/product sessions never emit photo IDs.
    static func selected(_ event: String, instance: String, identifiers: [String?]) {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("--picker-seeded-identity"),
              (1...4).contains(identifiers.count),
              let bytes = try? JSONSerialization.data(withJSONObject: identifiers.map { $0.map { $0 as Any } ?? NSNull() }) else { return }
        record(event, instance: instance, details: "selection_base64=\(bytes.base64EncodedString())")
        #endif
    }
}
