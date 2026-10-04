import SwiftUI
import CelluloidDomain
import CelluloidRendering

enum AssetPanel: String, Identifiable {
    case stickers, bubbles
    var id: String { rawValue }
}

struct AssetPaletteView: View {
    @Environment(\.dismiss) private var dismiss
    let panel: AssetPanel
    let select: (Overlay) -> Void
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text(LocalizedStringKey(panel == .stickers ? "Choose a Sticker" : "Choose a Bubble")).font(.headline)
                Spacer(); Button("Done") { dismiss() }
            }
            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                    if panel == .stickers {
                        ForEach(StickerAsset.all, id: \.rawValue) { sticker in
                            AssetCell(asset: sticker.rawValue, title: String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(sticker.rawValue) ?? 32) - 31)) {
                                select(Overlay(sticker: sticker))
                            }
                        }
                    } else {
                        ForEach(BubbleAsset.allCases, id: \.rawValue) { bubble in
                            AssetCell(asset: bubble.rawValue, title: bubble.localizedTitle) { select(Overlay(bubble: bubble, text: NSLocalizedString("Hello", comment: "Default bubble text"))) }
                        }
                    }
                }.padding(2)
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(panel == .stickers ? Text("Choose a Sticker") : Text("Choose a Bubble"))
            }
        }.padding(16).frame(width: 350, height: 410)
            #if os(macOS)
            .background(NativePopoverAccessibility(label: NSLocalizedString(panel == .stickers ? "Choose a Sticker" : "Choose a Bubble", comment: "Palette presentation")).frame(width: 0, height: 0))
            #endif
            #if DEBUG && os(macOS)
            .background(NativePopoverOwnershipProbe(label: NSLocalizedString(panel == .stickers ? "Choose a Sticker" : "Choose a Bubble", comment: "Palette ownership diagnostic")).frame(width: 0, height: 0))
            #endif
            .accessibilityElement(children: .contain)
            .accessibilityLabel(panel == .stickers ? Text("Choose a Sticker") : Text("Choose a Bubble"))
    }
}

private struct AssetCell: View {
    let asset: String
    let title: String
    let action: () -> Void
    @State private var image: CGImage?
    @State private var failed = false
    var body: some View {
        Button(action: action) {
            VStack(spacing: 5) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15))
                    if let image {
                        Image(decorative: image, scale: 1).resizable().aspectRatio(contentMode: .fit).padding(5)
                    } else if failed { Image(systemName: "exclamationmark.triangle").foregroundStyle(.red) }
                    else { ProgressView() }
                }.frame(height: 72)
                Text(title).font(.caption).lineLimit(2).frame(maxWidth: .infinity)
            }.contentShape(Rectangle())
        }
        .buttonStyle(.plain).disabled(failed)
        .accessibilityLabel(title).accessibilityIdentifier("asset." + asset)
        .task(id: asset) {
            do { image = try NativeResources.image(named: asset); failed = false }
            catch { failed = true }
        }
    }
}
