//
//  CollageView.swift
//  Celluloid
//
//  Created by Mango on 16/5/10.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class CollageView: UIView {
    
    func setupWithCollageModel(collageModel: CollageModel, photoModels: [PhotoModel] ) {
        
        self.subviews.forEach { $0.removeFromSuperview() }
        
        for (points, var photoModel) in zip(collageModel.areas, photoModels) {
            photoModel.points = points
            let collageContentView = CollageContentView(model: photoModel)
            self.addSubview(collageContentView)
            collageContentView.setup()
        }
        
    }
    
}