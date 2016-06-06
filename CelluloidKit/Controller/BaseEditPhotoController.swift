//
//  BaseEditPhotoController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import Photos

public class BaseEditPhotoController: UIViewController {
    
    //MARK: Property
    public var input: PHContentEditingInput?
    public let preview: UIImageView = {
        let preview = UIImageView()
        preview.contentMode = .ScaleAspectFit
        preview.userInteractionEnabled = true
        return preview
    }()
    let toolBar =  EditPhotoToolBar()
    
    lazy var overlayView: ImageOverlayView = ImageOverlayView.makeViewOverlaysImageView(self.preview)
    
    var filterType = FilterType.Original {
        didSet {
            guard filterType != oldValue else {
                return
            }
            if filterType == .Original {
                self.preview.image = input?.displaySizeImage
            }else{
                if let input = input {
                    self.preview.image = input.displaySizeImage?.filteredImage(input.fullSizeImageOrientation, filter: Filters.filter(filterType))

                }
            }
        }
    }
    
    //Computed property
    public var adjustmentData: AdjustmentData {
        var adjustmentData = AdjustmentData()
        adjustmentData.bubbles = overlayView.bubbleModels
        adjustmentData.stickers = overlayView.stickerModels
        adjustmentData.filterType = filterType
        return adjustmentData
    }
    
    public var outputImage: UIImage? {
        if let fullSizeImage = UIImage(contentsOfFile: input?.fullSizeImageURL?.path ?? "") {
            let fullSizeImageView = UIImageView()
            fullSizeImageView.image = fullSizeImage
            fullSizeImageView.size = fullSizeImage.size
            let scale = fullSizeImage.size.width / preview.imageRect.width
            
            //filter
            if filterType != .Original {
                if let input = input {
                     fullSizeImageView.image = fullSizeImage.filteredImage(input.fullSizeImageOrientation, filter: Filters.filter(filterType))
                }
            }
            
            //bubbles
            let bubbles: [BubbleModel] = self.adjustmentData.bubbles.map({
                var new = $0
                new.center = CGPoint(x: scale * $0.center.x, y: scale * $0.center.y)
                new.transform = CGAffineTransformScale($0.transform, scale, scale)
                return new
            })
            
            bubbles.forEach({
                let bubbleView = BubbleView(bubbleModel: $0)
                fullSizeImageView.addSubview(bubbleView)
            })
            
            //stickers
            let stickers: [StickerModel] = self.adjustmentData.stickers.map({
                var new = $0
                new.center = CGPoint(x: scale * $0.center.x, y: scale * $0.center.y)
                new.transform = CGAffineTransformScale($0.transform, scale, scale)
                return new
            })
            
            stickers.forEach({
                let stickerView = StickerView(stickerModel: $0)
                fullSizeImageView.addSubview(stickerView)
            })
            
            //output
            let outputImage = fullSizeImageView.render()
            return outputImage
        }else{
            return nil
        }
    }
    
    //MARK: View Lift Cycle
    override public func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .blackBackgroundColor
        
        self.view.addSubview(preview)
        preview.snp_makeConstraints { (make) in
            make.edges.equalTo(preview.superview!)
        }
        
        toolBar.delegate = self
        self.view.addSubview(toolBar)
        toolBar.snp_makeConstraints { (make) in
            make.height.equalTo(49)
            make.left.right.bottom.equalTo(toolBar.superview!)
        }
    }
    
    override public func viewDidLayoutSubviews() {
        overlayView.adjustFrame()
    }
}


// MARK: - Public
public extension BaseEditPhotoController {
    func restoreFromData(data: AdjustmentData) {
        filterType = data.filterType
        data.bubbles.forEach{ self.overlayView.addBubble($0) }
        data.stickers.forEach{ self.overlayView.addSticker($0) }
    }
}

// MARK: - EditPhotoPanel Delegate
extension BaseEditPhotoController: EditPhotoToolBarDelegate {
    public func editPhotoToolBar(editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel) {
        self.overlayView.addBubble(bubble)
    }
    
    public func editPhotoToolBar(editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel) {
        self.overlayView.addSticker(sticker)
    }
    
    public func editPhotoToolBar(editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType) {
        filterType = filter
    }
}