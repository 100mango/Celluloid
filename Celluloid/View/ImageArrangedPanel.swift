//
//  ImageArrangedView.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

protocol ImageArrangedPanelDelegate: class {
    func imageArrangedPanel(_ imageArrangedPanel: ImageArrangedPanel, didEditModels models: [PhotoModel])
}

class ImageArrangedPanel: UIView {
    
    //MARK: Property
    var photoModels: [PhotoModel]
    
    fileprivate lazy var collectionView: UICollectionView = {
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: self.flowLayout)
        collectionView.backgroundColor = .white
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.registerClass(ArrangedCollectionViewCell.self)
        
        let longPressGesture = UILongPressGestureRecognizer(target: self, action: #selector(ImageArrangedPanel.handleLongPressGesture(_:)))
        collectionView.addGestureRecognizer(longPressGesture)
        
        return collectionView
    }()
    
    fileprivate let spacing: CGFloat = 10
    fileprivate lazy var flowLayout: UICollectionViewFlowLayout = {
        let layout = UICollectionViewFlowLayout()
        let spacing = self.spacing
        layout.sectionInset = UIEdgeInsets(top: spacing, left: spacing, bottom: spacing, right: spacing)
        layout.minimumLineSpacing = spacing
        layout.minimumInteritemSpacing = spacing
        layout.scrollDirection = .horizontal
        return layout
    }()
    
    weak var delegate: ImageArrangedPanelDelegate?
    
    //MARK: init
    init(models: [PhotoModel]) {
        photoModels = models
        super.init(frame: CGRect.zero)
        self.addSubview(collectionView)
        collectionView.snp.makeConstraints  { (make) in
            make.edges.equalTo(collectionView.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: layout
    func reload() {
        collectionView.reloadData()
    }
    
    override func layoutSubviews() {
        if self.width > self.height {
            let width = self.height - (spacing * 2)
            flowLayout.itemSize = CGSize(width:  width, height: width)
        } else {
            let width = self.width - (spacing * 2)
            flowLayout.itemSize = CGSize(width: width, height: width)
        }
    }
    
}

//MARK: Action
extension ImageArrangedPanel {
    @objc fileprivate func handleLongPressGesture(_ gesture: UILongPressGestureRecognizer) {
        switch gesture.state {
        case .began:
            let location = gesture.location(in: collectionView)
            if let selectedIndexPath = collectionView.indexPathForItem(at: location) {
                collectionView.beginInteractiveMovementForItem(at: selectedIndexPath)
            }
        case .changed:
            collectionView.updateInteractiveMovementTargetPosition(gesture.location(in: gesture.view!))
        case .ended:
            collectionView.endInteractiveMovement()
        default:
            collectionView.cancelInteractiveMovement()
        }
    }
}

//MARK: ArrangedCollectionViewCell Delegate
extension ImageArrangedPanel: ArrangedCollectionViewCellDelegate {
    fileprivate func shouldRemoveCell(_ cell: ArrangedCollectionViewCell) {
        if let indexPath = collectionView.indexPath(for: cell) {
            if photoModels.count != 2 {
                photoModels.remove(at: indexPath.item)
                collectionView.deleteItems(at: [indexPath])
                self.delegate?.imageArrangedPanel(self, didEditModels: photoModels)
            } else {
                let alert = UIAlertController(title: nil, message: "拼图最少需要两张照片", preferredStyle: .alert)
                self.parentViewController?.present(alert, animated: true, completion: nil)
                alert.addAction(UIAlertAction(title: "确定", style: .cancel, handler: { action in
                    alert.dismiss(animated: true, completion: nil)
                }))
            }
        }
    }
}

//MARK: UICollectionViewDataSource
extension ImageArrangedPanel: UICollectionViewDataSource {
    
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return photoModels.count
    }
    
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        
        let cell = collectionView.dequeueReusableCellForIndexPath(indexPath) as ArrangedCollectionViewCell
        cell.delegate = self
        
        photoModels[indexPath.row].requstImage { image in
            cell.imageView.image = image
        }
        return cell
    }
    
    func collectionView(_ collectionView: UICollectionView, moveItemAt sourceIndexPath: IndexPath, to destinationIndexPath: IndexPath) {
    
        swap(&photoModels[sourceIndexPath.row], &photoModels[destinationIndexPath.row])
        self.delegate?.imageArrangedPanel(self, didEditModels: photoModels)
    }
    
}

//MARK: UICollectionViewDelegate
extension ImageArrangedPanel: UICollectionViewDelegate {
    
    
}


//MARK: ArrangedCollectionViewCell
private protocol ArrangedCollectionViewCellDelegate: class {
    func shouldRemoveCell(_ cell: ArrangedCollectionViewCell)
}


private class ArrangedCollectionViewCell: UICollectionViewCell {
    
    let imageView: UIImageView = {
        let imageView = UIImageView()
        imageView.contentMode = .scaleAspectFill
        imageView.clipsToBounds = true
        return imageView
    }()
    
    fileprivate lazy var deleteButton: UIButton = {
        let button = UIButton(type: .custom)
        button.setImage(UIImage(asset: .Btn_icon_sticker_delete_normal), for: .normal)
        button.addTarget(self, action: #selector(ArrangedCollectionViewCell.remove) , for: .touchUpInside)
        return button
    }()
    
    var delegate: ArrangedCollectionViewCellDelegate?
    
    override init(frame: CGRect) {
        
        super.init(frame: frame)
        
        self.contentView.addSubview(imageView)
        imageView.snp.makeConstraints  { make in
            make.edges.equalTo(self.imageView.superview!)
        }
        
        self.contentView.addSubview(deleteButton)
        deleteButton.snp.makeConstraints  { make in
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



