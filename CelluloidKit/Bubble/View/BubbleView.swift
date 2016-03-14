//
//  BubbleView.swift
//  Celluloid
//
//  Created by Mango on 16/3/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public class BubbleView: AttachView {
    //MARK: Property
    lazy var editTextBubbton: UIButton = {
        let editTextButton = UIButton(type: .Custom)
        editTextButton.frame = CGRect(x: 0, y: 0, width: self.buttonWidth, height: self.buttonWidth)
        editTextButton.setImage(UIImage(asset: .Btn_icon_sticker_text_normal), forState: .Normal)
        editTextButton.addTarget(self, action: Selector("editText"), forControlEvents: .TouchUpInside)
        return editTextButton
    }()
    
    let bubbleLabel: BubbleLabel
    
    //MARK: init
    public init(bubbleModel:BubbleModel) {
        self.bubbleLabel = BubbleLabel(model: bubbleModel)
        super.init(frame: CGRect.zero)
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
    }
}