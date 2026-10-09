import SwiftUI
import UIKit

/// Only the artwork surface crosses into UIKit. No navigation, editor controller,
/// picker or application state is embedded here. This retains the shipped bubble
/// typography, sticker inset and affine geometry instead of changing output pixels.
@MainActor
struct CelluloidEditorCanvas: UIViewRepresentable {
    @ObservedObject var session: CelluloidEditingSession

    func makeUIView(context: Context) -> CelluloidCanvasSurface { session.canvas }
    func updateUIView(_ view: CelluloidCanvasSurface, context: Context) {
        let revision = session.revision
        view.update(image: session.previewImage, recipe: session.adjustment, revision: revision,
                    logicalImageSize: session.sourceImage?.size)
        view.didEstablishCanvas = { [weak session] size in
            // UIView layout must not synchronously publish during SwiftUI update.
            DispatchQueue.main.async { session?.establishCanvas(size, revision: revision) }
        }
    }
}

final class CelluloidCanvasSurface: UIView {
    let imageView = UIImageView()
    private lazy var overlay = ImageOverlayView.makeViewOverlaysImageView(imageView)
    private var recipe = AdjustmentData()
    private var logicalImageSize: CGSize?
    private var revision: UUID?
    private var restoredRevision: UUID?
    var didEstablishCanvas: ((CGSize) -> Void)?
    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .blackBackgroundColor
        imageView.contentMode = .scaleToFill
        imageView.isUserInteractionEnabled = false
        addSubview(imageView)
        isAccessibilityElement = true
        accessibilityLabel = NSLocalizedString("Photo Preview", bundle: extensionBundle, comment: "")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    func update(image: UIImage?, recipe: AdjustmentData, revision: UUID, logicalImageSize: CGSize? = nil) {
        imageView.image = image
        self.recipe = recipe; self.revision = revision
        self.logicalImageSize = logicalImageSize ?? image?.size
        setNeedsLayout()
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        // A thumbnail may round an odd pixel dimension. Its raster dimensions
        // must not become the persisted layer coordinate system.
        if let size = logicalImageSize, size.width > 0, size.height > 0 {
            let scale = CGFloat(fminf(Float(bounds.width / size.width), Float(bounds.height / size.height)))
            let scaled = CGSize(width: size.width * scale, height: size.height * scale)
            imageView.frame = CGRect(x: round((bounds.width - scaled.width) / 2),
                                     y: round((bounds.height - scaled.height) / 2),
                                     width: round(scaled.width), height: round(scaled.height))
        } else { imageView.frame = bounds }
        if restoredRevision != revision {
            overlay.restore(recipe)
            overlay.isUserInteractionEnabled = false
            overlay.accessibilityElementsHidden = true
            restoredRevision = revision
        }
        overlay.adjustFrame()
        if recipe.referenceCanvasSize == nil, let size = overlay.referenceCanvasSize {
            didEstablishCanvas?(size)
        }
    }
}
