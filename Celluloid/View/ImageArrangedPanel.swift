//
//  ImageArrangedView.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

protocol ImageArrangedPanelDelegate: class {
    func imageArrangedPanel(imageArrangedPanel: ImageArrangedPanel, didEditModels models: [PhotoModel])
}

class ImageArrangedPanel: UIView {
    
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
        
        let longPressGesture = UILongPressGestureRecognizer(target: self, action: #selector(ImageArrangedPanel.handleLongPressGesture(_:)))
        collectionView.addGestureRecognizer(longPressGesture)
        
        return collectionView
    }()
    
    weak var delegate: ImageArrangedPanelDelegate?
    
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
    
    func reload() {
        collectionView.reloadData()
    }
}

//MARK: Action
extension ImageArrangedPanel {
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

//MARK: ArrangedCollectionViewCell Delegate
extension ImageArrangedPanel: ArrangedCollectionViewCellDelegate {
    private func shouldRemoveCell(cell: ArrangedCollectionViewCell) {
        if let indexPath = collectionView.indexPathForCell(cell) {
            photoModels.removeAtIndex(indexPath.item)
            collectionView.deleteItemsAtIndexPaths([indexPath])
            self.delegate?.imageArrangedPanel(self, didEditModels: photoModels)
        }
    }
}

//MARK: UICollectionViewDataSource
extension ImageArrangedPanel: UICollectionViewDataSource {
    
    func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return photoModels.count
    }
    
    func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(ArrangedCollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath) as! ArrangedCollectionViewCell
        cell.delegate = self
        
        photoModels[indexPath.row].requstImage { image in
            cell.imageView.image = image
        }
        return cell
    }
    
    func collectionView(collectionView: UICollectionView, moveItemAtIndexPath sourceIndexPath: NSIndexPath, toIndexPath destinationIndexPath: NSIndexPath) {
    
        swap(&photoModels[sourceIndexPath.row], &photoModels[destinationIndexPath.row])
        self.delegate?.imageArrangedPanel(self, didEditModels: photoModels)
    }
    
}

//MARK: UICollectionViewDelegate
extension ImageArrangedPanel: UICollectionViewDelegate {
    
    
}


//MARK: ArrangedCollectionViewCell
private protocol ArrangedCollectionViewCellDelegate: class {
    func shouldRemoveCell(cell: ArrangedCollectionViewCell)
}


private class ArrangedCollectionViewCell: UICollectionViewCell {
    
    let imageView: UIImageView = {
        let imageView = UIImageView()
        imageView.contentMode = .ScaleAspectFill
        imageView.clipsToBounds = true
        return imageView
    }()
    
    private lazy var deleteButton: UIButton = {
        let button = UIButton(type: .Custom)
        button.setImage(UIImage(asset: .Btn_icon_sticker_delete_normal), forState: .Normal)
        button.addTarget(self, action: #selector(ArrangedCollectionViewCell.remove) , forControlEvents: .TouchUpInside)
        return button
    }()
    
    var delegate: ArrangedCollectionViewCellDelegate?
    
    override init(frame: CGRect) {
        
        super.init(frame: frame)
        
        self.contentView.addSubview(imageView)
        imageView.snp_makeConstraints { make in
            make.edges.equalTo(self.imageView.superview!)
        }
        
        self.contentView.addSubview(deleteButton)
        deleteButton.snp_makeConstraints { make in
            make.top.equalTo(deleteButton.superview!).offset(-10)
            make.right.equalTo(deleteButton.superview!).offset(10)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    @objc func remove() {
        self.delegate?.shouldRemoveCell(self)
    }
}



