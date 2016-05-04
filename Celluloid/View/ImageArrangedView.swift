//
//  ImageArrangedView.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class ImageArrangedView: UIView {
    
    //MARK: Property
    var photoModels: [PhotoModel]
    
    private lazy var collectionView: UICollectionView = {
        
        let layout = UICollectionViewFlowLayout()
        layout.itemSize = CGSize(width: 60, height: 60)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        layout.minimumLineSpacing = 10
        layout.minimumInteritemSpacing = 10
        layout.scrollDirection = .Horizontal
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.registerClass(ArrangedCollectionViewCell)
        
        let longPressGesture = UILongPressGestureRecognizer(target: self, action: #selector(ImageArrangedView.handleLongPressGesture(_:)))
        collectionView.addGestureRecognizer(longPressGesture)
        
        return collectionView
    }()
    
    //MARK: init
    init(models: [PhotoModel]) {
        photoModels = models
        super.init(frame: CGRect.zero)
        self.addSubview(collectionView)
        collectionView.snp_makeConstraints { (make) in
            make.edges.equalTo(collectionView.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

//MARK: Action
extension ImageArrangedView {
    @objc private func handleLongPressGesture(gesture: UILongPressGestureRecognizer) {
        switch gesture.state {
        case .Began:
            let location = gesture.locationInView(collectionView)
            if let selectedIndexPath = collectionView.indexPathForItemAtPoint(location) {
                collectionView.beginInteractiveMovementForItemAtIndexPath(selectedIndexPath)
            }
        case .Changed:
            collectionView.updateInteractiveMovementTargetPosition(gesture.locationInView(gesture.view!))
        case .Ended:
            collectionView.endInteractiveMovement()
        default:
            collectionView.cancelInteractiveMovement()
        }
    }
}

//MARK: UICollectionViewDataSource
extension ImageArrangedView: UICollectionViewDataSource {
    
    func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return photoModels.count
    }
    
    func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(ArrangedCollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath) as! ArrangedCollectionViewCell
        
        photoModels[indexPath.row].requstImage { image in
            cell.imageView.image = image
        }
        return cell
    }
    
    func collectionView(collectionView: UICollectionView, moveItemAtIndexPath sourceIndexPath: NSIndexPath, toIndexPath destinationIndexPath: NSIndexPath) {
        swap(&photoModels[sourceIndexPath.row], &photoModels[destinationIndexPath.row])
    }
    
}

//MARK: UICollectionViewDelegate
extension ImageArrangedView: UICollectionViewDelegate {
    
    
}

private class ArrangedCollectionViewCell: UICollectionViewCell {
    
    let imageView: UIImageView
    
    override init(frame: CGRect) {
        imageView = UIImageView.init()
        imageView.contentMode = .ScaleAspectFill
        super.init(frame: frame)
        
        self.addSubview(imageView)
        imageView.snp_makeConstraints { (make) in
            make.edges.equalTo(self.imageView.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
}



