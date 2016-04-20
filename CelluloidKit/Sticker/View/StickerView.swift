//
//  StickerView.swift
//  Celluloid
//
//  Created by Mango on 16/4/20.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public class StickerView: AttachView {
    
    //MARK: Property
    public var stickerModel: StickerModel
    
    //Property observers
    public override var transform: CGAffineTransform {
        didSet {
            stickerModel.transform = transform
        }
    }
    
    public override var bounds: CGRect {
        didSet {
            stickerModel.bounds = bounds
        }
    }
    
    public override var center: CGPoint {
        didSet {
            stickerModel.center = center
        }
    }
    
    //MARK: init
    public init(stickerModel: StickerModel) {
        self.stickerModel = stickerModel
        super.init(frame: CGRect.zero)
        self.transform = stickerModel.transform
        self.bounds = stickerModel.bounds
        self.center = stickerModel.center
        self.imageView.image = stickerModel.stickerImage
    }
    
    public required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    
}