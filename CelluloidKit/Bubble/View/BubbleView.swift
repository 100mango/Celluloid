//
//  BubbleView.swift
//  Celluloid
//
//  Created by Mango on 16/3/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import MZFormSheetPresentationController

public class BubbleView: AttachView {
    //MARK: Property
    lazy var editTextBubbton: UIButton = {
        let button = UIButton(type: .Custom)
        button.hidden = true
        button.frame = CGRect(x: 0, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        button.setImage(UIImage(asset: .Btn_icon_sticker_text_normal), forState: .Normal)
        button.addTarget(self, action: #selector(editText), forControlEvents: .TouchUpInside)
        return button
    }()
    
    public var bubbleModel: BubbleModel {
        didSet {
            bubbleLabel.text = bubbleModel.content
            bubbleLabel.adjustFrame()
        }
    }
    
    let bubbleLabel: BubbleLabel
    
    //Property observers
    public override var transform: CGAffineTransform {
        didSet {
            self.bubbleModel.transform = transform
        }
    }
    
    public override var bounds: CGRect {
        didSet {
            self.bubbleModel.bounds = bounds
        }
    }
    
    public override var center: CGPoint {
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
    }

    public required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    public override func layoutSubviews() {
        super.layoutSubviews()
        
        deleteButton.frame = CGRect(x: bounds.width - self.buttonWidth, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        editTextBubbton.frame = CGRect(x: 0, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        self.bubbleLabel.adjustFrame()
    }
}

//MARK: Action
extension BubbleView {
    @objc func editText() {
        let editBubbleVC = EditBubbleViewController(bubbleModel: self.bubbleModel)
        editBubbleVC.delegate = self
        let navigationVC = UINavigationController(rootViewController: editBubbleVC)
        let formSheetController = MZFormSheetPresentationViewController(contentViewController: navigationVC)
        formSheetController.presentationController?.shouldUseMotionEffect = true
        formSheetController.presentationController?.shouldCenterVertically = true
        self.parentViewController?.presentViewController(formSheetController, animated: true, completion: nil)
    }
}

//MARK: EditBubbleViewController delegate
extension BubbleView: EditBubbleViewControllerDelegate {
    public func editBubbleViewController(editBubbleViewController: EditBubbleViewController, didEditedBubbleModel bubbleModel: BubbleModel) {
        self.bubbleModel = bubbleModel
    }
}