//
//  EditPhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/17.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class EditPhotoViewController: UIViewController {
    
    let model: PhotoModel
    
    let imageView = UIImageView()
    
    
    
    init(model: PhotoModel) {
        self.model = model
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    
    
}