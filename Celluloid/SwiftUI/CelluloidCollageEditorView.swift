import CelluloidKit
import Photos
import SwiftUI
import UIKit

@MainActor
struct CelluloidCollageEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var session: CelluloidCollageSession

    init(assets: [PHAsset]) {
        _session = StateObject(wrappedValue: CelluloidCollageSession(assets: assets))
    }

    var body: some View {
        NavigationView {
            ZStack {
                if let image = session.savedImage {
                    CelluloidSavedPhotoView(image: image, onDone: cancelAndDismiss)
                } else {
                    CelluloidCollageContent(session: session)
                }
            }
            .navigationTitle(session.savedImage == nil ? tr(.collage) : "")
            .navigationBarTitleDisplayMode(.inline)
            .navigationBarBackButtonHidden(session.savedImage != nil)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if session.savedImage == nil {
                        Button(tr(.cancel), action: cancelAndDismiss)
                            .disabled(session.saving)
                            .accessibilityIdentifier("collage-cancel")
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if session.savedImage == nil {
                        Button(tr(.done), action: session.save)
                            .accessibilityIdentifier("collage-done")
                            .disabled(!session.ready || session.saving)
                    }
                }
            }
            .overlay {
                if session.saving {
                    ProgressView().padding().background(.regularMaterial).cornerRadius(12)
                }
            }
            .alert("", isPresented: $session.showingMinimumPhotoAlert) {
                Button(tr(.done), role: .cancel) {}
            } message: {
                Text(NSLocalizedString("A collage needs at least two photos.", comment: "Minimum collage selection"))
            }
            .alert(NSLocalizedString("Collage", comment: ""), isPresented: Binding(
                get: { session.error != nil }, set: { if !$0 { session.error = nil } })) {
                    Button(tr(.done), role: .cancel) { session.error = nil }
                    if !session.ready {
                        Button(NSLocalizedString("Retry", comment: ""), action: session.load)
                    }
                } message: { Text(session.error ?? "") }
        }
        .navigationViewStyle(.stack)
        .onAppear(perform: session.load)
        .onDisappear { if !session.saving { session.cancel() } }
    }

    private func cancelAndDismiss() {
        guard !session.saving else { return }
        session.cancel()
        dismiss()
    }
}

/// Match the original safe-area stack: 80-point thumbnails, square canvas,
/// and 120-point styles, with the remaining space divided into two equal gaps.
/// Stable representable identities retain the low-level views during rotation.
@MainActor
private struct CelluloidCollageContent: View {
    @ObservedObject var session: CelluloidCollageSession

    var body: some View {
        GeometryReader { geometry in
            let layout = CelluloidCollageLayout(size: geometry.size)
            ZStack(alignment: .topLeading) {
                CelluloidArrangedPhotos(session: session)
                    .frame(width: layout.arranged.width, height: layout.arranged.height)
                    .position(x: layout.arranged.midX, y: layout.arranged.midY)
                CelluloidCollageCanvas(session: session)
                    .frame(width: layout.canvas.width, height: layout.canvas.height)
                    .position(x: layout.canvas.midX, y: layout.canvas.midY)
                CelluloidCollageStyles(session: session, horizontal: layout.horizontal)
                    .frame(width: layout.styles.width, height: layout.styles.height)
                    .position(x: layout.styles.midX, y: layout.styles.midY)
            }
        }
        .background(Color.white)
    }
}

private struct CelluloidCollageLayout {
    let horizontal: Bool
    let arranged: CGRect
    let canvas: CGRect
    let styles: CGRect

    init(size: CGSize) {
        horizontal = size.width > size.height
        let side = max(1, min(size.width - (horizontal ? 200 : 0),
                              size.height - (horizontal ? 0 : 200)))
        if horizontal {
            let gap = max(0, (size.width - 200 - side) / 2)
            arranged = CGRect(x: 0, y: 0, width: 80, height: size.height)
            canvas = CGRect(x: 80 + gap, y: (size.height - side) / 2, width: side, height: side)
            styles = CGRect(x: size.width - 120, y: 0, width: 120, height: size.height)
        } else {
            let gap = max(0, (size.height - 200 - side) / 2)
            arranged = CGRect(x: 0, y: 0, width: size.width, height: 80)
            canvas = CGRect(x: (size.width - side) / 2, y: 80 + gap, width: side, height: side)
            styles = CGRect(x: 0, y: size.height - 120, width: size.width, height: 120)
        }
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
    @Published var showingMinimumPhotoAlert = false
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
    // The original panel edits its ordered array during interactive movement.
    // Keep those same PhotoModel instances so each source retains its crop/zoom.
    func applyArrangedPhotos(_ models: [PhotoModel]) {
        guard ready, !saving, (2...4).contains(models.count) else { return }
        let countChanged = photos.count != models.count
        photos = models
        if !photos.contains(where: { $0.asset.localIdentifier == selectedID }) {
            selectedID = photos.first?.asset.localIdentifier
        }
        if countChanged { refreshTemplates() }
        revision = UUID()
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

/// Reuse the shipped thumbnail cells and collection-view long-press movement.
@MainActor
private struct CelluloidArrangedPhotos: UIViewRepresentable {
    @ObservedObject var session: CelluloidCollageSession

    func makeCoordinator() -> Coordinator { Coordinator(session: session) }
    func makeUIView(context: Context) -> ImageArrangedPanel {
        let panel = ImageArrangedPanel(models: session.photos)
        panel.delegate = context.coordinator
        panel.onMinimumPhotoCountReached = { [weak coordinator = context.coordinator] in
            coordinator?.session.showingMinimumPhotoAlert = true
        }
        return panel
    }
    func updateUIView(_ panel: ImageArrangedPanel, context: Context) {
        context.coordinator.session = session
        // The panel already performed a drag/delete before notifying SwiftUI.
        // Avoid reloading it in the middle of its interactive movement animation.
        let sourcesChanged = panel.photoModels.map({ $0.asset.localIdentifier }) != session.photos.map({ $0.asset.localIdentifier })
        if sourcesChanged { panel.photoModels = session.photos }
        if sourcesChanged || (session.ready && !context.coordinator.wasReady) {
            // Also repopulate thumbnails after a failed load succeeds on retry.
            panel.reload()
        }
        context.coordinator.wasReady = session.ready
        panel.isUserInteractionEnabled = session.ready && !session.saving
    }
    static func dismantleUIView(_ panel: ImageArrangedPanel, coordinator: Coordinator) {
        panel.delegate = nil
        panel.onMinimumPhotoCountReached = nil
    }

    @MainActor
    final class Coordinator: NSObject, ImageArrangedPanelDelegate {
        var session: CelluloidCollageSession
        var wasReady = false
        init(session: CelluloidCollageSession) { self.session = session }
        func imageArrangedPanel(_ panel: ImageArrangedPanel, didEditModels models: [PhotoModel]) {
            session.applyArrangedPhotos(models)
        }
    }
}

/// Reuse the original layout thumbnails, insets, and selected-cell mask.
@MainActor
private struct CelluloidCollageStyles: UIViewRepresentable {
    @ObservedObject var session: CelluloidCollageSession
    let horizontal: Bool

    func makeCoordinator() -> Coordinator { Coordinator(session: session) }
    func makeUIView(context: Context) -> CollageStylePanel {
        let panel = CollageStylePanel(models: session.templates)
        panel.delegate = context.coordinator
        return panel
    }
    func updateUIView(_ panel: CollageStylePanel, context: Context) {
        context.coordinator.session = session
        if panel.collageModels.map(\.imageName) != session.templates.map(\.imageName) {
            panel.collageModels = session.templates
        }
        let direction: UICollectionView.ScrollDirection = horizontal ? .vertical : .horizontal
        if panel.scrollDirection != direction {
            panel.scrollDirection = direction
            panel.reload()
        }
        panel.isUserInteractionEnabled = session.ready && !session.saving
    }
    static func dismantleUIView(_ panel: CollageStylePanel, coordinator: Coordinator) {
        panel.delegate = nil
    }

    @MainActor
    final class Coordinator: NSObject, CollageStylePanelDelegate {
        var session: CelluloidCollageSession
        init(session: CelluloidCollageSession) { self.session = session }
        func collageStylePanel(_ panel: CollageStylePanel, didSelctModel model: CollageModel) {
            guard let index = session.templates.firstIndex(where: { $0.imageName == model.imageName }) else { return }
            session.selectTemplate(index)
        }
    }
}

@MainActor
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
