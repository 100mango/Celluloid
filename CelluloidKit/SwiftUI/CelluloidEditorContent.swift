import SwiftUI

@MainActor
public struct CelluloidEditorContent: View {
    @ObservedObject private var session: CelluloidEditingSession
    @State private var sheet: EditorSheet?
    @State private var fullScreenSheet: EditorSheet?
    @State private var dragTranslation = CGSize.zero
    public init(session: CelluloidEditingSession) { self.session = session }

    public var body: some View {
        VStack(spacing: 0) {
            GeometryReader { geometry in
                CelluloidEditorCanvas(session: session)
                    .contentShape(Rectangle())
                    .gesture(DragGesture().onChanged { value in
                        drag(value.translation, available: geometry.size)
                    }.onEnded { _ in dragTranslation = .zero })
                    .overlay(alignment: .topLeading) {
                        if session.previewIsLoading || session.phase == .loading || session.phase == .empty {
                            ProgressView().padding().background(.regularMaterial).cornerRadius(12).padding()
                        }
                    }
            }
            .frame(minHeight: 120)
            if session.isReadOnly {
                Text(tr(.unreadableEditsMessage)).font(.body).padding()
                    .accessibilityIdentifier("read-only-adjustment")
            } else {
                CelluloidLayerControls(session: session, editText: openTextEditor)
                Divider()
                HStack(spacing: 12) {
                    tool(tr(.filter), image: "camera.filters", id: "tool-filter", sheet: .filter)
                    tool(tr(.bubble), image: "text.bubble", id: "tool-bubble", sheet: .bubble)
                    tool(tr(.sticker), image: "face.smiling", id: "tool-sticker", sheet: .sticker)
                }
                .padding(8)
                .disabled(!session.canEdit)
            }
        }
        .background(Color(uiColor: .systemBackground))
        .sheet(item: $sheet, onDismiss: { session.isPresentingTool = false }) { selected in
            CelluloidEditorSheet(sheet: selected, session: session)
        }
        .fullScreenCover(item: $fullScreenSheet, onDismiss: { session.isPresentingTool = false }) { selected in
            CelluloidEditorSheet(sheet: selected, session: session)
        }
        .onChange(of: session.sessionIdentity) { _ in sheet = nil; fullScreenSheet = nil; dragTranslation = .zero }
        .alert(NSLocalizedString("Photo Editor", comment: ""), isPresented: Binding(
            get: { session.notice != nil }, set: { if !$0 { session.notice = nil } })) {
                Button(tr(.done), role: .cancel) { session.notice = nil }
            } message: { Text(session.notice ?? "") }
    }
    private func tool(_ title: String, image: String, id: String, sheet: EditorSheet) -> some View {
        Button {
            session.isPresentingTool = true
            if case .bubble = sheet { fullScreenSheet = sheet } else { self.sheet = sheet }
        } label: {
            Label(title, systemImage: image).frame(maxWidth: .infinity, minHeight: 44)
        }.accessibilityIdentifier(id)
    }
    private func openTextEditor() {
        guard let layer = session.selectedLayer, let text = session.text(for: layer) else { return }
        session.isPresentingTool = true
        fullScreenSheet = .text(layer, text, session.sessionIdentity)
    }
    private func drag(_ translation: CGSize, available: CGSize) {
        guard session.canEdit, session.selectedLayer != nil,
              let canvas = session.adjustment.referenceCanvasSize,
              let image = session.sourceImage, image.size.width > 0, image.size.height > 0 else { return }
        let scale = min(available.width / image.size.width, available.height / image.size.height)
        let width = image.size.width * scale, height = image.size.height * scale
        guard width > 0, height > 0 else { return }
        let dx = (translation.width - dragTranslation.width) * canvas.width / width
        let dy = (translation.height - dragTranslation.height) * canvas.height / height
        dragTranslation = translation
        session.moveSelectedLayer(x: dx, y: dy)
    }
}

@MainActor
private struct CelluloidLayerControls: View {
    @ObservedObject var session: CelluloidEditingSession
    let editText: () -> Void
    var body: some View {
        VStack(spacing: 4) {
            if !session.layers.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(session.layers) { layer in
                            Button { session.selectedLayer = layer } label: {
                                Label(title(layer), systemImage: session.selectedLayer == layer ? "checkmark.circle.fill" : "circle")
                                    .padding(.horizontal, 8).frame(minHeight: 44)
                            }
                            .accessibilityAddTraits(session.selectedLayer == layer ? .isSelected : [])
                            .accessibilityValue(session.text(for: layer) ?? "")
                            .accessibilityIdentifier(identifier(layer))
                        }
                    }
                }
                if session.selectedLayer != nil {
                    ScrollView(.horizontal) {
                        HStack(spacing: 12) {
                            action("Move Left", "arrow.left") { session.moveSelectedLayer(x: -10, y: 0) }
                            action("Move Right", "arrow.right") { session.moveSelectedLayer(x: 10, y: 0) }
                            action("Move Up", "arrow.up") { session.moveSelectedLayer(x: 0, y: -10) }
                            action("Move Down", "arrow.down") { session.moveSelectedLayer(x: 0, y: 10) }
                            action("Make Larger", "plus.magnifyingglass") { session.resizeSelectedLayer(by: 1.1) }
                            action("Make Smaller", "minus.magnifyingglass") { session.resizeSelectedLayer(by: 1 / 1.1) }
                            action("Rotate Clockwise", "rotate.right") { session.rotateSelectedLayer(by: .pi / 18) }
                            if let selected = session.selectedLayer, session.text(for: selected) != nil {
                                action("Edit Bubble Text", "character.cursor.ibeam", perform: editText)
                            }
                            action("Delete Decoration", "trash") { session.removeSelectedLayer() }
                        }.padding(.horizontal, 8)
                    }
                }
            }
        }
        .disabled(!session.canEdit)
    }
    private func identifier(_ layer: CelluloidEditingSession.Layer) -> String {
        switch layer {
        case .bubble(let index): return "bubble-layer-\(index)"
        case .sticker(let index): return "sticker-layer-\(index)"
        }
    }
    private func title(_ layer: CelluloidEditingSession.Layer) -> String {
        switch layer {
        case .bubble(let index): return "\(tr(.bubble)) \(index + 1)"
        case .sticker(let index): return "\(tr(.sticker)) \(index + 1)"
        }
    }
    private func action(_ title: String, _ symbol: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) { Image(systemName: symbol).frame(minWidth: 44, minHeight: 44) }
            .accessibilityLabel(NSLocalizedString(title, bundle: extensionBundle, comment: ""))
            .accessibilityIdentifier(title == "Edit Bubble Text" ? "bubble-edit-text" : title)
    }
}
