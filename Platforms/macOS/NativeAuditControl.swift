#if DEBUG
import AppKit
import SwiftUI

/// Diagnostic control only. Real editor audits always run separately without
/// this opt-in environment flag; no audit issue is suppressed by this view.
struct NativeAuditControl: NSViewRepresentable {
    static var enabled: Bool { ProcessInfo.processInfo.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] == "YES" }
    static var swiftUIEnabled: Bool { ProcessInfo.processInfo.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] == "SWIFTUI" }
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
        for label in [title, explanation, state] {
            label.textColor = .black
            label.backgroundColor = .white
            label.drawsBackground = true
        }
        let stack = NSStackView(views: [title, explanation, slider, state, button])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 24
        stack.edgeInsets = NSEdgeInsets(top: 32, left: 32, bottom: 32, right: 32)
        stack.wantsLayer = true; stack.layer?.backgroundColor = NSColor.white.cgColor
        stack.setAccessibilityElement(true); stack.setAccessibilityRole(.group)
        stack.setAccessibilityLabel(NSLocalizedString("AppKit audit diagnostic controls", comment: "Debug audit control"))
        slider.widthAnchor.constraint(equalToConstant: 320).isActive = true
        return stack
    }
    func updateNSView(_ view: NSView, context: Context) {}
    final class Coordinator: NSObject {
        weak var state: NSTextField?
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
#endif
