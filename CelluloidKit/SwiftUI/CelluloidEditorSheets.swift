import SwiftUI

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
    @State private var caption = ""
    @State private var newBubbleIndex: Int?
    private let columns = [GridItem(.adaptive(minimum: 88))]
    // Exactly the five shipped choices; all historical raw values still decode.
    private let filters = [
        EditorFilterOption(filter: .Original, title: "Original", asset: "OriginalFilter"),
        EditorFilterOption(filter: .Sepia, title: "Sepia", asset: "OldPictureFilter"),
        EditorFilterOption(filter: .Posterize, title: "Posterize", asset: "PosterizeFilter"),
        EditorFilterOption(filter: .Crystal, title: "Crystal", asset: "CrystalFilter"),
        EditorFilterOption(filter: .PixellateFace, title: "Pixelate Faces", asset: "PixellateFaceFilter")]

    var body: some View {
        NavigationView {
            GeometryReader { geometry in
                ScrollView {
                    switch sheet {
                    case .filter:
                        filterGrid
                    case .bubble:
                        if newBubbleIndex != nil { captionEditor(height: geometry.size.height) }
                        else { bubbleGrid }
                    case .sticker:
                        stickerGrid
                    case .text(_, let initial, _):
                        captionEditor(height: geometry.size.height).onAppear { caption = initial }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(tr(.cancel)) { dismiss() }
                        .accessibilityIdentifier(isCaptionEditor ? "bubble-text-cancel" : "editor-picker-cancel")
                }
                if case .text(let layer, _, let token) = sheet {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(tr(.done)) {
                            session.updateText(caption, layer: layer, session: token); dismiss()
                        }.accessibilityIdentifier("bubble-text-done")
                    }
                }
                if case .bubble = sheet, let index = newBubbleIndex {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(tr(.done)) {
                            var bubble = BubbleModel.bubbles[index]
                            bubble.content = caption; session.addBubble(bubble); dismiss()
                        }.accessibilityIdentifier("bubble-text-done")
                    }
                }
            }
        }.navigationViewStyle(.stack)
    }
    private var filterGrid: some View {
        LazyVGrid(columns: columns, spacing: 16) {
            ForEach(filters) { option in
                Button { session.selectFilter(option.filter); dismiss() } label: {
                    VStack {
                        Image(option.asset, bundle: extensionBundle).resizable().scaledToFit().frame(height: 72)
                        Text(NSLocalizedString(option.title, bundle: extensionBundle, comment: ""))
                        if session.adjustment.filterType == option.filter { Image(systemName: "checkmark.circle.fill") }
                    }.frame(minHeight: 100)
                }.accessibilityIdentifier("filter-\(option.id)")
            }
        }.padding()
    }
    private var bubbleGrid: some View {
        LazyVGrid(columns: columns, spacing: 16) {
            ForEach(BubbleModel.bubbles.indices, id: \.self) { index in
                Button { caption = ""; newBubbleIndex = index } label: {
                    Image(uiImage: BubbleModel.bubbles[index].bubbleImage).resizable().scaledToFit().frame(height: 88)
                }.accessibilityLabel("\(tr(.bubble)) \(index + 1)")
                    .accessibilityIdentifier("bubble-option-\(index)")
            }
        }.padding()
    }
    private var stickerGrid: some View {
        LazyVGrid(columns: columns, spacing: 16) {
            ForEach(StickerModel.stickers.indices, id: \.self) { index in
                Button { session.addSticker(StickerModel.stickers[index]); dismiss() } label: {
                    Image(uiImage: StickerModel.stickers[index].stickerImage).resizable().scaledToFit().frame(height: 88)
                }.accessibilityLabel("\(tr(.sticker)) \(index + 1)")
                    .accessibilityIdentifier("sticker-option-\(index)")
            }
        }.padding()
    }
    private func captionEditor(height: CGFloat) -> some View {
        TextEditor(text: $caption)
            .frame(maxWidth: 720)
            .frame(height: max(120, height - 20))
            .padding(10)
            .frame(maxWidth: .infinity)
            .accessibilityLabel(NSLocalizedString("Bubble Text", bundle: extensionBundle, comment: "Editable bubble caption"))
            .accessibilityIdentifier("bubble-text")
    }
    private var isCaptionEditor: Bool {
        if case .text = sheet { return true }
        return newBubbleIndex != nil
    }
    private var title: String {
        if isCaptionEditor { return NSLocalizedString("Edit Bubble Text", comment: "") }
        switch sheet {
        case .filter: return tr(.filter)
        case .bubble: return tr(.bubble)
        case .sticker: return tr(.sticker)
        case .text: return NSLocalizedString("Edit Bubble Text", comment: "")
        }
    }
}
