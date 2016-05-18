//
//  EditPhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/17.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit
import Photos

class EditPhotoViewController: BaseEditPhotoController {
    
    //MARK: Property
    let model: PhotoModel
    
    //MARK: init
    init(model: PhotoModel) {
        self.model = model
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
}
