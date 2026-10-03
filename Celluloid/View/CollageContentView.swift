import UIKit
import CelluloidKit

final class CollageContentView: UIView, UIScrollViewDelegate {
    private lazy var scrollView: UIScrollView = {
        let view = UIScrollView()
        view.delegate = self
        view.accessibilityIdentifier = "collage-image"
        view.minimumZoomScale = 1
        view.maximumZoomScale = 5
        view.bounces = false
        view.showsVerticalScrollIndicator = false
        view.showsHorizontalScrollIndicator = false
        view.addSubview(imageView)
        return view
    }()
    private let imageView = UIImageView()
    private let border = CAShapeLayer()
    private var rendering = false
    private var configuring = false
    let model: PhotoModel
    init(model: PhotoModel) { self.model = model; super.init(frame: .zero); addSubview(scrollView) }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    func setupForEdit() { rendering = false; layout() }
    func setupForRender() { rendering = true; scrollView.isScrollEnabled = false; layout() }

    func layout() {
        guard let superview = superview else { return }
        frame = model.points.frameWithNewSize(superview.bounds.size)
        guard bounds.width > 0, bounds.height > 0 else { return }
        model.requstImage { [weak self] image in
            guard let self = self, image.size.width > 0, image.size.height > 0 else { return }
            self.configuring = true
            let oldSize = self.model.oldScrollViewSize
            let oldOffset = self.model.contentOffset
            let zoom = self.model.zoomScale
            self.scrollView.zoomScale = 1
            self.scrollView.frame = self.bounds
            let factor = max(self.bounds.width / image.size.width, self.bounds.height / image.size.height)
            let size = CGSize(width: image.size.width * factor, height: image.size.height * factor)
            self.imageView.image = image
            self.imageView.frame = CGRect(origin: .zero, size: size)
            self.scrollView.contentSize = size
            self.scrollView.zoomScale = zoom
            let scale = oldSize.width > 0 ? self.bounds.width / oldSize.width : 1
            self.scrollView.contentOffset = CGPoint(x: oldOffset.x * scale, y: oldOffset.y * scale)
            if !self.rendering {
                self.model.oldScrollViewSize = self.bounds.size
                self.model.contentOffset = self.scrollView.contentOffset
            }
            self.configuring = false
        }
        let path = model.points.cropPath(superview.bounds.size)
        let shape = CAShapeLayer()
        shape.frame = bounds
        shape.path = path.cgPath
        layer.mask = shape
        border.frame = bounds
        border.path = path.cgPath
        border.lineWidth = 3
        border.strokeColor = UIColor.black.cgColor
        border.fillColor = UIColor.clear.cgColor
        if border.superlayer == nil { layer.addSublayer(border) }
    }
    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }
    func scrollViewDidZoom(_ scrollView: UIScrollView) { if !configuring && !rendering { model.zoomScale = scrollView.zoomScale } }
    func scrollViewDidScroll(_ scrollView: UIScrollView) { if !configuring && !rendering { model.contentOffset = scrollView.contentOffset } }
}
