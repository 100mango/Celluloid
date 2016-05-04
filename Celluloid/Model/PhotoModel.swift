//
//  PhotoModel.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import Photos

struct PhotoModel {
    
    let asset: PHAsset
    
    private var image: UIImage?
    
    init(asset: PHAsset) {
        self.asset = asset
    }
    
    mutating func requstImage(completion: (UIImage)->Void) {
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