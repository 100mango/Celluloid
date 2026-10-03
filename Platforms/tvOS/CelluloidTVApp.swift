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
    @State private var requestingPhotos = false
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
                    Button("Choose Photos") {
                        guard !requestingPhotos else { return }
                        requestingPhotos = true
                        #if DEBUG
                        print("TV_PHOTOS_BUTTON_ACTION choose entered")
                        #endif
                        Task {
                            defer { requestingPhotos = false }
                            do {
                                try await library.requestAccessAndRefresh(); panel = .photos
                                #if DEBUG
                                print("TV_PHOTOS_SHEET requested assets=\(library.assets.count)")
                                #endif
                            }
                            catch { editor.error = error.localizedDescription }
                        }
                    }.disabled(requestingPhotos).accessibilityIdentifier("tv.choose-photos")
                    if requestingPhotos { ProgressView("Waiting for Photos access…").accessibilityIdentifier("tv.photos-request-pending") }
                    Button("Reopen Kept Recipe") { Task { do { try await library.requestAccessAndRefresh(); await editor.reopen(library: library) } catch { editor.error = error.localizedDescription } } }.disabled(!editor.hasSavedRecipe).accessibilityIdentifier("tv.reopen-recipe")
                    Group {
                        Button(editor.recipe.filter.localizedTitle) { panel = .filters }.accessibilityIdentifier("tv.filters")
                        Button("Sticker") { panel = .stickers }.accessibilityIdentifier("tv.stickers")
                        Button("Bubble") { panel = .bubbles }.accessibilityIdentifier("tv.bubbles")
                        Button("Source Photos") { panel = .sources }.accessibilityIdentifier("tv.sources")
                        Button("Layers") { panel = .layers }.accessibilityIdentifier("tv.layers").disabled(editor.recipe.overlays.isEmpty)
                        Button("Undo") { editor.undo() }.accessibilityIdentifier("tv.undo").disabled(!editor.canUndo)
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
                VStack(spacing: 0) {
                    HStack {
                        Text(LocalizedStringKey(panelTitle(value))).font(.title2)
                        Spacer()
                        Button("Done") { panel = nil }.accessibilityIdentifier("tv.panel.done")
                    }.padding(.horizontal, 48).padding(.top, 30).padding(.bottom, 24).focusSection()
                    Divider()
                    ScrollView {
                        VStack(alignment: .leading, spacing: 28) {
                        switch value {
                        case .photos: TVPhotoPicker(library: library) { ids in panel = nil; Task { await editor.importPhotos(ids, library: library) } }
                            .onAppear {
                                #if DEBUG
                                print("TV_PHOTOS_SHEET appeared")
                                #endif
                            }
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
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(48)
                    }.focusSection()
                }.frame(width: 1280, height: 860)
            }
        }
        .alert("Celluloid", isPresented: Binding(get: { editor.error != nil }, set: { if !$0 { editor.error = nil } })) {
            Button("OK", role: .cancel) { editor.error = nil }
        } message: { Text(editor.error ?? "") }
    }
    private func panelTitle(_ value: Panel) -> String {
        switch value {
        case .photos: return "Choose Photos"
        case .filters: return "Filter"
        case .stickers: return "Choose a Sticker"
        case .bubbles: return "Choose a Bubble"
        case .sources: return "Source Photos"
        case .layers: return "Layers"
        case .privacy: return "Privacy Policy"
        }
    }
    private func artwork(stickers: Bool) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 40), count: 5), spacing: 40) {
            if stickers {
                ForEach(StickerAsset.all, id: \.rawValue) { asset in
                    TVAssetButton(asset: asset.rawValue, title: String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(asset.rawValue) ?? 32) - 31)) { editor.add(Overlay(sticker: asset)); panel = .layers }
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
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 36)], spacing: 36) {
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
                Text(verbatim: library.displayName(asset)).font(.caption).lineLimit(2)
                Text(order.map { String(format: NSLocalizedString("Selected %d", comment: "TV selection order"), $0) } ?? "\(asset.pixelWidth) × \(asset.pixelHeight)").font(.caption)
            }.frame(width: 260)
        }.accessibilityIdentifier("tv.photo." + asset.localIdentifier)
            .accessibilityLabel(library.displayName(asset) + ", \(asset.pixelWidth) × \(asset.pixelHeight)")
            .accessibilityValue(order.map { String(format: NSLocalizedString("Selected %d", comment: "TV selection order"), $0) } ?? "")
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
                    TVAdjustButtons(title: "Text size", identifier: "tv.layer.font-size", value: layer.fontSize, step: 0.005, range: 0.005...0.2) { value in editor.editLayer { $0.fontSize = value } }
                }
                TVAdjustButtons(title: "Horizontal position", identifier: "tv.layer.x", value: layer.centerX, step: 0.02, range: -0.5...1.5) { value in editor.editLayer { $0.centerX = value } }
                TVAdjustButtons(title: "Vertical position", identifier: "tv.layer.y", value: layer.centerY, step: 0.02, range: -0.5...1.5) { value in editor.editLayer { $0.centerY = value } }
                TVAdjustButtons(title: "Width", identifier: "tv.layer.width", value: layer.width, step: 0.02, range: 0.02...1.5) { value in editor.editLayer { $0.width = value } }
                TVAdjustButtons(title: "Height", identifier: "tv.layer.height", value: layer.height, step: 0.02, range: 0.02...1.5) { value in editor.editLayer { $0.height = value } }
                TVAdjustButtons(title: "Rotation", identifier: "tv.layer.rotation", value: layer.rotation, step: 15, range: -180...180) { value in editor.editLayer { $0.rotation = value } }
                Button { editor.editLayer { $0.mirrored.toggle() } } label: {
                    Text("Mirror layer").frame(maxWidth: .infinity, alignment: .leading)
                }.accessibilityIdentifier("tv.layer.mirror")
                    .accessibilityValue(layer.mirrored ? NSLocalizedString("On", comment: "Mirror state") : NSLocalizedString("Off", comment: "Mirror state"))
                Button(role: .destructive) { editor.change { $0.overlays.removeAll { $0.id == layer.id } }; editor.selectedLayer = nil } label: {
                    Text("Delete Layer").frame(maxWidth: .infinity, alignment: .leading)
                }
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
                    Button(template.assetName) { editor.change { $0.collageTemplate = template.assetName } }.accessibilityIdentifier("tv.template." + template.assetName)
                }
            }
            ForEach(Array(editor.recipe.sources.enumerated()), id: \.element.id) { index, source in
                Text(source.displayName).font(.headline)
                TVAdjustButtons(title: "Horizontal crop", identifier: "tv.source.\(index).crop-x", value: source.crop.centerX, step: 0.05, range: 0...1) { value in editor.change { $0.sources[index].crop.centerX = value } }
                TVAdjustButtons(title: "Vertical crop", identifier: "tv.source.\(index).crop-y", value: source.crop.centerY, step: 0.05, range: 0...1) { value in editor.change { $0.sources[index].crop.centerY = value } }
                TVAdjustButtons(title: "Zoom", identifier: "tv.source.\(index).zoom", value: source.crop.zoom, step: 0.25, range: 1...5) { value in editor.change { $0.sources[index].crop.zoom = value } }
                Button("Reset Crop") { editor.change { $0.sources[index].crop = SourceCrop() } }.accessibilityIdentifier("tv.source.\(index).reset")
                Button("Earlier") { editor.change { $0.sources.swapAt(index, index - 1) } }.disabled(index == 0).accessibilityIdentifier("tv.source.\(index).earlier")
                Button("Later") { editor.change { $0.sources.swapAt(index, index + 1) } }.disabled(index == editor.recipe.sources.count - 1).accessibilityIdentifier("tv.source.\(index).later")
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
    var identifier: String = ""
    let value: Double, step: Double
    let range: ClosedRange<Double>
    let change: (Double) -> Void
    var body: some View {
        HStack(spacing: 30) {
            Text(LocalizedStringKey(title)).frame(maxWidth: .infinity, alignment: .leading)
            Text(value, format: .number.precision(.fractionLength(2))).monospacedDigit().frame(width: 110, alignment: .trailing)
            Button("−") { change(max(range.lowerBound, value - step)) }.frame(width: 90).accessibilityLabel(String(format: NSLocalizedString("Decrease %@", comment: "TV focus"), NSLocalizedString(title, comment: "Property"))).accessibilityIdentifier(identifier + ".decrease")
            Button("+") { change(min(range.upperBound, value + step)) }.frame(width: 90).accessibilityLabel(String(format: NSLocalizedString("Increase %@", comment: "TV focus"), NSLocalizedString(title, comment: "Property"))).accessibilityIdentifier(identifier + ".increase")
        }.frame(maxWidth: .infinity).focusSection()
    }
}
