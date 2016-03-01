//
//  EditPhotoPanel.swift
//  Celluloid
//
//  Created by Mango on 16/3/1.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit

private enum ButtonType:Int{
    case SayBubbleButton
    case ThinkBubbleButton
    case CallBubbleButton
    case AsideBubbleButton
    case Count
}


@IBDesignable public class EditPhotoPanel:UIView{
    
    lazy var collectionView:UICollectionView = {
        let collectionView = UICollectionView(frame: CGRect.zero,collectionViewLayout: self.flowLayot)
        collectionView.backgroundColor = UIColor.yellowColor()
        collectionView.dataSource = self
        collectionView.delegate = self
        collectionView.registerClass(UICollectionViewCell)
        return collectionView
    }()
    
    let flowLayot:UICollectionViewFlowLayout = {
        let layout = UICollectionViewFlowLayout()
        layout.itemSize =  CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.scrollDirection = .Horizontal
        return layout
    }()
    
    
    //MARK: init
    private func commonInit() {
        self.addSubview(collectionView)
        collectionView.snp_makeConstraints { (make) -> Void in
            make.edges.equalTo(collectionView.superview!)
        }
    }
    
    public override init(frame: CGRect) {
        super.init(frame: frame)
        self.commonInit()
    }

    public required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        self.commonInit()
    }
}

//MARK: CollectionView Data Source
extension EditPhotoPanel:UICollectionViewDataSource {
    
    public func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return ButtonType.Count.rawValue
    }
    
    public func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        cell.contentView.addSubview(imageView)
        
        if let buttonType = ButtonType(rawValue: indexPath.row){
            switch buttonType{
            case .SayBubbleButton:
                imageView.image = UIImage(asset: .Image_sticker_say)
            case .AsideBubbleButton:
                imageView.image = UIImage(asset: .Image_sticker_aside)
            case .CallBubbleButton:
                imageView.image = UIImage(asset: .Image_sticker_call)
            case .ThinkBubbleButton:
                imageView.image = UIImage(asset: .Image_sticker_think)
            case .Count:
                break
            }
        }
        return cell
    }
    
}

//MARK: CollectionView delegate
extension EditPhotoPanel:UICollectionViewDelegate {
}













