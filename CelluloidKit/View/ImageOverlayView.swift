//
//  ImageOverlayView.swift
//  Celluloid
//
//  Created by Mango on 16/3/21.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

open class ImageOverlayView: UIView {
    /// The coordinate space of the stored child geometry. Keep it through transient
    /// zero-sized layouts so rotation/Stage Manager cannot destroy an edit.
    private(set) var referenceCanvasSize: CGSize?

    
    open var bubbleModels: [BubbleModel] {
        return self.subviews.compactMap { $0 as? BubbleView }
            .map({ $0.bubbleModel })
    }
    
    open var stickerModels: [StickerModel] {
        return self.subviews.compactMap({ $0 as? StickerView })
            .map({ $0.stickerModel })
    }
    
    //MARK: init
    fileprivate func commonInit() {
        self.backgroundColor = UIColor.clear
        let tap = UITapGestureRecognizer(target: self, action: #selector(touch))
        self.addGestureRecognizer(tap)
    }
    public override init(frame: CGRect) {
        super.init(frame: frame)
        self.commonInit()
    }
    
    public required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        self.commonInit()
    }
    
    public static func makeViewOverlaysImageView(_ imageView: UIImageView) -> ImageOverlayView {
        let overlayView = ImageOverlayView()
        imageView.addSubview(overlayView)
        overlayView.adjustFrame()
        return overlayView
    }
    
    //MARK: layout
    open func adjustFrame() {
        guard let imageView = superview as? UIImageView else { return }
        let rect = imageView.imageRect
        guard rect.origin.x.isFinite, rect.origin.y.isFinite,
              rect.size.width.isFinite, rect.size.height.isFinite else { return }
        frame = rect
        // A blank image view's bounds are not an image coordinate system. In
        // particular, restoration can precede both source loading and layout.
        guard imageView.image != nil, rect.width > 0, rect.height > 0 else { return }
        if let previous = referenceCanvasSize, previous != rect.size {
            let x = rect.width / previous.width
            let y = rect.height / previous.height
            let decorations = subviews.compactMap { $0 as? AttachView }
            let proposed = decorations.map { (CGPoint(x: $0.center.x * x, y: $0.center.y * y), $0.transform.scaledInCanvas(x: x, y: y)) }
            guard x.isFinite, y.isFinite, x > 0, y > 0,
                  zip(decorations, proposed).allSatisfy({ hasRenderableGeometry(center: $0.1.0, bounds: $0.0.bounds, transform: $0.1.1) }) else { return }
            for (decoration, geometry) in zip(decorations, proposed) {
                decoration.center = geometry.0
                decoration.transform = geometry.1
            }
        }
        referenceCanvasSize = rect.size
    }

    func reset() {
        subviews.forEach { $0.removeFromSuperview() }
        referenceCanvasSize = nil
    }

    func restore(_ data: AdjustmentData) {
        subviews.forEach { $0.removeFromSuperview() }
        // Old 1.0 archives have no size. Their points retain the old meaning in
        // the first valid preview; do not guess which device wrote the archive.
        referenceCanvasSize = data.referenceCanvasSize.flatMap {
            AdjustmentData.isValidReferenceCanvas($0) ? $0 : nil
        }
        data.bubbles.forEach { addBubble($0) }
        data.stickers.forEach { addSticker($0) }
        adjustFrame()
    }
    
    open func addBubble(_ bubbleModel: BubbleModel) {
        guard hasRenderableGeometry(center: bubbleModel.center, bounds: bubbleModel.bounds, transform: bubbleModel.transform) else { return }
        let bubble = BubbleView(bubbleModel: bubbleModel)
        self.addSubview(bubble)
    }
    
    open func addSticker(_ stickerModel: StickerModel) {
        guard hasRenderableGeometry(center: stickerModel.center, bounds: stickerModel.bounds, transform: stickerModel.transform) else { return }
        let sticker = StickerView(stickerModel: stickerModel)
        self.addSubview(sticker)
    }
    
}

//MARK: Action
extension ImageOverlayView {
    @objc func touch() {
        self.subviews.compactMap({ $0 as? AttachView }).forEach{
            $0.hideButtonEnable = true
        }
    }
}

// Scale in the parent canvas, not the decoration's rotated local axes. Unlike
// scaledBy(x:y:), this also scales the translation of legacy affine transforms.
extension CGAffineTransform {
    var hasFiniteComponents: Bool { [a, b, c, d, tx, ty].allSatisfy { $0.isFinite } }
    func scaledInCanvas(x: CGFloat, y: CGFloat) -> CGAffineTransform {
        CGAffineTransform(a: a * x, b: b * y, c: c * x, d: d * y, tx: tx * x, ty: ty * y)
    }
}
