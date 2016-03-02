//
//  EditPhotoPanel.swift
//  Celluloid
//
//  Created by Mango on 16/3/1.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import MZFormSheetPresentationController


private enum ButtonType:Int{
    case SayBubbleButton = 0
    case ThinkBubbleButton
    case CallBubbleButton
    case AsideBubbleButton
    case Count
}


@IBDesignable public class EditPhotoPanel:UIView{
    
    let collectionView: UICollectionView = {
        
        let layout = UICollectionViewFlowLayout()
        layout.itemSize =  CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.scrollDirection = .Horizontal
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.backgroundColor = UIColor.whiteColor()
        collectionView.registerClass(UICollectionViewCell)
        return collectionView
    }()
    
    //MARK: init
    private func commonInit() {
        self.addSubview(collectionView)
        collectionView.dataSource = self
        collectionView.delegate = self
        collectionView.snp_makeConstraints { (make) -> Void in
            make.edges.equalTo(collectionView.superview!)
        }
    }
    
    public override init(frame: CGRect) {
        super.init(frame: frame)
        commonInit()
    }

    public required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        commonInit()
    }
}

//MARK: CollectionView Data Source
extension EditPhotoPanel:UICollectionViewDataSource {
    
    public func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return ButtonType.Count.rawValue
    }
    
    public func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = Style.cellLightPurple
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
    
    public func collectionView(collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: NSIndexPath) {
        
        let formSheetController = MZFormSheetPresentationViewController(contentViewController: BubblePickerViewController())
        formSheetController.presentationController?.shouldUseMotionEffect = true

        self.parentViewController?.presentViewController(formSheetController, animated: true, completion: nil)
    }
}













