//
//  EditPhotoPanel.swift
//  Celluloid
//
//  Created by Mango on 16/3/1.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public class EditPhotoPanel{
    
    public let collectionView:UICollectionView = {
        let layout = UICollectionViewFlowLayout()
        layout.itemSize =  CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.scrollDirection = .Horizontal
        let collectionView = UICollectionView(frame: CGRect.zero,collectionViewLayout: layout)
        collectionView.registerClass(UICollectionViewCell)
        return collectionView
    }()
    
    
    
}