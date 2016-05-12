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

public protocol EditPhotoPanelDelegate: class {
    
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectBubble bubble: BubbleModel)
    
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectSticker sticker: StickerModel)
    
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectFilter filter: FilterType)
}

private enum ButtonCellType: Int {
    case FilterButton = 0
    case StickerButton
    case SayBubbleButton
    case ThinkBubbleButton
    case CallBubbleButton
    case AsideBubbleButton
    case Count
}

private enum FilterCellType: Int {
    case BackButton = 0
    case Original
    case Sepia
    case Chrome
    case Fade
    case Invert
    case Posterize
    case Sketch
    case PixellateFace
    case Count
}

private enum PanelType {
    case FilterType
    case ButtonType
}

@IBDesignable public class EditPhotoPanel: UIView {
    
    //MARK: Property
    public weak var delegate: EditPhotoPanelDelegate?
    
    lazy var collectionView: UICollectionView = {
        
        let layout = UICollectionViewFlowLayout()
        layout.itemSize =  CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.scrollDirection = .Horizontal
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.backgroundColor = UIColor.whiteColor()
        collectionView.registerClass(UICollectionViewCell)
        return collectionView
    }()
    
    private var panelType = PanelType.ButtonType
    
    
    //MARK: init
    private func commonInit() {
        self.addSubview(collectionView)
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

//MARK: View
private extension EditPhotoPanel {
    func makeButtonCell(indexPath: NSIndexPath) -> UICollectionViewCell {
        
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        cell.contentView.addSubview(imageView)
        
        if let buttonType = ButtonCellType(rawValue: indexPath.row){
            switch buttonType{
            case .FilterButton:
                imageView.image = UIImage(asset: .Image_icon_filter)
            case .StickerButton:
                imageView.image = UIImage(asset: .Image_icon_filter)
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
    
    func makeFilterCell(indexPath: NSIndexPath) ->  UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        cell.contentView.addSubview(imageView)
        
        if let cellType = FilterCellType(rawValue: indexPath.row){
            switch cellType {
            case .BackButton:
                imageView.image = UIImage(asset: .Btn_icon_back_normal)
            case .Original:
                imageView.image = UIImage(asset: .Sepia)
            case .Sepia:
                imageView.image = UIImage(asset: .Sepia)
            case .Chrome:
                imageView.image = UIImage(asset: .Chrome)
            case .Fade:
                imageView.image = UIImage(asset: .Instant)
            case .Invert:
                imageView.image = UIImage(asset: .Invert)
            case .Posterize:
                imageView.image = UIImage(asset: .Posterize)
            case .PixellateFace:
                imageView.image = UIImage(asset: .Posterize)
            case .Sketch:
                imageView.image = UIImage(asset: .Posterize)
            case .Count:
                break
            }
        }
        return cell
    }
}

//MARK: Actions
private extension EditPhotoPanel {
    func handleSelectButton(type: ButtonCellType) {
        
        func presentViewControllerFromSheet(vc: UIViewController) {
            let navigationVC = UINavigationController(rootViewController: vc)
            let formSheetController = MZFormSheetPresentationViewController(contentViewController: navigationVC)
            formSheetController.presentationController?.shouldUseMotionEffect = true
            formSheetController.presentationController?.shouldCenterVertically = true
            self.parentViewController?.presentViewController(formSheetController, animated: true, completion: nil)
        }
        
        switch type {
        case .FilterButton:
            panelType = .FilterType
            collectionView.reloadData()
        case .StickerButton:
            let stickerPicker = StickerPickerViewController()
            stickerPicker.delegate = self
            presentViewControllerFromSheet(stickerPicker)
        default:
            let bubblePicker = BubblePickerViewController()
            bubblePicker.delegate = self
            presentViewControllerFromSheet(bubblePicker)
        }
    }
    
    func handleSelectFilter(type: FilterCellType) {
        
        switch type {
        case .BackButton:
            panelType = .ButtonType
            collectionView.reloadData()
        case .Original:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Original)
        case .Sepia:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Sepia)
        case .Chrome:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Chrome)
        case .Fade:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Fade)
        case .Invert:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Invert)
        case .Posterize:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Posterize)
        case .Sketch:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .Sketch)
        case .PixellateFace:
            self.delegate?.editPhotoPanel(self, didSelectFilter: .PixellateFace)
        case .Count:
            break
        }
    }
}

//MARK: CollectionView Data Source
extension EditPhotoPanel:UICollectionViewDataSource {
    
    public func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        if panelType == .ButtonType {
            return ButtonCellType.Count.rawValue
        }else if panelType == .FilterType {
            return FilterCellType.Count.rawValue
        }
        return 0
    }
    
    public func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        if panelType == .ButtonType {
            return makeButtonCell(indexPath)
        }else if panelType == .FilterType {
            return makeFilterCell(indexPath)
        }
        return UICollectionViewCell()
    }
    
}

//MARK: CollectionView delegate
extension EditPhotoPanel:UICollectionViewDelegate {
    
    public func collectionView(collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: NSIndexPath) {
        
        if panelType == .ButtonType {
            if let type = ButtonCellType(rawValue: indexPath.row) {
                handleSelectButton(type)
            }
        }else if panelType == .FilterType {
            if let type = FilterCellType(rawValue: indexPath.row) {
                handleSelectFilter(type)
            }
        }
    }
}

//MARK: BubblePickerViewControllerDelegate
extension EditPhotoPanel: BubblePickerViewControllerDelegate {
    public func bubblePickerViewController(bubblePickerViewController: BubblePickerViewController, didSelectBubble bubble: BubbleModel) {
        self.delegate?.editPhotoPanel(self, didSelectBubble: bubble)
    }
}

//MARK: StickerPickerViewControllerDelegate
extension EditPhotoPanel: StickerPickerViewControllerDelegate {
    public func stickerPickerViewController(stickerPickerViewController: StickerPickerViewController, didSelectSticker sticker: StickerModel) {
        self.delegate?.editPhotoPanel(self, didSelectSticker: sticker)
    }
}







