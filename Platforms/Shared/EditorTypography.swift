import SwiftUI

extension View {
    /// Small macOS bitmap glyphs had few full-coverage pixels in the real audit
    /// captures. Use body-sized medium helper text; keep other platform sizing.
    func editorHelperText() -> some View {
        #if os(macOS)
        font(.body.weight(.medium)).foregroundStyle(.primary)
        #else
        font(.caption).foregroundStyle(.primary)
        #endif
    }
    func editorAdjustmentLabel() -> some View {
        #if os(macOS)
        font(.body.weight(.medium))
        #else
        self
        #endif
    }
}
