//
//  PhotoModel.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import Photos

class PhotoModel {
    
    let asset: PHAsset
    fileprivate var image: UIImage?

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
    
    func requstImage(_ completion: @escaping (UIImage)->Void) {
        if let image = image {
            completion(image)
        }else{
            let options = PHImageRequestOptions()
            options.isNetworkAccessAllowed = true
            options.deliveryMode = .highQualityFormat
            PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 512, height: 512), contentMode: .aspectFill, options: options, resultHandler: { (image, info) in
                if let image = image {
                    DispatchQueue.main.async {
                        self.image = image
                        completion(image)
                    }
                }
            })
        }
    }
}
