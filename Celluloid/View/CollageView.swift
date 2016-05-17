//
//  CollageView.swift
//  Celluloid
//
//  Created by Mango on 16/5/10.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class CollageView: UIView {
    
    var collageModel: CollageModel?
    var photoModels: [PhotoModel]?
    
    func setupWithCollageModel(collageModel: CollageModel, photoModels: [PhotoModel] ) {
        
        self.collageModel = collageModel
        self.photoModels = photoModels
        
        self.subviews.forEach { $0.removeFromSuperview() }
        
        for (points, var photoModel) in zip(collageModel.areas, photoModels) {
            photoModel.points = points
            let collageContentView = CollageContentView(model: photoModel)
            self.addSubview(collageContentView)
            collageContentView.setupForEdit()
        }
        
    }
    
    func setupWithCollageModel(collageModel: CollageModel) {
        if let photoModels = photoModels {
            setupWithCollageModel(collageModel, photoModels: photoModels)
        }
    }
    
    func setupWithPhotoModels(photoModels: [PhotoModel]) {
        if let collageModel = collageModel {
            setupWithCollageModel(collageModel, photoModels: photoModels)
        }
    }
    
}