import SwiftUI
import UIKit

/// Only the artwork/canvas crosses into UIKit. Its shipped hit testing, controls,
/// affine gesture math and accessibility actions are retained. SwiftUI owns the
/// recipe, presentations and save actions; no legacy editor controller is loaded.
@MainActor
struct CelluloidEditorCanvas: UIViewRepresentable {
    @ObservedObject var session: CelluloidEditingSession
    var editText: (CelluloidEditingSession.Layer, String, UUID) -> Void = { _, _, _ in }

    func makeUIView(context: Context) -> CelluloidCanvasSurface { session.canvas }
    static func dismantleUIView(_ view: CelluloidCanvasSurface, coordinator: ()) {
        view.didChange = nil; view.didRequestText = nil; view.didEstablishCanvas = nil
        view.isUserInteractionEnabled = false
    }
    func updateUIView(_ view: CelluloidCanvasSurface, context: Context) {
        let token = session.sessionIdentity, revision = session.revision
        view.didChange = { [weak session] recipe, selected, token, revision in
            session?.acceptCanvasSnapshot(recipe, selected: selected, session: token, revision: revision)
        }
        view.didRequestText = editText
        view.didEstablishCanvas = { [weak session] size in
            DispatchQueue.main.async {
                guard session?.sessionIdentity == token else { return }
                session?.establishCanvas(size, revision: revision)
            }
        }
        view.update(image: session.previewImage, recipe: session.adjustment, revision: revision,
                    logicalImageSize: session.sourceImage?.size, session: token, editable: session.canEdit,
                    scene: session.canvasIdentity)
    }
}

final class CelluloidCanvasSurface: UIView {
    struct Snapshot {
        var recipe: AdjustmentData
        let selected: CelluloidEditingSession.Layer?
    }
    let imageView = UIImageView()
    private lazy var overlay: EditingCanvasOverlay = {
        let result = EditingCanvasOverlay()
        imageView.addSubview(result)
        result.didChange = { [weak self] in self?.publishChange() }
        result.didRequestText = { [weak self] bubble in self?.requestText(for: bubble) }
        return result
    }()
    private var recipe = AdjustmentData()
    private var logicalImageSize: CGSize?
    private var revision: UUID?
    private var restoredRevision: UUID?
    private var sessionIdentity: UUID?
    private var restoredSession: UUID?
    private var sceneIdentity: UUID?
    private var restoredSceneIdentity: UUID?
    private var configuring = false
    private var editable = false
    private var layoutNotification = UUID()
    var didEstablishCanvas: ((CGSize) -> Void)?
    var didChange: ((AdjustmentData, CelluloidEditingSession.Layer?, UUID, UUID) -> Void)?
    var didRequestText: ((CelluloidEditingSession.Layer, String, UUID) -> Void)?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .blackBackgroundColor
        imageView.contentMode = .scaleToFill
        imageView.isUserInteractionEnabled = true
        addSubview(imageView)
        accessibilityLabel = NSLocalizedString("Photo Preview", bundle: extensionBundle, comment: "")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    func update(image: UIImage?, recipe: AdjustmentData, revision: UUID, logicalImageSize: CGSize? = nil,
                session: UUID? = nil, editable: Bool = false, scene: UUID? = nil) {
        imageView.image = image
        self.recipe = recipe; self.revision = revision
        self.logicalImageSize = logicalImageSize ?? image?.size
        self.sessionIdentity = session
        self.sceneIdentity = scene
        self.editable = editable
        isUserInteractionEnabled = true
        imageView.isUserInteractionEnabled = editable
        isAccessibilityElement = !editable
        overlay.accessibilityElementsHidden = !editable
        setNeedsLayout()
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        configuring = true
        let oldCanvasSize = overlay.referenceCanvasSize
        let restoresRecipe = restoredRevision != revision || restoredSession != sessionIdentity || restoredSceneIdentity != sceneIdentity
        // Fit using original logical dimensions, not a rounded thumbnail raster.
        // Match the shipped imageRect float/rounding rules exactly.
        if let size = logicalImageSize, size.width > 0, size.height > 0 {
            let scale = CGFloat(fminf(Float(bounds.width / size.width), Float(bounds.height / size.height)))
            let scaled = CGSize(width: size.width * scale, height: size.height * scale)
            imageView.frame = CGRect(x: round((bounds.width - scaled.width) / 2),
                                     y: round((bounds.height - scaled.height) / 2),
                                     width: round(scaled.width), height: round(scaled.height))
        } else { imageView.frame = bounds }
        if restoresRecipe {
            let sameScene = restoredSession == sessionIdentity && restoredSceneIdentity == sceneIdentity
            let selected = sameScene ? overlay.visibleControls : []
            let stackingOrder = sameScene ? overlay.liveStackingOrder : []
            overlay.restore(recipe)
            // The archive groups layer kinds, but the original live canvas
            // appended newly added artwork on top. Preserve that live hit order
            // across filter/caption commands without changing archive/export order.
            overlay.restoreStackingOrder(stackingOrder)
            overlay.restoreVisibleControls(selected)
            restoredRevision = revision; restoredSession = sessionIdentity
            restoredSceneIdentity = sceneIdentity
        }
        overlay.adjustFrame()
        configuring = false
        if recipe.referenceCanvasSize == nil, let size = overlay.referenceCanvasSize { didEstablishCanvas?(size) }
        guard restoresRecipe || oldCanvasSize != overlay.referenceCanvasSize else { return }
        // Layout can occur while SwiftUI is updating its view tree. Commit only
        // after that transaction and reject any superseding source/revision.
        let notification = UUID(); layoutNotification = notification
        let token = sessionIdentity, command = revision
        DispatchQueue.main.async { [weak self] in
            guard let self = self, self.layoutNotification == notification,
                  self.sessionIdentity == token, self.revision == command else { return }
            self.publishChange()
        }
    }
    func snapshot(session: UUID, revision: UUID) -> Snapshot? {
        guard restoredSession == session, restoredRevision == revision,
              imageView.image != nil, overlay.referenceCanvasSize != nil else { return nil }
        return currentSnapshot()
    }
    private func currentSnapshot() -> Snapshot {
        var snapshot = recipe
        snapshot.bubbles = overlay.liveBubbles.map(\.bubbleModel)
        snapshot.stickers = overlay.liveStickers.map(\.stickerModel)
        snapshot.referenceCanvasSize = overlay.referenceCanvasSize
        return Snapshot(recipe: snapshot, selected: overlay.visibleControls.first)
    }
    private func publishChange() {
        guard editable, !configuring, let token = restoredSession, let command = restoredRevision,
              token == sessionIdentity, command == revision else { return }
        let snapshot = currentSnapshot()
        didChange?(snapshot.recipe, snapshot.selected, token, command)
    }
    private func requestText(for bubble: BubbleView) {
        guard editable, !configuring, let token = sessionIdentity,
              let index = overlay.liveBubbles.firstIndex(where: { $0 === bubble }) else { return }
        publishChange()
        didRequestText?(.bubble(index), bubble.bubbleModel.content, token)
    }
}

private final class EditingCanvasOverlay: ImageOverlayView {
    var didChange: (() -> Void)?
    var didRequestText: ((BubbleView) -> Void)?
    var liveBubbles: [CanvasBubbleView] { subviews.compactMap { $0 as? CanvasBubbleView }.filter { !$0.pendingRemoval } }
    var liveStickers: [CanvasStickerView] { subviews.compactMap { $0 as? CanvasStickerView }.filter { !$0.pendingRemoval } }
    var visibleControls: [CelluloidEditingSession.Layer] {
        liveBubbles.enumerated().compactMap { $0.element.hideButtonEnable ? nil : .bubble($0.offset) }
        + liveStickers.enumerated().compactMap { $0.element.hideButtonEnable ? nil : .sticker($0.offset) }
    }
    var liveStackingOrder: [CelluloidEditingSession.Layer] {
        let bubbles = Dictionary(uniqueKeysWithValues: liveBubbles.enumerated().map { (ObjectIdentifier($0.element), $0.offset) })
        let stickers = Dictionary(uniqueKeysWithValues: liveStickers.enumerated().map { (ObjectIdentifier($0.element), $0.offset) })
        return subviews.compactMap { view in
            if let index = bubbles[ObjectIdentifier(view)] { return .bubble(index) }
            if let index = stickers[ObjectIdentifier(view)] { return .sticker(index) }
            return nil
        }
    }
    func restoreStackingOrder(_ previous: [CelluloidEditingSession.Layer]) {
        var views: [CelluloidEditingSession.Layer: UIView] = [:]
        let all = liveBubbles.enumerated().map { index, view -> CelluloidEditingSession.Layer in
            let id = CelluloidEditingSession.Layer.bubble(index); views[id] = view; return id
        } + liveStickers.enumerated().map { index, view -> CelluloidEditingSession.Layer in
            let id = CelluloidEditingSession.Layer.sticker(index); views[id] = view; return id
        }
        let retained = previous.filter { views[$0] != nil }
        let existing = Set(retained)
        for id in retained + all.filter({ !existing.contains($0) }) {
            if let view = views[id] { bringSubviewToFront(view) }
        }
    }
    func restoreVisibleControls(_ layers: [CelluloidEditingSession.Layer]) {
        for layer in layers {
            switch layer {
            case .bubble(let index): if liveBubbles.indices.contains(index) { liveBubbles[index].hideButtonEnable = false }
            case .sticker(let index): if liveStickers.indices.contains(index) { liveStickers[index].hideButtonEnable = false }
            }
        }
    }
    override func addBubble(_ model: BubbleModel) {
        guard hasRenderableGeometry(center: model.center, bounds: model.bounds, transform: model.transform) else { return }
        let bubble = CanvasBubbleView(bubbleModel: model)
        bubble.changed = { [weak self] in self?.didChange?() }
        bubble.selectionDidChange = bubble.changed
        bubble.removalDidBegin = { [weak self, weak bubble] in
            bubble?.pendingRemoval = true; bubble?.isUserInteractionEnabled = false; self?.didChange?()
        }
        bubble.requestTextEditing = { [weak self] in self?.didRequestText?($0) }
        addSubview(bubble)
    }
    override func addSticker(_ model: StickerModel) {
        guard hasRenderableGeometry(center: model.center, bounds: model.bounds, transform: model.transform) else { return }
        let sticker = CanvasStickerView(stickerModel: model)
        sticker.changed = { [weak self] in self?.didChange?() }
        sticker.selectionDidChange = sticker.changed
        sticker.removalDidBegin = { [weak self, weak sticker] in
            sticker?.pendingRemoval = true; sticker?.isUserInteractionEnabled = false; self?.didChange?()
        }
        addSubview(sticker)
    }
}

private final class CanvasBubbleView: BubbleView {
    var changed: (() -> Void)?
    var pendingRemoval = false
    override var transform: CGAffineTransform { didSet { if !pendingRemoval { changed?() } } }
    override var center: CGPoint { didSet { if !pendingRemoval { changed?() } } }
    override var bounds: CGRect { didSet { if !pendingRemoval { changed?() } } }
    override func didMoveToSuperview() { super.didMoveToSuperview(); changed?() }
}
private final class CanvasStickerView: StickerView {
    var changed: (() -> Void)?
    var pendingRemoval = false
    override var transform: CGAffineTransform { didSet { if !pendingRemoval { changed?() } } }
    override var center: CGPoint { didSet { if !pendingRemoval { changed?() } } }
    override var bounds: CGRect { didSet { if !pendingRemoval { changed?() } } }
    override func didMoveToSuperview() { super.didMoveToSuperview(); changed?() }
}
