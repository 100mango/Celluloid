import SwiftUI

@MainActor
public struct CelluloidEditorContent: View {
    @ObservedObject private var session: CelluloidEditingSession
    @StateObject private var presentation: CelluloidEditorPresentation
    public init(session: CelluloidEditingSession) {
        self.session = session
        _presentation = StateObject(wrappedValue: CelluloidEditorPresentation())
    }
    #if DEBUG
    init(session: CelluloidEditingSession, presentation: CelluloidEditorPresentation) {
        self.session = session
        _presentation = StateObject(wrappedValue: presentation)
    }
    #endif

    public var body: some View {
        VStack(spacing: 0) {
            CelluloidEditorCanvas(session: session, editText: textEditorAction)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .overlay(alignment: .center) {
                    if session.previewIsLoading || session.phase == .loading || session.phase == .empty {
                        ProgressView().tint(.white)
                    }
                }
            if session.isReadOnly {
                Text(tr(.unreadableEditsMessage)).font(.body).multilineTextAlignment(.center).padding()
                    .background(Color(uiColor: .systemBackground))
                    .accessibilityIdentifier("read-only-adjustment")
            } else {
                CelluloidOriginalToolBar(selected: presentation.selectedTool, select: presentTool)
                    .disabled(!session.canEdit)
            }
        }
        .background(Color(uiColor: .blackBackgroundColor))
        .sheet(item: $presentation.sheet, onDismiss: { session.isPresentingTool = false }) { selected in
            CelluloidEditorSheet(sheet: selected, session: session)
        }
        .fullScreenCover(item: $presentation.fullScreenSheet, onDismiss: { session.isPresentingTool = false }) { selected in
            CelluloidEditorSheet(sheet: selected, session: session)
        }
        .onChange(of: session.sessionIdentity) { _ in
            presentation.sheet = nil; presentation.fullScreenSheet = nil; presentation.selectedTool = nil
        }
        .alert(session.isReadOnly ? tr(.unreadableEditsTitle) : NSLocalizedString("Photo Editor", comment: ""), isPresented: Binding(
            get: { session.notice != nil }, set: { if !$0 { session.notice = nil } })) {
                Button(tr(.done), role: .cancel) { session.notice = nil }
            } message: { Text(session.notice ?? "") }
    }
    private func presentTool(_ selected: EditorSheet) {
        guard session.canEdit else { return }
        presentation.selectedTool = selected.id
        session.isPresentingTool = true
        // Original filter, sticker and bubble style pickers are form sheets.
        // Editing an existing bubble retains the original full-screen focus task.
        presentation.sheet = selected
    }
    private var textEditorAction: (CelluloidEditingSession.Layer, String, UUID) -> Void {
        // The session owns its low-level canvas. Do not store a SwiftUI Binding
        // in that canvas: a Binding can retain the presentation graph that owns
        // the observed session even when a separate session capture is weak.
        return { [weak session, weak presentation] layer, text, token in
            guard let session = session, let presentation = presentation,
                  session.canEdit, session.sessionIdentity == token else { return }
            session.selectedLayer = layer
            session.isPresentingTool = true
            presentation.fullScreenSheet = .text(layer, text, token)
        }
    }
}

/// Independently owned by SwiftUI. It contains only route values, never the
/// session or canvas, and native callbacks hold this target weakly.
@MainActor
final class CelluloidEditorPresentation: ObservableObject {
    @Published var sheet: EditorSheet?
    @Published var fullScreenSheet: EditorSheet?
    @Published var selectedTool: String?
}

/// Reproduces the shipped toolbar's three equal-width items, template assets,
/// 22-point icon, caption font, one-point gap and translucent black surface.
private struct CelluloidOriginalToolBar: View {
    let selected: String?
    let select: (EditorSheet) -> Void
    var body: some View {
        HStack(alignment: .center, spacing: 0) {
            item(.filter, title: tr(.filter), asset: "filterButton", identifier: "tool-filter")
            item(.bubble, title: tr(.bubble), asset: "bubbleButton", identifier: "tool-bubble")
            item(.sticker, title: tr(.sticker), asset: "stickerButton", identifier: "tool-sticker")
        }
        .background(Color(uiColor: .alphaBlackColor))
    }
    private func item(_ tool: EditorSheet, title: String, asset: String, identifier: String) -> some View {
        Button { select(tool) } label: {
            VStack(spacing: 1) {
                Image(asset, bundle: extensionBundle).renderingMode(.template)
                    .resizable().frame(width: 22, height: 22)
                Text(title).font(.caption).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
            .foregroundColor(selected == tool.id ? .white : Color(uiColor: .alphaWhiteColor))
            .padding(.horizontal, 6).padding(.vertical, 4)
            .frame(maxWidth: .infinity, minHeight: 49)
            .contentShape(Rectangle())
            .overlay(alignment: .bottom) {
                if selected == tool.id { Color.white.frame(width: 22, height: 2) }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
        .accessibilityIdentifier(identifier)
    }
}
