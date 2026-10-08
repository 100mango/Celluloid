import SwiftUI
#if os(macOS)
import AppKit
#endif

/// Keep native macOS range-control semantics, including its accessible thumb
/// value and keyboard action. Vision uses its platform SwiftUI control.
struct EditorSlider: View {
    @Binding var value: Double
    let range: ClosedRange<Double>
    let label: String
    var body: some View {
        #if os(macOS)
        MacEditorSlider(value: $value, range: range, label: label).frame(height: 24)
        #else
        Slider(value: $value, in: range).accessibilityLabel(label)
        #endif
    }
}

#if os(macOS)
private struct MacEditorSlider: NSViewRepresentable {
    @Binding var value: Double
    let range: ClosedRange<Double>
    let label: String
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(value: $value) }
    func makeNSView(context: Context) -> NSSlider {
        let slider = NSSlider(value: value, minValue: range.lowerBound, maxValue: range.upperBound,
                              target: context.coordinator, action: #selector(Coordinator.changed(_:)))
        slider.isContinuous = true
        slider.setAccessibilityLabel(label)
        return slider
    }
    func updateNSView(_ slider: NSSlider, context: Context) {
        context.coordinator.value = $value
        slider.minValue = range.lowerBound; slider.maxValue = range.upperBound
        if slider.doubleValue != value { slider.doubleValue = value }
        slider.isEnabled = enabled
        slider.setAccessibilityLabel(label)
    }
    final class Coordinator: NSObject {
        var value: Binding<Double>
        init(value: Binding<Double>) { self.value = value }
        @objc func changed(_ sender: NSSlider) { value.wrappedValue = sender.doubleValue }
    }
}
#endif
