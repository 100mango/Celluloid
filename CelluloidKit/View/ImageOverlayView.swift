//
//  ImageOverlayView.swift
//  Celluloid
//
//  Created by Mango on 16/3/21.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public class ImageOverlayView: UIView {
    
    public var bubbleModels: [BubbleModel] {
        return bubbles.map({ $0.bubbleModel })
    }
    
    var bubbles: [BubbleView] {
        return self.subviews.flatMap({ $0 as? BubbleView })
    }
}

extension ImageOverlayView {
    @objc func touch() {
        
    }
}