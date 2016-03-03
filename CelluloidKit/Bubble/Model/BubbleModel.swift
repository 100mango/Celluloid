//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public struct BubbleModel {
    public var bubbleImage:UIImage
    public var content:String
    
    init(bubbleImage: UIImage, content: String = ""){
        self.bubbleImage = bubbleImage
        self.content = content
    }
}