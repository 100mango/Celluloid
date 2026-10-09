import SwiftUI
import UIKit

enum EditorSheet: Identifiable {
    case filter, bubble, sticker, text(CelluloidEditingSession.Layer, String, UUID)
    var id: String {
        switch self { case .filter: return "filter"; case .bubble: return "bubble"; case .sticker: return "sticker"; case .text: return "text" }
    }
}

private struct EditorFilterOption: Identifiable {
    let filter: FilterType
    let title: String
    let asset: String
    var id: String { filter.rawValue }
}

@MainActor
struct CelluloidEditorSheet: View {
    let sheet: EditorSheet
    @ObservedObject var session: CelluloidEditingSession
    @Environment(\.dismiss) private var dismiss
    @State private var sessionToken: UUID
    private let columns = [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)]
    private let filters = [
        EditorFilterOption(filter: .Original, title: "Original", asset: "OriginalFilter"),
        EditorFilterOption(filter: .Sepia, title: "Sepia", asset: "OldPictureFilter"),
        EditorFilterOption(filter: .Posterize, title: "Posterize", asset: "PosterizeFilter"),
        EditorFilterOption(filter: .Crystal, title: "Crystal", asset: "CrystalFilter"),
        EditorFilterOption(filter: .PixellateFace, title: "Pixelate Faces", asset: "PixellateFaceFilter")]
    init(sheet: EditorSheet, session: CelluloidEditingSession) {
        self.sheet = sheet; self.session = session
        _sessionToken = State(initialValue: session.sessionIdentity)
    }
    var body: some View {
        NavigationView {
            Group {
                if case .text(let layer, let text, let token) = sheet {
                    CelluloidCaptionEditor(initialText: text, cancel: { dismiss() }) { caption in
                        session.updateText(caption, layer: layer, session: token); dismiss()
                    }
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 10) {
                            pickerItems
                        }.padding(10)
                    }
                    .background(Color.white)
                    .navigationTitle(title)
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button(tr(.cancel)) { dismiss() }.accessibilityIdentifier("editor-picker-cancel")
                        }
                    }
                    .background(CelluloidSheetChrome())
                }
            }
        }.navigationViewStyle(.stack)
    }
    @ViewBuilder private var pickerItems: some View {
        switch sheet {
        case .filter:
            ForEach(filters) { option in
                Button {
                    guard session.sessionIdentity == sessionToken else { return }
                    session.selectFilter(option.filter); dismiss()
                } label: {
                    Image(option.asset, bundle: extensionBundle).resizable().aspectRatio(1, contentMode: .fit)
                        .background(Color(uiColor: .cellLightPurple))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(NSLocalizedString(option.title, bundle: extensionBundle, comment: ""))
                .accessibilityIdentifier("filter-\(option.id)")
            }
        case .bubble:
            ForEach(BubbleModel.bubbles.indices, id: \.self) { index in
                NavigationLink {
                    // Original picker pushed caption editing, so Back returns to
                    // the style grid without committing an unfinished bubble.
                    CelluloidCaptionEditor(initialText: "", cancel: nil) { caption in
                        guard session.sessionIdentity == sessionToken else { return }
                        var model = BubbleModel.bubbles[index]; model.content = caption
                        session.addBubble(model); dismiss()
                    }
                } label: {
                    pickerImage(BubbleModel.bubbles[index].bubbleImage)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(String(format: NSLocalizedString("Bubble %d", bundle: extensionBundle, comment: "Picker item"), index + 1))
                .accessibilityIdentifier("bubble-option-\(index)")
            }
        case .sticker:
            ForEach(StickerModel.stickers.indices, id: \.self) { index in
                Button {
                    guard session.sessionIdentity == sessionToken else { return }
                    session.addSticker(StickerModel.stickers[index]); dismiss()
                } label: { pickerImage(StickerModel.stickers[index].stickerImage) }
                .buttonStyle(.plain)
                .accessibilityLabel(String(format: NSLocalizedString("Sticker %d", bundle: extensionBundle, comment: "Picker item"), index + 1))
                .accessibilityIdentifier("sticker-option-\(index)")
            }
        case .text: EmptyView()
        }
    }
    private func pickerImage(_ image: UIImage) -> some View {
        Color(uiColor: .cellLightPurple).aspectRatio(1, contentMode: .fit)
            .overlay(Image(uiImage: image).resizable().scaledToFit())
    }
    private var title: String {
        switch sheet {
        case .filter: return tr(.filter)
        case .bubble: return tr(.bubble)
        case .sticker: return tr(.sticker)
        case .text: return tr(.edit)
        }
    }
}

private struct CelluloidCaptionEditor: View {
    let cancel: (() -> Void)?
    let commit: (String) -> Void
    @State private var text: String
    init(initialText: String, cancel: (() -> Void)?, commit: @escaping (String) -> Void) {
        self.cancel = cancel; self.commit = commit; _text = State(initialValue: initialText)
    }
    var body: some View {
        CelluloidCaptionTextView(text: $text)
            .frame(maxWidth: 720, maxHeight: .infinity)
            .padding(10)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.white)
            .navigationTitle(tr(.edit))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if let cancel = cancel {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(tr(.cancel), action: cancel).accessibilityIdentifier("bubble-text-cancel")
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tr(.done)) { commit(text) }.accessibilityIdentifier("bubble-text-done")
                }
            }
    }
}

/// A text-input primitive, not a controller: preserves iOS 15 background, center
/// alignment, Dynamic Type, black caret and the original text accessibility node.
private struct CelluloidCaptionTextView: UIViewRepresentable {
    @Binding var text: String
    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.delegate = context.coordinator
        view.text = text
        view.textAlignment = .center
        view.backgroundColor = .bubbleBackgroundColor
        view.textColor = .black; view.tintColor = .black
        view.font = .preferredFont(forTextStyle: .body)
        view.adjustsFontForContentSizeCategory = true
        view.accessibilityIdentifier = "bubble-text"
        view.accessibilityLabel = NSLocalizedString("Bubble Text", bundle: extensionBundle, comment: "Editable bubble caption")
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) {
        context.coordinator.text = $text
        if view.text != text { view.text = text }
    }
    final class Coordinator: NSObject, UITextViewDelegate {
        var text: Binding<String>
        init(text: Binding<String>) { self.text = text }
        func textViewDidChange(_ textView: UITextView) { text.wrappedValue = textView.text }
    }
}

/// Configures only the system sheet chrome on iOS 15; the picker remains SwiftUI.
private struct CelluloidSheetChrome: UIViewRepresentable {
    func makeUIView(context: Context) -> SheetChromeView { SheetChromeView() }
    func updateUIView(_ view: SheetChromeView, context: Context) { view.configure() }
}
private final class SheetChromeView: UIView {
    override func didMoveToWindow() { super.didMoveToWindow(); configure() }
    func configure() {
        DispatchQueue.main.async { [weak self] in
            var controller = self?.parentViewController
            while let current = controller {
                if current.presentingViewController != nil, let sheet = current.sheetPresentationController {
                    sheet.detents = [.medium(), .large()]
                    sheet.prefersGrabberVisible = true
                    break
                }
                controller = current.parent
            }
        }
    }
}
