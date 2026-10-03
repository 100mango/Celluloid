import SwiftUI
import Photos
import CelluloidDomain
import CelluloidRendering

@main struct CelluloidTVApp: App {
    var body: some Scene { WindowGroup { TVEditorView() } }
}

struct TVEditorView: View {
    @StateObject private var library = TVPhotoLibrary()
    @StateObject private var editor = TVEditorModel()
    @State private var panel: Panel?
    enum Panel: String, Identifiable { case photos, filters, stickers, bubbles, sources, layers, privacy; var id: String { rawValue } }
    var body: some View {
        HStack(spacing: 40) {
            VStack(spacing: 20) {
                Text("Celluloid").font(.largeTitle)
                if let preview = editor.preview {
                    Image(preview, scale: 1, label: Text("Edited photo preview"))
                        .resizable().aspectRatio(contentMode: .fit).accessibilityIdentifier("tv.preview")
                } else {
                    Image(systemName: "photo.on.rectangle").font(.system(size: 90))
                    Text("Choose one photo to edit, or 2–4 for a collage.").multilineTextAlignment(.center)
                }
                Text(editor.status).font(.callout).accessibilityIdentifier("tv.status")
                if editor.busy { ProgressView() }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Button("Choose Photos") { Task { do { try await library.requestAccessAndRefresh(); panel = .photos } catch { editor.error = error.localizedDescription } } }.accessibilityIdentifier("tv.choose-photos")
                    Button("Reopen Kept Recipe") { Task { do { try await library.requestAccessAndRefresh(); await editor.reopen(library: library) } catch { editor.error = error.localizedDescription } } }.disabled(!editor.hasSavedRecipe)
                    Group {
                        Button(editor.recipe.filter.localizedTitle) { panel = .filters }.accessibilityIdentifier("tv.filters")
                        Button("Sticker") { panel = .stickers }.accessibilityIdentifier("tv.stickers")
                        Button("Bubble") { panel = .bubbles }.accessibilityIdentifier("tv.bubbles")
                        Button("Source Photos") { panel = .sources }
                        Button("Layers") { panel = .layers }.disabled(editor.recipe.overlays.isEmpty)
                        Button("Undo") { editor.undo() }.disabled(!editor.canUndo)
                        Button("Keep Editable Recipe") { editor.keepRecipe() }.accessibilityIdentifier("tv.keep-recipe")
                        Button("Save Picture to Photos") { Task { await editor.saveToPhotos(library: library) } }.accessibilityIdentifier("tv.save-photos")
                    }.disabled(editor.recipe.sources.isEmpty || editor.busy)
                    if editor.recipe.filter == .pixellateFace { Text("Face detection can miss faces. Check the result before sharing.").font(.caption) }
                    Text("Static photos · sRGB SDR export").font(.caption)
                    Text("TV image caches can be removed by the system. Keep originals in Photos and save finished pictures to Photos.").font(.caption)
                    Button("Privacy Policy") { panel = .privacy }
                }.padding(24)
            }.frame(width: 530)
        }.padding(60)
        .sheet(item: $panel) { value in
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        Button("Done") { panel = nil }
                        switch value {
                        case .photos: TVPhotoPicker(library: library) { ids in panel = nil; Task { await editor.importPhotos(ids, library: library) } }
                        case .filters:
                            ForEach(FilterPreset.allCases, id: \.rawValue) { filter in
                                Button(filter.localizedTitle) { editor.change { $0.filter = filter }; panel = nil }.accessibilityIdentifier("tv.filter." + filter.rawValue)
                            }
                        case .stickers: artwork(stickers: true)
                        case .bubbles: artwork(stickers: false)
                        case .sources: TVSourceControls(editor: editor)
                        case .layers: TVLayerControls(editor: editor)
                        case .privacy:
                            Text(Bundle.main.url(forResource: "PrivacyPolicy", withExtension: "txt").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? "https://100mango.github.io/app-privacy/")
                                .font(.body)
                            Text("https://100mango.github.io/app-privacy/").font(.callout)
                        }
                    }.padding(70)
                }
            }
        }
        .alert("Celluloid", isPresented: Binding(get: { editor.error != nil }, set: { if !$0 { editor.error = nil } })) {
            Button("OK", role: .cancel) { editor.error = nil }
        } message: { Text(editor.error ?? "") }
    }
    private func artwork(stickers: Bool) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 40), count: 5), spacing: 40) {
            if stickers {
                ForEach(StickerAsset.all, id: \.rawValue) { asset in
                    TVAssetButton(asset: asset.rawValue, title: "Sticker \((Int(asset.rawValue) ?? 32) - 31)") { editor.add(Overlay(sticker: asset)); panel = .layers }
                }
            } else {
                ForEach(BubbleAsset.allCases, id: \.rawValue) { asset in
                    TVAssetButton(asset: asset.rawValue, title: asset.localizedTitle) { editor.add(Overlay(bubble: asset, text: NSLocalizedString("Hello", comment: "Bubble"))); panel = .layers }
                }
            }
        }
    }
}

private struct TVAssetButton: View {
    let asset: String, title: String
    let action: () -> Void
    @State private var image: CGImage?
    var body: some View {
        Button(action: action) {
            VStack {
                if let image { Image(decorative: image, scale: 1).resizable().aspectRatio(contentMode: .fit).frame(height: 130) }
                Text(title).font(.caption)
            }.frame(width: 180, height: 190)
        }.accessibilityIdentifier("tv.asset." + asset).task { image = try? NativeResources.image(named: asset) }
    }
}

private struct TVPhotoPicker: View {
    @ObservedObject var library: TVPhotoLibrary
    let choose: ([String]) -> Void
    @State private var selected: [String] = []
    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            Text("Choose Photos").font(.title)
            Text("Up to 200 recent photos. Select one to four in the order you want.").font(.callout)
            Button("Edit Selected Photos (\(selected.count))") { choose(selected) }.disabled(selected.isEmpty).accessibilityIdentifier("tv.edit-selected")
            if library.assets.isEmpty { Text("No pictures are available. Add photos to Photos, then choose Photos again.") }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 36), count: 5), spacing: 36) {
                ForEach(library.assets, id: \.localIdentifier) { asset in
                    TVPhotoCell(asset: asset, library: library, order: selected.firstIndex(of: asset.localIdentifier).map { $0 + 1 }) {
                        if let index = selected.firstIndex(of: asset.localIdentifier) { selected.remove(at: index) }
                        else if selected.count < 4 { selected.append(asset.localIdentifier) }
                    }
                }
            }
        }
    }
}
private struct TVPhotoCell: View {
    let asset: PHAsset
    @ObservedObject var library: TVPhotoLibrary
    let order: Int?
    let select: () -> Void
    @State private var image: CGImage?
    var body: some View {
        Button(action: select) {
            VStack {
                if let image { Image(decorative: image, scale: 1).resizable().aspectRatio(contentMode: .fit).frame(height: 160) }
                else { Image(systemName: "photo").frame(height: 160) }
                Text(order.map { "Selected \($0)" } ?? "\(asset.pixelWidth) × \(asset.pixelHeight)").font(.caption)
            }.frame(width: 260)
        }.accessibilityIdentifier("tv.photo." + asset.localIdentifier)
            .task(id: asset.localIdentifier) { image = await library.thumbnail(asset) }
    }
}

private struct TVLayerControls: View {
    @ObservedObject var editor: TVEditorModel
    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            Text("Layers").font(.title)
            ForEach(editor.recipe.overlays) { layer in
                Button(layer.kind == .bubble ? layer.text : layer.asset) { editor.selectedLayer = layer.id }
            }
            if let layer = editor.recipe.overlays.first(where: { $0.id == editor.selectedLayer }) {
                if layer.kind == .bubble {
                    TextField("Bubble text", text: Binding(get: { layer.text }, set: { text in editor.editLayer { $0.text = text } })).accessibilityIdentifier("tv.bubble-text")
                    TVAdjustButtons(title: "Text size", value: layer.fontSize, step: 0.005, range: 0.005...0.2) { value in editor.editLayer { $0.fontSize = value } }
                }
                TVAdjustButtons(title: "Horizontal position", value: layer.centerX, step: 0.02, range: -0.5...1.5) { value in editor.editLayer { $0.centerX = value } }
                TVAdjustButtons(title: "Vertical position", value: layer.centerY, step: 0.02, range: -0.5...1.5) { value in editor.editLayer { $0.centerY = value } }
                TVAdjustButtons(title: "Width", value: layer.width, step: 0.02, range: 0.02...1.5) { value in editor.editLayer { $0.width = value } }
                TVAdjustButtons(title: "Height", value: layer.height, step: 0.02, range: 0.02...1.5) { value in editor.editLayer { $0.height = value } }
                TVAdjustButtons(title: "Rotation", value: layer.rotation, step: 15, range: -180...180) { value in editor.editLayer { $0.rotation = value } }
                Button("Mirror layer") { editor.editLayer { $0.mirrored.toggle() } }
                Button("Delete Layer", role: .destructive) { editor.change { $0.overlays.removeAll { $0.id == layer.id } }; editor.selectedLayer = nil }
            }
        }
    }
}
private struct TVSourceControls: View {
    @ObservedObject var editor: TVEditorModel
    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            if editor.recipe.sources.count > 1 {
                ForEach((try? NativeResources.templates(count: editor.recipe.sources.count)) ?? [], id: \.assetName) { template in
                    Button(template.assetName) { editor.change { $0.collageTemplate = template.assetName } }
                }
            }
            ForEach(Array(editor.recipe.sources.enumerated()), id: \.element.id) { index, source in
                Text(source.displayName).font(.headline)
                TVAdjustButtons(title: "Horizontal crop", value: source.crop.centerX, step: 0.05, range: 0...1) { value in editor.change { $0.sources[index].crop.centerX = value } }
                TVAdjustButtons(title: "Vertical crop", value: source.crop.centerY, step: 0.05, range: 0...1) { value in editor.change { $0.sources[index].crop.centerY = value } }
                TVAdjustButtons(title: "Zoom", value: source.crop.zoom, step: 0.25, range: 1...5) { value in editor.change { $0.sources[index].crop.zoom = value } }
                Button("Reset Crop") { editor.change { $0.sources[index].crop = SourceCrop() } }
                Button("Earlier") { editor.change { $0.sources.swapAt(index, index - 1) } }.disabled(index == 0)
                Button("Later") { editor.change { $0.sources.swapAt(index, index + 1) } }.disabled(index == editor.recipe.sources.count - 1)
                Button("Remove Photo", role: .destructive) {
                    editor.change { next in
                        next.sources.remove(at: index)
                        do { try TVEditorModel.configureCanvas(&next) } catch { editor.error = error.localizedDescription }
                    }
                }.disabled(editor.recipe.sources.count <= 1)
            }
        }
    }
}
private struct TVAdjustButtons: View {
    let title: String
    let value: Double, step: Double
    let range: ClosedRange<Double>
    let change: (Double) -> Void
    var body: some View {
        HStack(spacing: 30) {
            Text(LocalizedStringKey(title)); Text(value, format: .number.precision(.fractionLength(2)))
            Button("−") { change(max(range.lowerBound, value - step)) }.accessibilityLabel(String(format: NSLocalizedString("Decrease %@", comment: "TV focus"), NSLocalizedString(title, comment: "Property")))
            Button("+") { change(min(range.upperBound, value + step)) }.accessibilityLabel(String(format: NSLocalizedString("Increase %@", comment: "TV focus"), NSLocalizedString(title, comment: "Property")))
        }
    }
}
