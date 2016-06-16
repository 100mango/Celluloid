//
//  StickerPickerViewController.swift
//  Celluloid
//
//  Created by Mango on 16/4/19.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public protocol StickerPickerViewControllerDelegate: class {
    func stickerPickerViewController(stickerPickerViewController: StickerPickerViewController, didSelectSticker sticker: StickerModel)
}

public class StickerPickerViewController: BasePickerController {
    
    //MARK: Property
    public weak var delegate: StickerPickerViewControllerDelegate?
    
    //MARK: View life cycle
    public override func viewDidLoad() {
        super.viewDidLoad()
        
        self.navigationItem.title = tr(.Sticker)
    }

}

//MARK: CollectionView Data Source
extension StickerPickerViewController {
    
    public override func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return StickerModel.stickers.count
    }
    
    public override func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        imageView.contentMode = .ScaleAspectFit
        imageView.image = StickerModel.stickers[indexPath.row].stickerImage
        cell.contentView.addSubview(imageView)
        return cell
    }
    
}

//MARK: CollectionView delegate
extension StickerPickerViewController {
    public func collectionView(collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: NSIndexPath) {
        let sticker = StickerModel.stickers[indexPath.row]
        self.delegate?.stickerPickerViewController(self, didSelectSticker: sticker)
        self.dismissViewControllerAnimated(true, completion: nil)
    }
}
