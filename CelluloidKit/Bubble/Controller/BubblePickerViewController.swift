//
//  BubblePickerViewController.swift
//  Celluloid
//
//  Created by Mango on 16/3/2.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit

public protocol BubblePickerViewControllerDelegate: class {
    func bubblePickerViewController(_ bubblePickerViewController: BubblePickerViewController, didSelectBubble bubble: BubbleModel)
}

open class BubblePickerViewController: BasePickerController {
    
    //MARK: Property
    open weak var delegate: BubblePickerViewControllerDelegate?
    
    //MARK: View life cycle
    open override func viewDidLoad() {
        super.viewDidLoad()
        
        self.navigationItem.title = tr(.bubble)
    }
    
}

//MARK: CollectionView Data Source
extension BubblePickerViewController {
    
    public override func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return BubbleModel.bubbles.count
    }
    
    public override func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        
        let cell = collectionView.dequeueReusableCellForIndexPath(indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        imageView.contentMode = .scaleAspectFit
        imageView.image = BubbleModel.bubbles[indexPath.row].bubbleImage
        cell.contentView.addSubview(imageView)
        return cell
    }
    
}

//MARK: CollectionView delegate
extension BubblePickerViewController {
    public func collectionView(_ collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: IndexPath) {
        let bubble = BubbleModel.bubbles[indexPath.row]
        let editBubbleViewController = EditBubbleViewController(bubbleModel: bubble)
        editBubbleViewController.delegate = self
        self.navigationController?.pushViewController(editBubbleViewController, animated: true)
    }
}

//MARK: EditBubbleViewController delegate
extension BubblePickerViewController: EditBubbleViewControllerDelegate {
    public func editBubbleViewController(_ editBubbleViewController: EditBubbleViewController, didEditedBubbleModel bubbleModel: BubbleModel) {
        self.delegate?.bubblePickerViewController(self, didSelectBubble: bubbleModel)
    }
}


