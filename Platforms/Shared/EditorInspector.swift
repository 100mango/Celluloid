import SwiftUI
import CelluloidDomain
import CelluloidRendering
#if os(macOS)
import AppKit
#endif

struct EditorInspector: View {
    let recipe: EditRecipe
    @Binding var selection: UUID?
    let change: RecipeChange
    @State private var assetPanel: AssetPanel?
    @State private var showingPrivacy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Celluloid").font(.largeTitle.bold())
                Text("Native photo editor").foregroundStyle(.primary)
                #if os(macOS)
                HStack {
                    Text("Filter")
                    NativeChoicePicker(selection: Binding(get: { recipe.filter.rawValue }, set: { raw in
                        guard let preset = FilterPreset(rawValue: raw) else { return }
                        change({ $0.filter = preset }, "Change Filter")
                    }), options: FilterPreset.allCases.map { (id: $0.rawValue, title: $0.localizedTitle) },
                       label: NSLocalizedString("Filter", comment: "Filter menu"), identifier: "editor.filter")
                }
                #else
                Picker("Filter", selection: Binding(get: { recipe.filter }, set: { preset in
                    change({ $0.filter = preset }, "Change Filter")
                })) {
                    ForEach(FilterPreset.allCases, id: \.rawValue) { Text($0.localizedTitle).tag($0) }
                }.accessibilityIdentifier("editor.filter")
                #endif
                if recipe.filter == .pixellateFace { Text("Face detection can miss faces. Check the result before sharing.").font(.caption) }
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
                if recipe.overlays.isEmpty { Text("Add a sticker or a speech bubble").foregroundStyle(.primary) }
                ForEach(recipe.overlays.reversed()) { overlay in
                    Button {
                        selection = overlay.id
                    } label: {
                        HStack {
                            Image(systemName: overlay.kind == .bubble ? "text.bubble" : "face.smiling")
                            Text(layerTitle(overlay)).lineLimit(1)
                            Spacer()
                            if selection == overlay.id { Image(systemName: "checkmark.circle.fill") }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain).padding(6)
                        .accessibilityLabel(String(format: NSLocalizedString("Select layer: %@", comment: "Layer selection"), String(layerTitle(overlay).prefix(80))))
                        .accessibilityIdentifier("layer." + overlay.id.uuidString)
                }
                if let selected = recipe.overlays.first(where: { $0.id == selection }) {
                    OverlayInspector(overlay: selected, update: update, remove: remove).id(selected.id)
                }
                Divider()
                Text("Static photos · sRGB SDR export").editorHelperText()
                Text("RAW/ProRAW and animation are not supported. Live Photos import as still images.").editorHelperText()
                Text("Save this .celluloid document to reopen all originals, layers and text. Export PNG or JPEG for a finished image.")
                    .editorHelperText()
                Button("Privacy Policy") { showingPrivacy = true }.accessibilityIdentifier("editor.privacy")
            }.padding(18)
        }.sheet(isPresented: $showingPrivacy) { PrivacyView() }
    }
    private func layerTitle(_ overlay: Overlay) -> String {
        if overlay.kind == .bubble {
            return overlay.text.isEmpty ? (BubbleAsset(rawValue: overlay.asset)?.localizedTitle ?? overlay.asset) : overlay.text
        }
        return String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(overlay.asset) ?? 32) - 31)
    }
    private func add(_ overlay: Overlay) {
        selection = overlay.id
        change({ $0.overlays.append(overlay) }, "Add \(overlay.kind.rawValue.capitalized)")
    }
    private func update(_ identity: UUID, _ mutation: @escaping (inout Overlay) -> Void, _ name: String) {
        change({ $0.editOverlay(identity, mutation: mutation) }, name)
    }
    private func remove(_ overlay: Overlay) {
        selection = nil
        change({ $0.overlays.removeAll { $0.id == overlay.id } }, "Delete Layer")
    }
}

private struct CollagePicker: View {
    let recipe: EditRecipe
    let change: RecipeChange
    @State private var templates: [CollageTemplate] = []
    @State private var failure: String?
    var body: some View {
        VStack(alignment: .leading) {
            Picker("Collage Layout", selection: Binding(get: { recipe.collageTemplate ?? "" }, set: { name in
                change({ $0.collageTemplate = name }, "Change Collage Layout")
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
    let update: (UUID, @escaping (inout Overlay) -> Void, String) -> Void
    let remove: (Overlay) -> Void
    #if os(macOS)
    @FocusState private var editingText: Bool
    #endif
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()
            Text("Selected Layer").font(.headline)
            if overlay.kind == .bubble {
                #if os(visionOS)
                VisionBubbleTextEditor(value: overlay.text, accepts: { text in
                    var candidate = overlay; candidate.text = text
                    return (try? candidate.validate()) != nil
                }) { text in edit("Edit Bubble Text") { $0.text = text } }.id(overlay.id)
                #else
                TextField("Bubble text", text: Binding(get: { overlay.text }, set: { text in
                    edit("Edit Bubble Text") { $0.text = text }
                }), axis: .vertical).lineLimit(3...8).accessibilityIdentifier("editor.bubble-text")
                    .focused($editingText)
                #endif
                number("Text size", \.fontSize, range: 0.005...0.2)
            }
            number("Horizontal position", \.centerX, range: -0.5...1.5)
            number("Vertical position", \.centerY, range: -0.5...1.5)
            number("Width", \.width, range: 0.02...1.5)
            number("Height", \.height, range: 0.02...1.5)
            number("Rotation", \.rotation, range: -180...180)
            Toggle("Mirror layer", isOn: Binding(get: { overlay.mirrored }, set: { value in
                edit("Mirror Layer") { $0.mirrored = value }
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
            Text("Move with ⌥⌘ arrows; rotate with ⌥⌘ [ or ].").editorHelperText()
        }
    }
    private func edit(_ name: String, _ mutation: @escaping (inout Overlay) -> Void) {
        update(overlay.id, mutation, name)
    }
    private func number(_ label: String, _ path: WritableKeyPath<Overlay, Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack { Text(LocalizedStringKey(label)).editorAdjustmentLabel(); Spacer(); Text(overlay[keyPath: path], format: .number.precision(.fractionLength(2))).monospacedDigit().accessibilityIdentifier("editor.layer.value." + label) }
            EditorSlider(value: Binding(get: { overlay[keyPath: path] }, set: { value in
                edit(label) { $0[keyPath: path] = value }
            }), range: range, label: NSLocalizedString(label, comment: "Layer adjustment"))
        }
    }
    #if os(macOS)
    private func finishTextInput() -> Bool {
        // A Cocoa field editor may commit on focus exit. Complete that normal
        // responder transition synchronously before applying a document command.
        if editingText, NSApp.keyWindow?.makeFirstResponder(nil) == false { return false }
        editingText = false
        return true
    }
    #endif
    private func nudge(x: Double, y: Double) {
        #if os(macOS)
        // These are document-transform commands, even when invoked while a
        // multiline field is focused. End text input before the next Undo.
        guard finishTextInput() else { return }
        #endif
        edit("Move Layer") {
            $0.centerX = min(3, max(-2, $0.centerX + x)); $0.centerY = min(3, max(-2, $0.centerY + y))
        }
    }
    private func rotate(_ delta: Double) {
        #if os(macOS)
        guard finishTextInput() else { return }
        #endif
        edit("Rotate Layer") { $0.rotation = ($0.rotation + delta).truncatingRemainder(dividingBy: 360) }
    }
}

#if os(visionOS)
/// Keep the text-input value in local state while document revisions and preview
/// tasks are published. The previous getter read an immutable recipe snapshot on
/// every input event; exact full-string UI assertions guard against lost input.
private struct VisionBubbleTextEditor: View {
    let value: String
    let accepts: (String) -> Bool
    let commit: (String) -> Void
    @State private var draft: String
    init(value: String, accepts: @escaping (String) -> Bool, commit: @escaping (String) -> Void) {
        self.value = value; self.accepts = accepts; self.commit = commit; _draft = State(initialValue: value)
    }
    var body: some View {
        TextEditor(text: $draft).frame(minHeight: 110, maxHeight: 180)
            .accessibilityLabel("Bubble text").accessibilityIdentifier("editor.bubble-text")
            .onChange(of: draft) { text in
                if text != value {
                    commit(text) // The document reports its normal validation error.
                    if !accepts(text) { draft = value } // Never display unsaved oversized text as the exported recipe.
                }
            }
            .onChange(of: value) { text in if text != draft { draft = text } }
    }
}
#endif
