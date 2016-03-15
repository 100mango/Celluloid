//
//  BubbleLabel.swift
//  Celluloid
//
//  Created by Mango on 16/3/14.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public class BubbleLabel: UILabel {
    
    //MARK: Property
    var model: BubbleModel
    
    //MARK: init
    public init(model: BubbleModel) {
        self.model = model
        super.init(frame: CGRect.zero)
        self.backgroundColor = UIColor.clearColor()
        self.numberOfLines = 0
        self.lineBreakMode = .ByCharWrapping
        self.text = model.content
    }

    required public init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: layout
    /**
    call this method in superView's layoutSubViews method to adjust label frame and font size
    */
    public func adjustFrame() {
        if let superview = self.superview as? UIImageView {
            let imageRect = superview.imageRect
            let width = imageRect.size.width
            let height = imageRect.size.height
            let area = self.model.area
            let insets = UIEdgeInsets(top: height * area[0]/100,
                left: width * area[2]/100 + 4,
                bottom: height * (100 - area[1])/100,
                right: width * (100 - area[3])/100)
            self.frame = UIEdgeInsetsInsetRect(imageRect, insets)
            self.adjustFontSizeToFitBounds()
        }
    }
}

private extension UILabel {
    func adjustFontSizeToFitBounds() {
        var maxFontSize = CGFloat(16)
        let minFontSize = CGFloat(1)
        
        let constrainSize = CGSize(width: self.width, height: CGFloat.max)
        var textSize: CGSize
        repeat {
            self.font = UIFont(name: self.font.fontName, size: maxFontSize)
            textSize = self.sizeThatFits(constrainSize)
            maxFontSize -= 1
        } while maxFontSize > minFontSize && textSize.height >= self.height
        
        //如果只有一行则居中
        if (floor((textSize.height / self.font.lineHeight)) == 1) {
            self.textAlignment = .Center;
        }else{
            self.textAlignment = .Left;
        }
    }
}