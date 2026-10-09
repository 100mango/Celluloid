import CelluloidKit
import Photos
import SwiftUI

@MainActor
struct CelluloidCollageEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var session: CelluloidCollageSession
    init(assets: [PHAsset]) { _session = StateObject(wrappedValue: CelluloidCollageSession(assets: assets)) }
    var body: some View {
        NavigationView {
            VStack(spacing: 8) {
                if let image = session.savedImage {
                    CelluloidSavedPhotoView(image: image)
                } else {
                    ScrollView(.horizontal) {
                        HStack {
                            ForEach(session.photos, id: \.asset.localIdentifier) { photo in
                                Button { session.selectedID = photo.asset.localIdentifier } label: {
                                    VStack {
                                        if let image = photo.loadedImage {
                                            Image(uiImage: image).resizable().scaledToFill().frame(width: 60, height: 60).clipped()
                                        } else { ProgressView().frame(width: 60, height: 60) }
                                        if session.selectedID == photo.asset.localIdentifier { Image(systemName: "checkmark.circle.fill") }
                                    }.padding(4)
                                }.accessibilityLabel(NSLocalizedString("Select Collage Photo", comment: ""))
                            }
                        }.padding(.horizontal)
                    }
                    HStack {
                        Button { session.moveSelected(by: -1) } label: { Label(NSLocalizedString("Move Left", comment: ""), systemImage: "arrow.left") }
                        Button { session.moveSelected(by: 1) } label: { Label(NSLocalizedString("Move Right", comment: ""), systemImage: "arrow.right") }
                        Button(role: .destructive) { session.removeSelected() } label: { Image(systemName: "trash").accessibilityLabel(NSLocalizedString("Remove Photo", comment: "")) }
                    }.frame(minHeight: 44).disabled(!session.ready || session.saving)
                    GeometryReader { geometry in
                        let side = max(1, min(geometry.size.width, geometry.size.height))
                        CelluloidCollageCanvas(session: session).frame(width: side, height: side)
                            .position(x: geometry.size.width / 2, y: geometry.size.height / 2)
                    }.frame(minHeight: 100)
                    ScrollView(.horizontal) {
                        HStack {
                            ForEach(session.templates.indices, id: \.self) { index in
                                Button { session.selectTemplate(index) } label: {
                                    VStack {
                                        Image(session.templates[index].imageName).resizable().scaledToFit().frame(width: 70, height: 70)
                                        if index == session.templateIndex { Image(systemName: "checkmark.circle.fill") }
                                    }.padding(4)
                                }.accessibilityLabel("\(NSLocalizedString("Collage Layout", comment: "")) \(index + 1)")
                            }
                        }.padding(.horizontal)
                    }.disabled(!session.ready || session.saving)
                }
            }
            .navigationTitle(tr(.collage))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(session.savedImage == nil ? tr(.cancel) : tr(.done)) { session.cancel(); dismiss() }.disabled(session.saving)
                        .accessibilityIdentifier(session.savedImage == nil ? "collage-cancel" : "share-done")
                }
                ToolbarItem(placement: .confirmationAction) {
                    if session.savedImage == nil {
                        Button(tr(.done)) { session.save() }.accessibilityIdentifier("collage-done")
                            .disabled(!session.ready || session.saving)
                    }
                }
            }
            .overlay { if session.saving { ProgressView().padding().background(.regularMaterial).cornerRadius(12) } }
            .alert(NSLocalizedString("Collage", comment: ""), isPresented: Binding(
                get: { session.error != nil }, set: { if !$0 { session.error = nil } })) {
                    Button(tr(.done), role: .cancel) { session.error = nil }
                    if !session.ready { Button(NSLocalizedString("Retry", comment: "")) { session.load() } }
                } message: { Text(session.error ?? "") }
        }
        .navigationViewStyle(.stack)
        .onAppear { session.load() }
        .onDisappear { if !session.saving { session.cancel() } }
    }
}

@MainActor
final class CelluloidCollageSession: ObservableObject {
    @Published private(set) var photos: [PhotoModel]
    @Published private(set) var templates: [CollageModel] = []
    @Published private(set) var templateIndex = 0
    @Published private(set) var revision = UUID()
    @Published private(set) var ready = false
    @Published private(set) var saving = false
    @Published private(set) var savedImage: UIImage?
    @Published var selectedID: String?
    @Published var error: String?
    private var generation = UUID()
    private var loading = false
    init(assets: [PHAsset]) {
        photos = assets.map(PhotoModel.init)
        selectedID = assets.first?.localIdentifier
    }
    func load() {
        guard !loading, !ready, (2...4).contains(photos.count) else { return }
        loading = true; error = nil
        let token = UUID(); generation = token
        refreshTemplates()
        let group = DispatchGroup()
        var failure: Error?
        for photo in photos {
            group.enter()
            photo.loadImage { result in
                if case .failure(let error) = result { failure = error }
                group.leave()
            }
        }
        group.notify(queue: .main) { [weak self] in
            guard let self = self, self.generation == token else { return }
            self.loading = false
            if let failure = failure { self.error = failure.localizedDescription }
            else { self.ready = !self.templates.isEmpty; self.revision = UUID() }
        }
    }
    func moveSelected(by delta: Int) {
        guard ready, !saving, let index = photos.firstIndex(where: { $0.asset.localIdentifier == selectedID }),
              photos.indices.contains(index + delta) else { return }
        photos.swapAt(index, index + delta); revision = UUID()
    }
    func removeSelected() {
        guard ready, !saving, let index = photos.firstIndex(where: { $0.asset.localIdentifier == selectedID }) else { return }
        guard photos.count > 2 else { error = NSLocalizedString("A collage needs at least two photos.", comment: ""); return }
        photos.remove(at: index); selectedID = photos.first?.asset.localIdentifier
        refreshTemplates(); revision = UUID()
    }
    func selectTemplate(_ index: Int) {
        guard ready, !saving, templates.indices.contains(index) else { return }
        templateIndex = index; revision = UUID()
    }
    private func refreshTemplates() {
        guard let count = CollageImageCount(rawValue: photos.count) else { templates = []; return }
        templates = CollageModel.collageModels(count); templateIndex = 0
    }
    func save() {
        guard ready, !saving, templates.indices.contains(templateIndex), photos.allSatisfy({ $0.loadedImage != nil }) else { return }
        saving = true
        // Preserve the shipped 800-point collage raster and crop/zoom semantics.
        // This is a bounded low-level canvas snapshot, never a controller screen.
        let holder = UIView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        let canvas = CollageView(frame: holder.bounds)
        holder.addSubview(canvas)
        canvas.setupWithCollageModel(templates[templateIndex], photoModels: photos, forEdit: false)
        canvas.layoutIfNeeded()
        let image = holder.render()
        PHPhotoLibrary.shared().performChanges({
            PHAssetChangeRequest.creationRequestForAsset(from: image).creationDate = Date()
        }) { [weak self] success, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.saving = false
                if success { self.savedImage = image }
                else { self.error = error?.localizedDescription ?? NSLocalizedString("The collage could not be saved.", comment: "") }
            }
        }
    }
    func cancel() { generation = UUID(); loading = false }
}

private struct CelluloidCollageCanvas: UIViewRepresentable {
    @ObservedObject var session: CelluloidCollageSession
    func makeUIView(context: Context) -> CelluloidCollageSurface { CelluloidCollageSurface() }
    func updateUIView(_ view: CelluloidCollageSurface, context: Context) {
        guard session.ready, session.templates.indices.contains(session.templateIndex) else { return }
        if view.revision != session.revision {
            view.canvas.setupWithCollageModel(session.templates[session.templateIndex], photoModels: session.photos)
            view.revision = session.revision
        }
        view.isUserInteractionEnabled = !session.saving
        view.setNeedsLayout()
    }
}
private final class CelluloidCollageSurface: UIView {
    let canvas = CollageView()
    var revision: UUID?
    override init(frame: CGRect) { super.init(frame: frame); addSubview(canvas) }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    override func layoutSubviews() { super.layoutSubviews(); canvas.frame = bounds; canvas.resize() }
}
