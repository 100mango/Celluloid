//
//  PhotoModel.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import Photos

class PhotoModel {
    
    let asset: PHAsset
    private var image: UIImage?

    //拼图相关：
    var points: [CGPoint] = []
    var zoomScale: CGFloat = 1
    var contentOffset: CGPoint = .zero
    var oldScrollViewSize: CGSize = .zero
    
    init(asset: PHAsset) {
        self.asset = asset
    }
    
}

extension PhotoModel {
    
    func requstImage(completion: (UIImage)->Void) {
        if let image = image {
            completion(image)
        }else{
            PHImageManager.defaultManager().requestImageForAsset(asset, targetSize: CGSize(width: 512, height: 512), contentMode: .AspectFill, options: nil, resultHandler: { (image, info) in
                if let image = image {
                    self.image = image
                    completion(image)
                }
            })
        }
    }
}