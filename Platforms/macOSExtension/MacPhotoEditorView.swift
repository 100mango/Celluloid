import AppKit
import SwiftUI
import CelluloidDomain
import CelluloidRendering

struct MacPhotoEditorView: View {
    @ObservedObject var session: MacPhotoSession
    @State private var palette: MacPhotoLayer.Kind?
    var body: some View {
        HStack(spacing: 16) {
            ZStack {
                Color(nsColor: .underPageBackgroundColor)
                if let preview = session.preview {
                    Image(preview, scale: 1, label: Text("Edited photo preview")).resizable().aspectRatio(contentMode: .fit)
                } else if let image = session.placeholder {
                    Image(nsImage: image).resizable().aspectRatio(contentMode: .fit).accessibilityLabel("Current photo from Photos")
                }
                if session.loading || session.rendering || session.finishing { ProgressView().accessibilityLabel("Preparing photo") }
            }.accessibilityElement(children: .contain).accessibilityLabel("Photo preview")
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Celluloid").font(.title)
                    if session.readOnly {
                        Text("These edits cannot be safely restored here. You can view the current photo. Done and Cancel leave its existing edits and original unchanged.")
                            .accessibilityIdentifier("photos-extension.read-only")
                    } else {
                        NativeChoicePicker(selection: Binding(get: { session.adjustment.filter.rawValue }, set: { raw in
                            if let value = FilterPreset(rawValue: raw) { session.change { $0.filter = value } }
                        }), options: FilterPreset.allCases.map { (id: $0.rawValue, title: $0.localizedTitle) },
                            label: NSLocalizedString("Filter", comment: "Filter menu"), identifier: "photos-extension.filter")
                        if session.adjustment.filter == .pixellateFace {
                            Text("Face detection can miss faces. Check the result before sharing.").font(.caption)
                        }
                        HStack {
                            Button("Sticker") { palette = .sticker }.accessibilityIdentifier("photos-extension.add-sticker")
                            Button("Bubble") { palette = .bubble }.accessibilityIdentifier("photos-extension.add-bubble")
                        }.disabled(true) // Independent UIKit layer-pixel gate has not passed.
                        .popover(isPresented: Binding(get: { palette != nil }, set: { if !$0 { palette = nil } })) {
                            if let kind = palette {
                                MacPhotoAssetPicker(kind: kind, select: { asset in session.add(kind: kind, asset: asset); palette = nil }, close: { palette = nil })
                            }
                        }
                        Text("Layers").font(.headline)
                        ForEach(session.adjustment.layers.reversed()) { layer in
                            Button { session.selection = layer.id } label: {
                                HStack {
                                    Image(systemName: layer.kind == .bubble ? "text.bubble" : "face.smiling")
                                    Text(title(layer)).lineLimit(2)
                                    Spacer()
                                    if session.selection == layer.id { Image(systemName: "checkmark.circle.fill") }
                                }.contentShape(Rectangle())
                            }.buttonStyle(.plain).padding(5)
                            .accessibilityIdentifier("photos-extension.layer." + layer.id.uuidString)
                            .accessibilityLabel(String(format: NSLocalizedString("Select layer: %@", comment: "Layer selection"), title(layer)))
                        }
                        if let layer = session.adjustment.layers.first(where: { $0.id == session.selection }) {
                            layerControls(layer).id(layer.id)
                        }
                        Text("Use Done in Photos to save and reopen editable filters. Sticker and bubble editing is temporarily unavailable while cross-platform rendering is verified.").font(.callout)
                        Text("Static photos · sRGB SDR export").font(.caption)
                    }
                    if let error = session.error { Text(error).foregroundStyle(.red).accessibilityIdentifier("photos-extension.error") }
                }.padding(8)
                .disabled(session.finishing || session.loading)
            }.frame(width: 285)
            .accessibilityElement(children: .contain).accessibilityLabel("Photo editing controls")
        }.padding(16).frame(minWidth: 640, minHeight: 440)
        .accessibilityElement(children: .contain).accessibilityLabel("Celluloid photo editor")
    }
    private func title(_ layer: MacPhotoLayer) -> String {
        if layer.kind == .bubble { return layer.text.isEmpty ? (BubbleAsset(rawValue: layer.asset)?.localizedTitle ?? layer.asset) : String(layer.text.prefix(80)) }
        return String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(layer.asset) ?? 32) - 31)
    }
    private func current(_ id: UUID) -> MacPhotoLayer? { session.adjustment.layers.first { $0.id == id } }
    private func layerControls(_ layer: MacPhotoLayer) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if layer.kind == .bubble {
                Text("Bubble text")
                MacPhotoTextEditor(text: Binding(get: { current(layer.id)?.text ?? "" }, set: { value in
                    session.edit(layer.id) { $0.text = value }
                })).frame(height: 100)
            }
            HStack {
                Button("←") { move(layer.id, x: -10, y: 0) }.accessibilityLabel("Move layer left")
                Button("↑") { move(layer.id, x: 0, y: -10) }.accessibilityLabel("Move layer up")
                Button("↓") { move(layer.id, x: 0, y: 10) }.accessibilityLabel("Move layer down")
                Button("→") { move(layer.id, x: 10, y: 0) }.accessibilityLabel("Move layer right")
            }
            HStack {
                Button("Rotate −15°") { rotate(layer.id, angle: -.pi / 12) }
                Button("Rotate +15°") { rotate(layer.id, angle: .pi / 12) }
            }
            HStack {
                Button("Make Smaller") { resize(layer.id, factor: 1 / 1.1) }
                Button("Make Larger") { resize(layer.id, factor: 1.1) }
            }
            Button("Delete Layer", role: .destructive) { session.remove(layer.id) }.accessibilityIdentifier("photos-extension.delete-layer")
        }
    }
    private func move(_ id: UUID, x: CGFloat, y: CGFloat) { session.edit(id) { $0.center.x += x; $0.center.y += y } }
    private func rotate(_ id: UUID, angle: CGFloat) { session.edit(id) { $0.transform = $0.transform.rotated(by: angle) } }
    private func resize(_ id: UUID, factor: CGFloat) {
        session.edit(id) {
            let size = CGSize(width: $0.bounds.width * factor, height: $0.bounds.height * factor)
            if size.width >= 52 && size.height >= 52 { $0.bounds.size = size }
        }
    }
}

private struct MacPhotoAssetPicker: View {
    let kind: MacPhotoLayer.Kind
    let select: (String) -> Void
    let close: () -> Void
    private var assets: [String] { kind == .sticker ? StickerAsset.all.map(\.rawValue) : BubbleAsset.allCases.map(\.rawValue) }
    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Text(LocalizedStringKey(kind == .sticker ? "Choose a Sticker" : "Choose a Bubble")).font(.headline)
                Spacer(); Button("Done", action: close)
            }
            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3)) {
                    ForEach(assets, id: \.self) { asset in
                        MacPhotoAssetCell(asset: asset, title: title(asset)) { select(asset) }
                    }
                }
            }
        }.padding(16).frame(width: 350, height: 410)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(kind == .sticker ? Text("Choose a Sticker") : Text("Choose a Bubble"))
    }
    private func title(_ asset: String) -> String {
        kind == .sticker ? String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(asset) ?? 32) - 31) : (BubbleAsset(rawValue: asset)?.localizedTitle ?? asset)
    }
}
private struct MacPhotoAssetCell: View {
    let asset: String
    let title: String
    let select: () -> Void
    @State private var image: CGImage?
    @State private var failed = false
    var body: some View {
        Button(action: select) {
            VStack {
                if let image { Image(decorative: image, scale: 1).resizable().aspectRatio(contentMode: .fit).frame(height: 68) }
                else if failed { Image(systemName: "exclamationmark.triangle").frame(height: 68) }
                else { ProgressView().frame(height: 68) }
                Text(title).font(.caption)
            }.frame(maxWidth: .infinity).contentShape(Rectangle())
        }.buttonStyle(.plain).padding(4).disabled(failed || image == nil)
        .accessibilityLabel(title).accessibilityIdentifier("photos-extension.asset." + asset)
        .task(id: asset) { do { image = try NativeResources.image(named: asset) } catch { failed = true } }
    }
}

/// NSTextView reports complete strings on every edit; preview publications do
/// not reset selection or IME marked text. The host's Done commits first responder.
private struct MacPhotoTextEditor: NSViewRepresentable {
    @Binding var text: String
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator($text) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        let editor = scroll.documentView as! NSTextView
        editor.isRichText = false; editor.font = .systemFont(ofSize: 14); editor.delegate = context.coordinator
        editor.setAccessibilityLabel(NSLocalizedString("Bubble text", comment: "Bubble text input"))
        editor.setAccessibilityIdentifier("photos-extension.bubble-text")
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.binding = $text
        guard let editor = scroll.documentView as? NSTextView else { return }
        editor.isEditable = enabled
        if editor.string != text && !editor.hasMarkedText() {
            let selection = editor.selectedRange(); editor.string = text
            editor.setSelectedRange(NSRange(location: min(selection.location, (text as NSString).length), length: 0))
        }
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var binding: Binding<String>
        init(_ binding: Binding<String>) { self.binding = binding }
        func textDidChange(_ notification: Notification) {
            guard let editor = notification.object as? NSTextView else { return }
            binding.wrappedValue = editor.string
            // A rejected over-budget edit must not appear to have been saved.
            if !editor.hasMarkedText(), editor.string != binding.wrappedValue { editor.string = binding.wrappedValue }
        }
    }
}
