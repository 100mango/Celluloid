import AppKit
import SwiftUI
import ImageIO
import CelluloidDomain
import CelluloidRendering

struct MacPhotoAdjustmentPayload {
    let identifier: String
    let version: String
    let bytes: Data
}
struct MacPhotoSnapshot {
    let adjustment: MacPhotoAdjustment
    let source: SourceImage
    let bytes: Data
}

enum MacPhotoFinishPlan {
    case noChange
    case render(MacPhotoSnapshot)
    case unavailable
}

@MainActor final class MacPhotoSession: ObservableObject {
    @Published private(set) var adjustment = MacPhotoAdjustment()
    @Published private(set) var preview: CGImage?
    @Published private(set) var placeholder: NSImage?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var rendering = false
    @Published private(set) var readOnly = false
    @Published private(set) var changed = false
    @Published var finishing = false
    @Published var selection: UUID?
    private(set) var originalAdjustment: MacPhotoAdjustmentPayload?
    private var source: SourceImage?
    private var bytes: Data?
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var renderGeneration = UUID()
    typealias Loader = (URL) async throws -> Data
    typealias Preview = (MacPhotoAdjustment, SourceImage, Data) async throws -> CGImage
    private let load: Loader
    private let makePreview: Preview
    init(load: @escaping Loader = { try await NativeImportQueue.shared.read([$0])[0].1 },
         preview: @escaping Preview = { try await MacPhotoRenderQueue.shared.preview($0, source: $1, bytes: $2) }) {
        self.load = load; makePreview = preview
    }
    var editable: Bool { !readOnly && !loading && !finishing && source != nil }
    var snapshot: MacPhotoSnapshot? {
        guard !readOnly, !loading, let source, let bytes else { return nil }
        return MacPhotoSnapshot(adjustment: adjustment, source: source, bytes: bytes)
    }
    func cancel() {
        generation = UUID(); renderGeneration = UUID(); task?.cancel(); task = nil
        source = nil; bytes = nil; originalAdjustment = nil; preview = nil; placeholder = nil
        adjustment = MacPhotoAdjustment(); error = nil; loading = false; rendering = false
        readOnly = false; changed = false; finishing = false; selection = nil
    }
    func begin(url: URL?, orientation: Int32, previous: MacPhotoAdjustmentPayload?, placeholder: NSImage) {
        cancel(); self.placeholder = placeholder; originalAdjustment = previous
        let token = generation
        if let previous {
            do {
                guard MacPhotoAdjustment.supports(identifier: previous.identifier, version: previous.version) else { throw RecipeError.unsupportedVersion }
                adjustment = try MacPhotoAdjustment.decode(previous.bytes)
                try adjustment.requireEditableCanvas()
                try MacPhotoRenderer.requireQualifiedPhotosOutput(adjustment)
            } catch { preserveReadOnly(); return }
        }
        loading = true
        task = Task {
            do {
                try Task.checkCancellation()
                guard let url else { throw RenderError.invalidImage }
                let data = try await load(url)
                try Task.checkCancellation()
                guard token == generation else { return }
                guard let image = CGImageSourceCreateWithData(data as CFData, nil),
                      let properties = CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [CFString: Any],
                      (properties[kCGImagePropertyOrientation] as? Int ?? 1) == Int(orientation) else { throw RenderError.invalidImage }
                let metadata = try RasterCodec.metadata(data)
                source = metadata; bytes = data
                if adjustment.referenceCanvas == nil {
                    // This is a new coordinate space for newly added layers, never
                    // a guessed size for preexisting absolute-point decorations.
                    let factor = min(1, 800 / CGFloat(max(metadata.pixelWidth, metadata.pixelHeight)))
                    adjustment.referenceCanvas = CGSize(width: CGFloat(metadata.pixelWidth) * factor, height: CGFloat(metadata.pixelHeight) * factor)
                }
                loading = false; render()
            } catch is CancellationError { }
            catch { if token == generation { preserveReadOnly(error: error) } }
        }
    }
    private func preserveReadOnly(error: Error? = nil) {
        loading = false; rendering = false; readOnly = true; changed = false; preview = nil
        source = nil; bytes = nil
        self.error = error?.localizedDescription
    }
    func report(_ error: Error) { self.error = error.localizedDescription }
    func prepareHostFinish() -> MacPhotoFinishPlan {
        // Loading never permits mutations. An immediate host Done is therefore
        // a successful no-change result, not an unavailable/failed export.
        let plan: MacPhotoFinishPlan
        if readOnly || !changed { plan = .noChange }
        else if let snapshot { plan = .render(snapshot) }
        else { plan = .unavailable }
        prepareToFinish()
        return plan
    }
    func prepareToFinish() { renderGeneration = UUID(); task?.cancel(); task = nil; rendering = false }
    func change(_ mutation: (inout MacPhotoAdjustment) -> Void) {
        guard editable else { return }
        var next = adjustment; mutation(&next)
        do {
            try next.requireEditableCanvas()
            try MacPhotoRenderer.requireQualifiedPhotosOutput(next)
            // Validate the very payload that will be saved before showing an edit.
            _ = try next.encode()
            adjustment = next; changed = true; error = nil; render()
        } catch { self.error = error.localizedDescription }
    }
    func add(kind: MacPhotoLayer.Kind, asset: String) {
        guard let canvas = adjustment.referenceCanvas else { return }
        let layer = MacPhotoLayer(kind: kind, asset: asset,
            text: kind == .bubble ? NSLocalizedString("Hello", comment: "Default bubble text") : "", canvas: canvas)
        change { if kind == .bubble { $0.bubbles.append(layer) } else { $0.stickers.append(layer) } }
        if adjustment.layers.contains(where: { $0.id == layer.id }) { selection = layer.id }
    }
    func edit(_ id: UUID, _ mutation: (inout MacPhotoLayer) -> Void) { change { $0.edit(id, mutation) } }
    func remove(_ id: UUID) { change { $0.remove(id) }; if selection == id { selection = nil } }
    private func render() {
        guard let snapshot else { return }
        task?.cancel(); renderGeneration = UUID()
        let token = generation, revision = renderGeneration
        rendering = true
        task = Task {
            do {
                try Task.checkCancellation()
                let image = try await makePreview(snapshot.adjustment, snapshot.source, snapshot.bytes)
                try Task.checkCancellation()
                guard token == generation, revision == renderGeneration else { return }
                preview = image; placeholder = nil; rendering = false; error = nil
            } catch is CancellationError { }
            catch { if token == generation, revision == renderGeneration { rendering = false; self.error = error.localizedDescription } }
        }
    }
}
