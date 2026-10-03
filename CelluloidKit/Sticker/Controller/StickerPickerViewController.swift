//
//  StickerPickerViewController.swift
//  Celluloid
//
//  Created by Mango on 16/4/19.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public protocol StickerPickerViewControllerDelegate: AnyObject {
    func stickerPickerViewController(_ stickerPickerViewController: StickerPickerViewController, didSelectSticker sticker: StickerModel)
}

open class StickerPickerViewController: BasePickerController {
    
    //MARK: Property
    open weak var delegate: StickerPickerViewControllerDelegate?
    
    //MARK: View life cycle
    open override func viewDidLoad() {
        super.viewDidLoad()
        
        self.navigationItem.title = tr(.sticker)
    }

}

//MARK: CollectionView Data Source
extension StickerPickerViewController {
    
    public override func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return StickerModel.stickers.count
    }
    
    public override func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        
        let cell: UICollectionViewCell = collectionView.dequeueReusableCellForIndexPath(indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.isAccessibilityElement = true
        cell.accessibilityTraits = .button
        cell.accessibilityLabel = String(format: NSLocalizedString("Sticker %d", bundle: extensionBundle, comment: "Picker item"), indexPath.row + 1)
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        imageView.contentMode = .scaleAspectFit
        imageView.image = StickerModel.stickers[indexPath.row].stickerImage
        cell.contentView.addSubview(imageView)
        return cell
    }
    
}

//MARK: CollectionView delegate
extension StickerPickerViewController {
    public func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        let sticker = StickerModel.stickers[indexPath.row]
        self.delegate?.stickerPickerViewController(self, didSelectSticker: sticker)
        self.dismiss(animated: true, completion: nil)
    }
}
