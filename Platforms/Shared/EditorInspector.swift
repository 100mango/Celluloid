import SwiftUI
import CelluloidDomain
import CelluloidRendering

struct EditorInspector: View {
    let recipe: EditRecipe
    @Binding var selection: UUID?
    let change: (EditRecipe, String) -> Void
    @State private var assetPanel: AssetPanel?
    @State private var showingPrivacy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Celluloid").font(.largeTitle.bold())
                Text("Native photo editor").foregroundStyle(.secondary)
                Picker("Filter", selection: Binding(get: { recipe.filter }, set: { preset in
                    var next = recipe; next.filter = preset; change(next, "Change Filter")
                })) {
                    ForEach(FilterPreset.allCases, id: \.rawValue) { Text($0.localizedTitle).tag($0) }
                }.accessibilityIdentifier("editor.filter")
                if recipe.sources.count > 1 {
                    CollagePicker(recipe: recipe, change: change)
                }
                HStack {
                    Button("Sticker") { assetPanel = .stickers }.accessibilityIdentifier("editor.add-sticker")
                    Button("Bubble") { assetPanel = .bubbles }.accessibilityIdentifier("editor.add-bubble")
                }.disabled(recipe.sources.isEmpty || recipe.overlays.count >= 100)
                .popover(item: $assetPanel) { panel in
                    AssetPaletteView(panel: panel) { overlay in add(overlay); assetPanel = nil }
                }
                SourceInspector(recipe: recipe, change: change)
                Text("Layers").font(.headline)
                if recipe.overlays.isEmpty { Text("Add a sticker or a speech bubble").foregroundStyle(.secondary) }
                ForEach(recipe.overlays.reversed()) { overlay in
                    Button {
                        selection = overlay.id
                    } label: {
                        HStack {
                            Image(systemName: overlay.kind == .bubble ? "text.bubble" : "face.smiling")
                            Text(overlay.kind == .bubble && !overlay.text.isEmpty ? overlay.text : overlay.asset).lineLimit(1)
                            Spacer()
                            if selection == overlay.id { Image(systemName: "checkmark.circle.fill") }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain).padding(6)
                        .accessibilityLabel(String(format: NSLocalizedString("Select layer: %@", comment: "Layer selection"), overlay.kind == .bubble && !overlay.text.isEmpty ? String(overlay.text.prefix(80)) : overlay.asset))
                        .accessibilityIdentifier("layer." + overlay.id.uuidString)
                }
                if let selected = recipe.overlays.first(where: { $0.id == selection }) {
                    OverlayInspector(overlay: selected, update: update, remove: remove)
                }
                Divider()
                Text("Static photos · sRGB SDR export").font(.caption).foregroundStyle(.secondary)
                Text("RAW/ProRAW and animation are not supported. Live Photos import as still images.").font(.caption).foregroundStyle(.secondary)
                Text("Save this .celluloid document to reopen all originals, layers and text. Export PNG or JPEG for a finished image.")
                    .font(.caption).foregroundStyle(.secondary)
                Button("Privacy Policy") { showingPrivacy = true }.accessibilityIdentifier("editor.privacy")
            }.padding(18)
        }.sheet(isPresented: $showingPrivacy) { PrivacyView() }
    }
    private func add(_ overlay: Overlay) {
        var next = recipe; next.overlays.append(overlay)
        selection = overlay.id; change(next, "Add \(overlay.kind.rawValue.capitalized)")
    }
    private func update(_ overlay: Overlay, _ name: String) {
        guard let index = recipe.overlays.firstIndex(where: { $0.id == overlay.id }) else { return }
        var next = recipe; next.overlays[index] = overlay; change(next, name)
    }
    private func remove(_ overlay: Overlay) {
        var next = recipe; next.overlays.removeAll { $0.id == overlay.id }
        selection = nil; change(next, "Delete Layer")
    }
}

private struct CollagePicker: View {
    let recipe: EditRecipe
    let change: (EditRecipe, String) -> Void
    @State private var templates: [CollageTemplate] = []
    @State private var failure: String?
    var body: some View {
        VStack(alignment: .leading) {
            Picker("Collage Layout", selection: Binding(get: { recipe.collageTemplate ?? "" }, set: { name in
                var next = recipe; next.collageTemplate = name; change(next, "Change Collage Layout")
            })) {
                ForEach(templates, id: \.assetName) { Text($0.assetName).tag($0.assetName) }
            }
            if let failure { Text(failure).foregroundStyle(.red) }
        }.task(id: recipe.sources.count) {
            do { templates = try NativeResources.templates(count: recipe.sources.count); failure = nil }
            catch { failure = error.localizedDescription }
        }
    }
}

private struct OverlayInspector: View {
    let overlay: Overlay
    let update: (Overlay, String) -> Void
    let remove: (Overlay) -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()
            Text("Selected Layer").font(.headline)
            if overlay.kind == .bubble {
                TextField("Bubble text", text: Binding(get: { overlay.text }, set: { text in
                    var next = overlay; next.text = text; update(next, "Edit Bubble Text")
                }), axis: .vertical).lineLimit(3...8).accessibilityIdentifier("editor.bubble-text")
                number("Text size", \.fontSize, range: 0.005...0.2)
            }
            number("Horizontal position", \.centerX, range: -0.5...1.5)
            number("Vertical position", \.centerY, range: -0.5...1.5)
            number("Width", \.width, range: 0.02...1.5)
            number("Height", \.height, range: 0.02...1.5)
            number("Rotation", \.rotation, range: -180...180)
            Toggle("Mirror layer", isOn: Binding(get: { overlay.mirrored }, set: { value in
                var next = overlay; next.mirrored = value; update(next, "Mirror Layer")
            }))
            HStack {
                Button("←") { nudge(x: -0.01, y: 0) }.keyboardShortcut(.leftArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer left")
                Button("↑") { nudge(x: 0, y: -0.01) }.keyboardShortcut(.upArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer up")
                Button("↓") { nudge(x: 0, y: 0.01) }.keyboardShortcut(.downArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer down")
                Button("→") { nudge(x: 0.01, y: 0) }.keyboardShortcut(.rightArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer right")
            }
            HStack {
                Button("Rotate −15°") { rotate(-15) }.keyboardShortcut("[", modifiers: [.command, .option])
                Button("Rotate +15°") { rotate(15) }.keyboardShortcut("]", modifiers: [.command, .option])
            }
            Button("Delete Layer", role: .destructive) { remove(overlay) }
            Text("Move with ⌥⌘ arrows; rotate with ⌥⌘ [ or ].").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func number(_ label: String, _ path: WritableKeyPath<Overlay, Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack { Text(LocalizedStringKey(label)); Spacer(); Text(overlay[keyPath: path], format: .number.precision(.fractionLength(2))).monospacedDigit() }
            Slider(value: Binding(get: { overlay[keyPath: path] }, set: { value in
                var next = overlay; next[keyPath: path] = value; update(next, label)
            }), in: range).accessibilityLabel(label)
        }
    }
    private func nudge(x: Double, y: Double) {
        var next = overlay
        next.centerX = min(3, max(-2, next.centerX + x)); next.centerY = min(3, max(-2, next.centerY + y))
        update(next, "Move Layer")
    }
    private func rotate(_ delta: Double) {
        var next = overlay; next.rotation = (next.rotation + delta).truncatingRemainder(dividingBy: 360)
        update(next, "Rotate Layer")
    }
}
