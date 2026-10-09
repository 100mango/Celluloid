//
//  AttachView.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

open class AttachView: UIView {
    // Optional canvas-owner hooks. Legacy UIKit callers keep their existing behavior.
    var removalDidBegin: (() -> Void)?
    var selectionDidChange: (() -> Void)?
    //MARK: Property
    let buttonWidth = CGFloat(32)
    let halfButtonWidth = CGFloat(16)
    
    open lazy var imageView:UIImageView = {
        let imageView = UIImageView(frame: self.bounds.insetBy(dx: self.halfButtonWidth, dy: self.halfButtonWidth))
        imageView.contentMode = .scaleAspectFit
        return imageView
    }()
    
    lazy var deleteButton: UIButton = {
        let button = DecorationControlButton(type: .custom)
        button.isHidden = true
        button.frame = CGRect(x: self.bounds.width - self.buttonWidth, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        button.setImage(UIImage(asset: .Btn_icon_sticker_delete_normal), for: .normal)
        button.accessibilityLabel = NSLocalizedString("Delete Decoration", bundle: extensionBundle, comment: "Decoration control")
        button.accessibilityIdentifier = "delete-decoration"
        button.addTarget(self, action: .removeSelf, for: .touchUpInside)
        return button
    }()
    
    lazy var resizeButton: UIButton = {
        let button = DecorationControlButton(type: .custom)
        button.isHidden = true
        button.frame = CGRect(x: self.bounds.width - self.buttonWidth, y: self.bounds.height - self.buttonWidth, width: self.buttonWidth, height: self.buttonWidth)
        button.setImage(UIImage(asset: .Btn_icon_sticker_edit_normal), for: .normal)
        button.accessibilityLabel = NSLocalizedString("Resize and Rotate Decoration", bundle: extensionBundle, comment: "Decoration control")
        button.accessibilityIdentifier = "resize-decoration"
        let panGesture = UIPanGestureRecognizer(target: self, action: .rotateAndResize)
        button.addGestureRecognizer(panGesture)
        
        return button
    }()
    
    open var hideButtonEnable:Bool = true {
        didSet {
            imageView.layer.borderWidth = hideButtonEnable ? 0 : 1
            imageView.layer.borderColor = UIColor.white.withAlphaComponent(0.6).cgColor
            UIView.animate(withDuration: 0.3, animations: {
                for view in self.subviews {
                    if let button = view as? UIButton {
                        button.isHidden = self.hideButtonEnable
                    }
                }
            })
            selectionDidChange?()
        }
    }
    
    //MARK: init
    fileprivate func commonInit() {
        self.addSubview(imageView)
        imageView.isAccessibilityElement = true
        imageView.accessibilityLabel = NSLocalizedString("Photo Decoration", bundle: extensionBundle, comment: "Editable decoration")
        imageView.accessibilityIdentifier = "attachment-image"
        imageView.accessibilityCustomActions = [
            UIAccessibilityCustomAction(name: NSLocalizedString("Delete Decoration", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleDelete)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Make Larger", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleEnlarge)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Make Smaller", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleReduce)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Rotate Clockwise", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleRotate)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Move Left", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleLeft)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Move Right", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleRight)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Move Up", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleUp)),
            UIAccessibilityCustomAction(name: NSLocalizedString("Move Down", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleDown))
        ]
        self.addSubview(deleteButton)
        self.addSubview(resizeButton)
        
        let moveGesture = UIPanGestureRecognizer(target: self, action: .moveAttachment)
        self.addGestureRecognizer(moveGesture)
        
        let tapGesture = UITapGestureRecognizer(target: self, action: .tap)
        self.addGestureRecognizer(tapGesture)
        
    }
    
    public override init(frame: CGRect) {
        super.init(frame: frame)
        commonInit()
    }

    public required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        commonInit()
    }
    
    open override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
        if bounds.contains(point) { return true }
        return subviews.compactMap { $0 as? UIButton }.contains {
            !$0.isHidden && $0.point(inside: convert(point, to: $0), with: event)
        }
    }

    static func transformForGesture(initial: CGAffineTransform, angleDelta: CGFloat) -> CGAffineTransform {
        initial.rotated(by: angleDelta)
    }

    @objc func accessibleDelete() -> Bool { removeSelf(); return true }
    @objc func accessibleEnlarge() -> Bool { bounds = bounds.scaled(1.1, 1.1); return true }
    @objc func accessibleReduce() -> Bool {
        let reduced = bounds.scaled(1 / 1.1, 1 / 1.1)
        guard reduced.width >= buttonWidth + 20, reduced.height >= buttonWidth + 20 else { return false }
        bounds = reduced
        return true
    }
    @objc func accessibleRotate() -> Bool { transform = transform.rotated(by: .pi / 18); return true }
    @objc func accessibleLeft() -> Bool { center.x -= 10; return true }
    @objc func accessibleRight() -> Bool { center.x += 10; return true }
    @objc func accessibleUp() -> Bool { center.y -= 10; return true }
    @objc func accessibleDown() -> Bool { center.y += 10; return true }

    open override func layoutSubviews() {
        super.layoutSubviews()
        
        //set frame.width & bounds.width is different because of the transform
        deleteButton.frame = CGRect(x: bounds.width - self.buttonWidth, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        resizeButton.frame = CGRect(x: bounds.width - self.buttonWidth, y: bounds.height - self.buttonWidth, width: self.buttonWidth, height: self.buttonWidth)
        imageView.frame = self.bounds.insetBy(dx: self.halfButtonWidth, dy: self.halfButtonWidth)
    }
    
}

//MARK: Action
private extension Selector {
    static let removeSelf = #selector(AttachView.removeSelf)
    static let rotateAndResize = #selector(AttachView.rotateAndResize(_:))
    static let moveAttachment = #selector(AttachView.moveAttachment(_:))
    static let tap = #selector(AttachView.tap)
}


extension AttachView{
    
    @objc func removeSelf() {
        removalDidBegin?()
        UIView.animate(withDuration: 0.3, delay: 0, usingSpringWithDamping: 1, initialSpringVelocity: 0.3, options: [],
            animations: {
                self.transform = CGAffineTransform(scaleX: 0.5, y: 0.5)
                self.alpha = 0
            },
            completion: { finish in
                self.removeFromSuperview()
            }
        )
    }
    
    @objc func rotateAndResize (_ gestureRecognizer:UIPanGestureRecognizer) {
        
        struct Static {
            static var deltaAngle = CGFloat()
            static var initialBounds = CGRect.zero
            static var initialDistance = CGFloat()
            static var initialTransform = CGAffineTransform.identity
        }
        
        let touchLocation = gestureRecognizer.location(in: self.superview!)
        let center = self.center
        
        
        if gestureRecognizer.state == .began {
            //AB两个点之间连线和x轴的夹角就是atan2（By-Ay，Bx-Ax）
            Static.deltaAngle = atan2(touchLocation.y - center.y, touchLocation.x - center.x)
            Static.initialTransform = self.transform
            Static.initialBounds = self.bounds
            Static.initialDistance = CGPointGetDistance(center, touchLocation)
        } else if gestureRecognizer.state == .changed {
            let ang = atan2(touchLocation.y - center.y, touchLocation.x - center.x)
            let angleDiff = ang - Static.deltaAngle
            self.transform = Self.transformForGesture(initial: Static.initialTransform, angleDelta: angleDiff)
            
            //Finding scale between current touchPoint and previous touchPoint
            guard Static.initialDistance > 0 else { return }
            let scale = CGPointGetDistance(center, touchLocation)/Static.initialDistance
            let scaleRect = Static.initialBounds.scaled(scale, scale)
            
            if scaleRect.width >= (buttonWidth + 20) && scaleRect.size.height >= (buttonWidth + 20) {
                self.bounds = scaleRect
            }
            self.layoutIfNeeded()
        }else{
            //do nothing
        }
    }
    
    @objc func moveAttachment (_ gestureRecognizer: UIPanGestureRecognizer) {
        struct Static {
            static var touchPoint = CGPoint.zero
            static var beginningCenter = CGPoint.zero
            static var beginningPoint = CGPoint.zero
        }
        
        func makeCenter() -> CGPoint {
            let x = Static.beginningCenter.x + (Static.touchPoint.x - Static.beginningPoint.x)
            let y = Static.beginningCenter.y + (Static.touchPoint.y - Static.beginningPoint.y)
            return CGPoint(x: x, y: y)
        }
        
        Static.touchPoint = gestureRecognizer.location(in: self.superview!)
        
        if gestureRecognizer.state == .began {
            Static.beginningCenter = self.center
            Static.beginningPoint = Static.touchPoint
            self.center = makeCenter()
        } else if gestureRecognizer.state == .changed || gestureRecognizer.state == .ended {
            self.center = makeCenter()
        }
    }
    
    @objc func tap() {
        hideButtonEnable = !hideButtonEnable
    }
}






// Keep the original 32-point artwork/layout and persisted geometry while enlarging
// interaction and accessibility targets to at least 44 points.
final class DecorationControlButton: UIButton {
    private var targetBounds: CGRect {
        let windowRect = convert(bounds, to: nil)
        let expanded = windowRect.insetBy(dx: -max(0, (44 - windowRect.width) / 2),
                                         dy: -max(0, (44 - windowRect.height) / 2))
        return convert(expanded, from: nil)
    }
    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool { targetBounds.contains(point) }
    override var accessibilityFrame: CGRect {
        get { UIAccessibility.convertToScreenCoordinates(targetBounds, in: self) }
        set { super.accessibilityFrame = newValue }
    }
}
