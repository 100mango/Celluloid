import AppKit
import SwiftUI

/// Standard AppKit popup-button action/value semantics. Persist only stable IDs;
/// localized titles are presentation, never the saved filter or template key.
struct NativeChoicePicker: NSViewRepresentable {
    @Binding var selection: String
    let options: [(id: String, title: String)]
    let label: String
    let identifier: String
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(selection: $selection, options: options) }
    func makeNSView(context: Context) -> NSPopUpButton {
        let button = NSPopUpButton(frame: .zero, pullsDown: false)
        button.target = context.coordinator; button.action = #selector(Coordinator.changed(_:))
        return button
    }
    func updateNSView(_ button: NSPopUpButton, context: Context) {
        context.coordinator.selection = $selection; context.coordinator.options = options
        let titles = options.map(\.title)
        if button.itemTitles != titles { button.removeAllItems(); button.addItems(withTitles: titles) }
        if let index = options.firstIndex(where: { $0.id == selection }) { button.selectItem(at: index) }
        else { button.select(nil) }
        button.isEnabled = enabled
        button.setAccessibilityLabel(label); button.setAccessibilityIdentifier(identifier)
    }
    final class Coordinator: NSObject {
        var selection: Binding<String>
        var options: [(id: String, title: String)]
        init(selection: Binding<String>, options: [(id: String, title: String)]) { self.selection = selection; self.options = options }
        @objc func changed(_ sender: NSPopUpButton) {
            guard options.indices.contains(sender.indexOfSelectedItem) else { return }
            selection.wrappedValue = options[sender.indexOfSelectedItem].id
        }
    }
}

/// A native pull-down menu preserves the real PNG/JPEG choice and Cocoa press
/// action instead of replacing export with an accessibility-only shortcut.
struct NativeExportMenu: NSViewRepresentable {
    let export: (Bool) -> Void
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(export: export) }
    func makeNSView(context: Context) -> NSPopUpButton {
        let button = NSPopUpButton(frame: .zero, pullsDown: true)
        button.addItems(withTitles: [NSLocalizedString("Export", comment: "Export menu"),
                                    NSLocalizedString("PNG…", comment: "Export menu"), NSLocalizedString("JPEG…", comment: "Export menu")])
        button.target = context.coordinator; button.action = #selector(Coordinator.selected(_:))
        button.setAccessibilityLabel(NSLocalizedString("Export", comment: "Export menu"))
        button.setAccessibilityIdentifier("editor.export")
        return button
    }
    func updateNSView(_ button: NSPopUpButton, context: Context) {
        context.coordinator.export = export; button.isEnabled = enabled
    }
    final class Coordinator: NSObject {
        var export: (Bool) -> Void
        init(export: @escaping (Bool) -> Void) { self.export = export }
        @objc func selected(_ sender: NSPopUpButton) {
            if sender.indexOfSelectedItem == 1 { export(true) }
            else if sender.indexOfSelectedItem == 2 { export(false) }
        }
    }
}
