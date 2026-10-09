//
//  BubbleView.swift
//  Celluloid
//
//  Created by Mango on 16/3/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

open class BubbleView: AttachView {
    // SwiftUI owns the caption route when this view belongs to its canvas.
    // The legacy editor continues using its existing controller when unset.
    var requestTextEditing: ((BubbleView) -> Void)?
    //MARK: Property
    lazy var editTextBubbton: UIButton = {
        let button = DecorationControlButton(type: .custom)
        button.isHidden = true
        button.frame = CGRect(x: 0, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        button.setImage(UIImage(asset: .Btn_icon_sticker_text_normal), for: .normal)
        button.accessibilityLabel = NSLocalizedString("Edit Bubble Text", bundle: extensionBundle, comment: "Bubble control")
        button.accessibilityIdentifier = "bubble-edit-text"
        button.addTarget(self, action: #selector(editText), for: .touchUpInside)
        return button
    }()
    
    open var bubbleModel: BubbleModel {
        didSet {
            bubbleLabel.text = bubbleModel.content
            imageView.accessibilityValue = bubbleModel.content
            bubbleLabel.adjustFrame()
        }
    }
    
    let bubbleLabel: BubbleLabel
    
    //Property observers
    open override var transform: CGAffineTransform {
        didSet {
            self.bubbleModel.transform = transform
        }
    }
    
    open override var bounds: CGRect {
        didSet {
            self.bubbleModel.bounds = bounds
        }
    }
    
    open override var center: CGPoint {
        didSet {
            self.bubbleModel.center = center
        }
    }
    
    //MARK: init
    public init(bubbleModel:BubbleModel) {
        self.bubbleModel = bubbleModel
        self.bubbleLabel = BubbleLabel(model: bubbleModel)
        super.init(frame: CGRect.zero)
        self.transform = bubbleModel.transform
        self.bounds = bubbleModel.bounds
        self.center = bubbleModel.center
        self.addSubview(editTextBubbton)
        self.imageView.image = bubbleModel.bubbleImage
        self.imageView.addSubview(bubbleLabel)
        imageView.accessibilityLabel = NSLocalizedString("Bubble", bundle: extensionBundle, comment: "")
        imageView.accessibilityValue = bubbleModel.content
        imageView.accessibilityCustomActions?.append(UIAccessibilityCustomAction(
            name: NSLocalizedString("Edit Bubble Text", bundle: extensionBundle, comment: ""), target: self, selector: #selector(accessibleEditText)))
    }

    public required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    open override func layoutSubviews() {
        super.layoutSubviews()
        
        deleteButton.frame = CGRect(x: bounds.width - self.buttonWidth, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        editTextBubbton.frame = CGRect(x: 0, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        self.bubbleLabel.adjustFrame()
    }
}

//MARK: Action
extension BubbleView {
    @objc func accessibleEditText() -> Bool { editText(); return true }
    @objc func editText() {
        if let requestTextEditing = requestTextEditing { requestTextEditing(self); return }
        let editBubbleVC = EditBubbleViewController(bubbleModel: self.bubbleModel)
        editBubbleVC.delegate = self
        let navigationVC = UINavigationController(rootViewController: editBubbleVC)
        // Keep the editing task visually and accessibly modal on every size.
        // A form sheet left old caption text visible outside its focus boundary.
        navigationVC.modalPresentationStyle = .fullScreen
        self.parentViewController?.present(navigationVC, animated: true)
    }
}

//MARK: EditBubbleViewController delegate
extension BubbleView: EditBubbleViewControllerDelegate {
    public func editBubbleViewController(_ editBubbleViewController: EditBubbleViewController, didEditedBubbleModel bubbleModel: BubbleModel) {
        self.bubbleModel = bubbleModel
    }
}
