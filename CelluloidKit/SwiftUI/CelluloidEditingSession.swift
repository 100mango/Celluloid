import Combine
import Photos
import UIKit

/// Owns one immutable source identity and the reversible 1.0 edit recipe.
/// Every UI mutation is main-actor isolated; decode, preview and export are asynchronous.
@MainActor
public final class CelluloidEditingSession: ObservableObject {
    public enum Phase: Equatable { case empty, loading, ready, readOnly, failed }
    public enum Layer: Hashable, Identifiable {
        case bubble(Int), sticker(Int)
        public var id: Self { self }
    }
    @Published public private(set) var phase: Phase = .empty
    @Published public private(set) var adjustment = AdjustmentData()
    @Published public private(set) var previewImage: UIImage?
    @Published public private(set) var previewIsLoading = false
    @Published public private(set) var isExporting = false
    @Published public var selectedLayer: Layer?
    @Published public var notice: String?
    @Published public private(set) var revision = UUID()
    public var isPresentingTool = false
    private(set) var canvasIdentity = UUID()
    public private(set) var input: PHContentEditingInput?
    public private(set) var preservedAdjustmentData: PHAdjustmentData?
    public private(set) var sourceImage: UIImage?
    private let previewPipeline = LegacyFilterPreviewPipeline()
    private let exporter = PhotoExportService()
    let canvas = CelluloidCanvasSurface()
    private var pendingReadOnlyPreview: UIImage?
    private var generation = UUID()
    private var previewGeneration = UUID()
    private var exportGeneration = UUID()
    private var activeExport: PhotoExportTask?
    private static let decodeQueue = DispatchQueue(label: "Mango.Celluloid.swiftui.adjustment", qos: .userInitiated)

    public init() {}
    public var isReadOnly: Bool { phase == .readOnly }
    public var canEdit: Bool { phase == .ready && !isExporting }
    public var layers: [Layer] {
        adjustment.bubbles.indices.map(Layer.bubble) + adjustment.stickers.indices.map(Layer.sticker)
    }

    public func start(input: PHContentEditingInput, placeholder: UIImage?) {
        reset()
        self.input = input
        sourceImage = input.displaySizeImage ?? placeholder
        previewImage = sourceImage
        phase = .loading
        guard sourceImage != nil else { phase = .failed; notice = NSLocalizedString("The photo could not be loaded.", comment: ""); return }
        guard let archived = input.adjustmentData else { phase = .ready; renderPreview(); return }
        let token = generation
        let bytes = archived.data, identifier = archived.formatIdentifier, version = archived.formatVersion
        Self.decodeQueue.async { [weak self] in
            let decoded = Result { () throws -> AdjustmentData in
                guard AdjustmentData.supportIdentifier(identifier, version: version) else {
                    throw AdjustmentDataError.invalidValue("bound adjustment format")
                }
                return try AdjustmentData.decode(bytes)
            }
            DispatchQueue.main.async {
                guard let self = self, self.generation == token, self.input === input else { return }
                switch decoded {
                case .success(let recipe):
                    self.adjustment = recipe
                    self.revision = UUID()
                    self.phase = .ready
                    self.renderPreview()
                case .failure:
                    self.preserve(archived, currentImage: self.pendingReadOnlyPreview ?? placeholder)
                }
            }
        }
    }

    /// Explicit new-copy source only. There is no PHAsset to overwrite.
    public func startCopy(image: UIImage) {
        reset(); sourceImage = image; previewImage = image; phase = .ready; renderPreview()
    }
    public func replaceReadOnlyPreview(_ image: UIImage, for input: PHContentEditingInput) {
        guard self.input === input else { return }
        pendingReadOnlyPreview = image
        guard isReadOnly else { return }
        sourceImage = image; previewImage = image
    }
    public func preserve(_ archived: PHAdjustmentData, currentImage: UIImage?) {
        cancelExport(); previewPipeline.cancel(); previewGeneration = UUID()
        preservedAdjustmentData = archived
        adjustment = AdjustmentData(); selectedLayer = nil; revision = UUID()
        sourceImage = currentImage; previewImage = currentImage; previewIsLoading = false
        phase = .readOnly; notice = tr(.unreadableEditsMessage)
    }
    public func restore(_ recipe: AdjustmentData) {
        guard canEdit else { return }
        canvasIdentity = UUID()
        adjustment = recipe; revision = UUID(); selectedLayer = nil; renderPreview()
    }
    public func selectFilter(_ filter: FilterType) {
        guard canEdit else { return }
        adjustment.filterType = filter; revision = UUID(); renderPreview()
    }
    public func establishCanvas(_ size: CGSize, revision: UUID) {
        guard self.revision == revision, canEdit, adjustment.referenceCanvasSize == nil,
              AdjustmentData.isValidReferenceCanvas(size) else { return }
        adjustment.referenceCanvasSize = size
        self.revision = UUID()
    }
    public func addBubble(_ model: BubbleModel) {
        guard canEdit, adjustment.referenceCanvasSize != nil else { return }
        adjustment.bubbles.append(model); selectedLayer = .bubble(adjustment.bubbles.count - 1); revision = UUID()
    }
    public func addSticker(_ model: StickerModel) {
        guard canEdit, adjustment.referenceCanvasSize != nil else { return }
        adjustment.stickers.append(model); selectedLayer = .sticker(adjustment.stickers.count - 1); revision = UUID()
    }
    public func text(for layer: Layer) -> String? {
        guard case .bubble(let index) = layer, adjustment.bubbles.indices.contains(index) else { return nil }
        return adjustment.bubbles[index].content
    }
    public func updateText(_ text: String, layer: Layer, session: UUID) {
        guard session == generation, canEdit, case .bubble(let index) = layer,
              adjustment.bubbles.indices.contains(index) else { return }
        // Keep the complete text. The existing export budget rejects oversized
        // recipes atomically, instead of truncating the user's caption.
        adjustment.bubbles[index].content = text; revision = UUID()
    }
    public var sessionIdentity: UUID { generation }
    public func removeSelectedLayer() {
        guard canEdit, let layer = selectedLayer else { return }
        switch layer {
        case .bubble(let index): guard adjustment.bubbles.indices.contains(index) else { return }; adjustment.bubbles.remove(at: index)
        case .sticker(let index): guard adjustment.stickers.indices.contains(index) else { return }; adjustment.stickers.remove(at: index)
        }
        selectedLayer = nil; revision = UUID()
    }
    public func moveSelectedLayer(x: CGFloat, y: CGFloat) {
        mutateSelected { center, _, _ in center.x += x; center.y += y }
    }
    public func rotateSelectedLayer(by angle: CGFloat) {
        mutateSelected { _, _, transform in transform = transform.rotated(by: angle) }
    }
    public func resizeSelectedLayer(by scale: CGFloat) {
        guard scale.isFinite, scale > 0 else { return }
        mutateSelected { _, bounds, _ in
            let size = CGSize(width: bounds.width * scale, height: bounds.height * scale)
            if size.width >= 52, size.height >= 52 { bounds.size = size }
        }
    }
    private func mutateSelected(_ update: (inout CGPoint, inout CGRect, inout CGAffineTransform) -> Void) {
        guard canEdit, let selected = selectedLayer else { return }
        switch selected {
        case .bubble(let index):
            guard adjustment.bubbles.indices.contains(index) else { return }
            var item = adjustment.bubbles[index]
            update(&item.center, &item.bounds, &item.transform)
            guard hasRenderableGeometry(center: item.center, bounds: item.bounds, transform: item.transform) else { return }
            adjustment.bubbles[index] = item
        case .sticker(let index):
            guard adjustment.stickers.indices.contains(index) else { return }
            var item = adjustment.stickers[index]
            update(&item.center, &item.bounds, &item.transform)
            guard hasRenderableGeometry(center: item.center, bounds: item.bounds, transform: item.transform) else { return }
            adjustment.stickers[index] = item
        }
        revision = UUID()
    }
    private func renderPreview() {
        guard let source = sourceImage, phase == .ready else { return }
        let token = generation, request = UUID(), filter = adjustment.filterType
        previewGeneration = request; previewIsLoading = true
        previewPipeline.render(source: source, filter: filter) { [weak self] result in
            guard let self = self, self.generation == token, self.previewGeneration == request,
                  self.phase == .ready else { return }
            self.previewIsLoading = false
            switch result {
            case .success(let image): self.previewImage = image
            case .failure: self.notice = NSLocalizedString("The preview could not be rendered. Try the filter again.", comment: "")
            }
        }
    }
    public func export(completion: @escaping (Result<PhotoExport, PhotoExportError>) -> Void) {
        captureCanvasIfCurrent()
        cancelExport()
        guard phase == .ready else { completion(.failure(.invalidState)); return }
        let token = generation, request = UUID()
        exportGeneration = request
        let source: PhotoExportSource = input.map { .photosOriginal(url: $0.fullSizeImageURL, orientation: $0.fullSizeImageOrientation) } ?? .importedCopy(sourceImage)
        isExporting = true
        activeExport = exporter.export(snapshot: adjustment, source: source, isReadOnly: isReadOnly) { [weak self] result in
            guard let self = self, self.generation == token, self.exportGeneration == request else { return }
            self.isExporting = false; self.activeExport = nil
            completion(result)
        }
    }
    /// Native hit testing/gestures change only the low-level canvas. Its current
    /// immutable geometry is committed back to the SwiftUI-owned recipe.
    func acceptCanvasSnapshot(_ recipe: AdjustmentData, selected: Layer?, session: UUID, revision: UUID) {
        guard canEdit, generation == session, self.revision == revision else { return }
        var snapshot = recipe
        snapshot.filterType = adjustment.filterType
        adjustment = snapshot
        selectedLayer = selected
        // Do not create a new command revision: rebuilding the touched UIView
        // during a pan would discard its recognizer/selection state.
    }
    private func captureCanvasIfCurrent() {
        guard canEdit, let snapshot = canvas.snapshot(session: generation, revision: revision) else { return }
        acceptCanvasSnapshot(snapshot.recipe, selected: snapshot.selected, session: generation, revision: revision)
    }
    public func cancelExport() { exportGeneration = UUID(); activeExport?.cancel(); activeExport = nil; exporter.cancel(); isExporting = false }
    public func cancel() { reset() }
    private func reset() {
        generation = UUID(); canvasIdentity = UUID(); previewGeneration = UUID(); cancelExport(); previewPipeline.cancel()
        input = nil; pendingReadOnlyPreview = nil; sourceImage = nil; previewImage = nil; preservedAdjustmentData = nil
        adjustment = AdjustmentData(); selectedLayer = nil; notice = nil
        revision = UUID(); phase = .empty; previewIsLoading = false; isPresentingTool = false
    }
    #if DEBUG
    public var previewViewForTesting: UIImageView { canvas.imageView }
    public var activeExportForTesting: PhotoExportTask? { activeExport }
    public var outputImageForTesting: UIImage? {
        guard phase == .ready else { return nil }
        let source: PhotoExportSource = input.map { .photosOriginal(url: $0.fullSizeImageURL, orientation: $0.fullSizeImageOrientation) } ?? .importedCopy(sourceImage)
        return PhotoExportService.synchronousOutput(snapshot: adjustment, source: source, isReadOnly: isReadOnly)
    }
    #endif
}

