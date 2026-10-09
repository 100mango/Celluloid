import Foundation

/// Opt-in scalar diagnostics only. Never logs asset IDs, pixels, paths or a view
/// hierarchy. System Photos readiness is not inferred from these app events.
enum PickerEntryDiagnostics {
    static func record(_ event: String, instance: String = "root") {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("--picker-entry-observation") else { return }
        print("PICKER_APP_TRACE event=\(event) instance=\(instance) uptime_seconds=\(ProcessInfo.processInfo.systemUptime) wall_seconds=\(Date().timeIntervalSince1970)")
        #endif
    }
}
