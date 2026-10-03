//
//  BaseEditPhotoController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import Photos

open class BaseEditPhotoController: UIViewController {
    
    //MARK: Property
    open var input: PHContentEditingInput? {
        didSet { sourceImage = input?.displaySizeImage }
    }
    public var sourceImage: UIImage? {
        didSet { preview.image = sourceImage }
    }
    public let preview: UIImageView = {
        let preview = UIImageView()
        preview.contentMode = .scaleAspectFit
        preview.isUserInteractionEnabled = true
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
                self.preview.image = sourceImage
            }else{
            
                self.preview.image = sourceImage?.filteredImage(Filters.filter(filterType))

            }
        }
    }
    
    //Computed property
    open var adjustmentData: AdjustmentData {
        var adjustmentData = AdjustmentData()
        adjustmentData.bubbles = overlayView.bubbleModels
        adjustmentData.stickers = overlayView.stickerModels
        adjustmentData.filterType = filterType
        return adjustmentData
    }
    
    open var outputImage: UIImage? {
        if let fullSizeImage = normalizedFullSizeImage {
            guard preview.imageRect.width > 0, fullSizeImage.size.width > 0, fullSizeImage.size.height > 0 else { return nil }
            let fullSizeImageView = UIImageView()
            fullSizeImageView.image = fullSizeImage
            fullSizeImageView.size = fullSizeImage.size
            let scale = fullSizeImage.size.width / preview.imageRect.width
            
            //filter
            if filterType != .Original {
                
                fullSizeImageView.image = fullSizeImage.filteredImage(Filters.filter(filterType))
                
            }
            
            //bubbles
            let bubbles: [BubbleModel] = self.adjustmentData.bubbles.map({
                var new = $0
                new.center = CGPoint(x: scale * $0.center.x, y: scale * $0.center.y)
                new.transform = $0.transform.scaledBy(x: scale, y: scale)
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
                new.transform = $0.transform.scaledBy(x: scale, y: scale)
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
    
    private var normalizedFullSizeImage: UIImage? {
        if let url = input?.fullSizeImageURL, let image = UIImage(contentsOfFile: url.path) {
            return image.filteredImage(input?.fullSizeImageOrientation ?? 1, filter: Filters.filter(.Original))
        }
        guard let image = sourceImage else { return nil }
        let orientation: Int32
        switch image.imageOrientation {
        case .up: orientation = 1
        case .upMirrored: orientation = 2
        case .down: orientation = 3
        case .downMirrored: orientation = 4
        case .leftMirrored: orientation = 5
        case .right: orientation = 6
        case .rightMirrored: orientation = 7
        case .left: orientation = 8
        @unknown default: orientation = 1
        }
        return image.filteredImage(orientation, filter: Filters.filter(.Original))
    }

    //MARK: View Lift Cycle
    override open func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .blackBackgroundColor
        
        self.view.addSubview(preview)
        preview.snp.makeConstraints { (make) in
            make.edges.equalTo(view.safeAreaLayoutGuide).inset(UIEdgeInsets(top: 0, left: 0, bottom: 49, right: 0))
        }
        
        toolBar.delegate = self
        self.view.addSubview(toolBar)
        toolBar.snp.makeConstraints  { (make) in
            make.height.equalTo(49)
            make.left.right.bottom.equalTo(view.safeAreaLayoutGuide)
        }
    }
    
    override open func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        overlayView.adjustFrame()
    }
}


// MARK: - Public
public extension BaseEditPhotoController {
    func restoreFromData(_ data: AdjustmentData) {
        overlayView.subviews.forEach { $0.removeFromSuperview() }
        filterType = data.filterType
        data.bubbles.forEach{ self.overlayView.addBubble($0) }
        data.stickers.forEach{ self.overlayView.addSticker($0) }
    }
}

// MARK: - EditPhotoPanel Delegate
extension BaseEditPhotoController: EditPhotoToolBarDelegate {
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel) {
        self.overlayView.addBubble(bubble)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel) {
        self.overlayView.addSticker(sticker)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType) {
        filterType = filter
    }
}
