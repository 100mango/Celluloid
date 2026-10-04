#if DEBUG
import AppKit
import SwiftUI

/// Diagnostic control only. Real editor audits always run separately without
/// this opt-in environment flag; no audit issue is suppressed by this view.
struct NativeAuditControl: NSViewRepresentable {
    static var enabled: Bool { ProcessInfo.processInfo.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] == "YES" }
    static var swiftUIEnabled: Bool { ["SWIFTUI", "SWIFTUI-SPLIT"].contains(ProcessInfo.processInfo.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] ?? "") }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> NSView {
        let title = NSTextField(labelWithString: "Native AppKit accessibility control")
        title.font = .systemFont(ofSize: 24, weight: .bold)
        let explanation = NSTextField(labelWithString: "Black text on white, using standard AppKit controls.")
        explanation.font = .systemFont(ofSize: 18)
        let slider = NSSlider(value: 0.5, minValue: 0, maxValue: 1, target: context.coordinator, action: #selector(Coordinator.changed(_:)))
        slider.setAccessibilityLabel(NSLocalizedString("Diagnostic value", comment: "Debug audit control"))
        slider.setAccessibilityIdentifier("probe.slider")
        let state = NSTextField(labelWithString: "Ready")
        state.font = .systemFont(ofSize: 18)
        state.setAccessibilityIdentifier("probe.status")
        context.coordinator.state = state
        let button = NSButton(title: "Diagnostic action", target: context.coordinator, action: #selector(Coordinator.clicked(_:)))
        button.setAccessibilityIdentifier("probe.action")
        button.bezelStyle = .rounded
        let document = NSButton(title: "Open Standard AppKit Document", target: context.coordinator, action: #selector(Coordinator.openDocument(_:)))
        document.setAccessibilityIdentifier("probe.document"); document.bezelStyle = .rounded
        for label in [title, explanation, state] {
            label.textColor = .black
            label.backgroundColor = .white
            label.drawsBackground = true
        }
        let stack = NSStackView(views: [title, explanation, slider, state, button, document])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 24
        stack.edgeInsets = NSEdgeInsets(top: 32, left: 32, bottom: 32, right: 32)
        stack.wantsLayer = true; stack.layer?.backgroundColor = NSColor.white.cgColor
        stack.setAccessibilityElement(true); stack.setAccessibilityRole(.group)
        stack.setAccessibilityLabel(NSLocalizedString("AppKit audit diagnostic controls", comment: "Debug audit control"))
        slider.widthAnchor.constraint(equalToConstant: 320).isActive = true
        return stack
    }
    func updateNSView(_ view: NSView, context: Context) {}
    @MainActor final class Coordinator: NSObject {
        weak var state: NSTextField?
        @objc func openDocument(_ sender: NSButton) {
            let previous = sender.window
            let document = StandardAppKitAuditDocument()
            NSDocumentController.shared.addDocument(document)
            document.makeWindowControllers(); document.showWindows()
            previous?.close() // Close only this empty diagnostic host window.
        }
        @objc func clicked(_ sender: NSButton) { state?.stringValue = "Action completed" }
        @objc func changed(_ sender: NSSlider) { state?.stringValue = String(format: "Value %.2f", sender.doubleValue) }
    }
}
/// Small equivalent SwiftUI control: explicit black, semantic primary, caption
/// and one labeled adjustable control. It never replaces the real editor audits.
struct NativeSwiftUIAuditControl: View {
    @State private var value = 0.5
    @State private var completed = false
    var body: some View {
        if ProcessInfo.processInfo.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] == "SWIFTUI-SPLIT" { splitComparison }
        else { simpleComparison }
    }
    private var splitComparison: some View {
        HSplitView {
            ZStack {
                Rectangle().fill(Color.secondary.opacity(0.08))
                VStack(spacing: 12) {
                    Image(systemName: "photo.on.rectangle.angled").font(.system(size: 48))
                    Text("Start with your photos").font(.title2)
                    Text("Import one photo to edit, or 2–4 for a collage.\nYour originals stay in this editable document.")
                        .multilineTextAlignment(.center).foregroundStyle(.primary).accessibilityIdentifier("probe.same-empty-instruction")
                }.padding(24)
            }.frame(minWidth: 320, maxWidth: .infinity, maxHeight: .infinity)
                .background(NativeWindowAccessibility(paneLabel: NSLocalizedString("Photo preview", comment: "Split pane")).frame(width: 0, height: 0))
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Celluloid").font(.largeTitle.bold())
                    Text("Native photo editor").foregroundStyle(.primary)
                    Divider()
                    ForEach(["Text size", "Horizontal position"], id: \.self) { title in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(LocalizedStringKey(title)).editorAdjustmentLabel().accessibilityIdentifier("probe.same-label." + title)
                                Spacer(); Text(value, format: .number.precision(.fractionLength(2))).monospacedDigit()
                            }
                            EditorSlider(value: $value, range: 0...1, label: title)
                        }
                    }
                    Text(verbatim: completed ? "Action completed" : "Ready").accessibilityIdentifier("probe.status")
                    Button { completed = true } label: { Text(verbatim: "Diagnostic action") }.accessibilityIdentifier("probe.action")
                }.padding(18)
            }.frame(minWidth: 250, idealWidth: 290, maxWidth: 360)
                .background(NativeWindowAccessibility(paneLabel: NSLocalizedString("Editing controls", comment: "Split pane")).frame(width: 0, height: 0))
        }.frame(minWidth: 640, minHeight: 480)
            .accessibilityElement(children: .contain).accessibilityLabel("SwiftUI audit diagnostic controls")
    }
    private var simpleComparison: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text(verbatim: "Native SwiftUI accessibility control").font(.system(size: 24, weight: .bold)).foregroundColor(.black)
            Text(verbatim: "Explicit black text on white.").font(.system(size: 18)).foregroundColor(.black).accessibilityIdentifier("probe.explicit-black")
            Text(verbatim: "Semantic primary text on white.").font(.system(size: 18)).foregroundStyle(.primary).accessibilityIdentifier("probe.semantic-primary")
            Text(verbatim: "Semantic primary caption on white.").font(.caption).foregroundStyle(.primary).accessibilityIdentifier("probe.semantic-caption")
            Text(verbatim: "Semantic primary body 13 on white.").font(.system(size: 13)).foregroundStyle(.primary).accessibilityIdentifier("probe.semantic-body")
            Text(verbatim: "Semantic primary medium 13 on white.").font(.system(size: 13, weight: .medium)).foregroundStyle(.primary).accessibilityIdentifier("probe.semantic-medium")
            Slider(value: $value, in: 0...1).frame(width: 320).accessibilityLabel("Diagnostic value").accessibilityIdentifier("probe.slider")
            Text(verbatim: completed ? "Action completed" : "Ready").font(.system(size: 18)).foregroundColor(.black).accessibilityIdentifier("probe.status")
            Button { completed = true } label: { Text(verbatim: "Diagnostic action") }.accessibilityIdentifier("probe.action")
            Spacer()
        }.padding(32).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).background(Color.white)
            .accessibilityElement(children: .contain).accessibilityLabel("SwiftUI audit diagnostic controls")
    }
}

/// A real, separate NSDocument/NSWindowController with standard AppKit controls.
/// No custom titlebar, title/status color, modal AX hiding, or audit filtering.
@MainActor private final class StandardAppKitAuditDocument: NSDocument {
    private let status = NSTextField(labelWithString: "Standard AppKit document")
    override func makeWindowControllers() {
        let window = NSWindow(contentRect: NSRect(x: 120, y: 180, width: 640, height: 420),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        let mark = NSButton(title: "Mark Document Edited", target: self, action: #selector(markEdited(_:)))
        mark.setAccessibilityIdentifier("probe.document-mark-edited")
        let alert = NSButton(title: "Show Standard NSAlert", target: self, action: #selector(showAlert(_:)))
        alert.setAccessibilityIdentifier("probe.document-alert")
        for button in [mark, alert] { button.bezelStyle = .rounded }
        status.setAccessibilityIdentifier("probe.document-status")
        status.font = .systemFont(ofSize: 13); status.textColor = .labelColor
        let stack = NSStackView(views: [status, mark, alert])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 24
        stack.edgeInsets = NSEdgeInsets(top: 32, left: 32, bottom: 32, right: 32)
        stack.setAccessibilityLabel(NSLocalizedString("AppKit audit diagnostic controls", comment: "Debug standard document"))
        window.contentView = stack
        let controller = NSWindowController(window: window)
        addWindowController(controller); controller.synchronizeWindowTitleWithDocumentName()
    }
    @objc private func markEdited(_ sender: NSButton) {
        updateChangeCount(.changeDone); status.stringValue = "Document is edited"
    }
    @objc private func showAlert(_ sender: NSButton) {
        guard let window = sender.window else { return }
        let alert = NSAlert(); alert.messageText = "Celluloid"
        alert.informativeText = "This file could not be decoded as an image."
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { [weak self] _ in self?.status.stringValue = "Standard alert dismissed" }
    }
}
#endif
