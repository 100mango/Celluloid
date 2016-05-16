//
//  PhotoEditingViewController.swift
//  CelluloidPhotoExtension
//
//  Created by Mango on 16/2/26.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import Photos
import PhotosUI
import Async
import CelluloidKit

class PhotoEditingViewController: UIViewController {

    //MARK: Property
    var input: PHContentEditingInput?
    @IBOutlet weak var preview: UIImageView!
    @IBOutlet weak var panel: EditPhotoPanel!
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
                self.preview.image = input?.displaySizeImage?.filteredImage(Filters.filter(filterType))
            }
        }
    }
    
    //Computed property
    var adjustmentData: AdjustmentData {
        var adjustmentData = AdjustmentData()
        adjustmentData.bubbles = overlayView.bubbleModels
        adjustmentData.stickers = overlayView.stickerModels
        adjustmentData.filterType = filterType
        return adjustmentData
    }
    
    var outputImage: UIImage? {
        if let fullSizeImage = UIImage(contentsOfFile: input?.fullSizeImageURL?.path ?? "") {
            let fullSizeImageView = UIImageView()
            fullSizeImageView.image = fullSizeImage
            fullSizeImageView.size = fullSizeImage.size
            let scale = fullSizeImage.size.width / preview.imageRect.width
            
            //filter
            if filterType != .Original {
                fullSizeImageView.image = fullSizeImage.filteredImage(input!.fullSizeImageOrientation, filter: Filters.filter(filterType))
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
    override func viewDidLoad() {
        super.viewDidLoad()
        panel.delegate = self
        self.view.addSubview(toolBar)
        toolBar.snp_makeConstraints { (make) in
            make.height.equalTo(49)
            make.left.right.bottom.equalTo(toolBar.superview!)
        }
        print(toolBar)
    }

    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
    }
    
    override func viewDidLayoutSubviews() {
        overlayView.adjustFrame()
    }
}


// MARK: - Private
private extension PhotoEditingViewController {
    func restoreFromData(data: AdjustmentData) {
        filterType = data.filterType
        data.bubbles.forEach{ self.overlayView.addBubble($0) }
        data.stickers.forEach{ self.overlayView.addSticker($0) }
    }
}

// MARK: - EditPhotoPanel Delegate
extension PhotoEditingViewController: EditPhotoPanelDelegate {
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectBubble bubble: BubbleModel) {
        self.overlayView.addBubble(bubble)
    }
    
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectSticker sticker: StickerModel) {
        self.overlayView.addSticker(sticker)
    }
    
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectFilter filter: FilterType) {
        filterType = filter
    }
}

// MARK: - PHContentEditingController Protocol
extension PhotoEditingViewController: PHContentEditingController{
    
    func canHandleAdjustmentData(adjustmentData: PHAdjustmentData?) -> Bool {
        
        if let adjustmentData = adjustmentData {
            return AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
        }else{
            return false
        }
    }
    
    func startContentEditingWithInput(contentEditingInput: PHContentEditingInput?, placeholderImage: UIImage) {
        
        input = contentEditingInput
        preview.image = input?.displaySizeImage
        if let adjustmentData = contentEditingInput?.adjustmentData {
            let adjustmentData = AdjustmentData.decode(adjustmentData.data)
            //state restoration
            restoreFromData(adjustmentData)
        }
    }
    
    func finishContentEditingWithCompletionHandler(completionHandler: ((PHContentEditingOutput!) -> Void)!) {
        // Update UI to reflect that editing has finished and output is being rendered.
        
        // Render and provide output on a background queue.
        dispatch_async(dispatch_get_global_queue(CLong(DISPATCH_QUEUE_PRIORITY_DEFAULT), 0)) {
            // Create editing output from the editing input.
            let output = PHContentEditingOutput(contentEditingInput: self.input!)
            
            // Provide new adjustments and render output to given location.
            // output.adjustmentData = <#new adjustment data#>
            // let renderedJPEGData = <#output JPEG#>
            // renderedJPEGData.writeToURL(output.renderedContentURL, atomically: true)
            
            output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: AdjustmentData.formatVersion, data: self.adjustmentData.encode())
            let renderedJPEGData: NSData
            if let outputImage = self.outputImage {
                renderedJPEGData = UIImageJPEGRepresentation(outputImage, 1.0)!
            }else{
                renderedJPEGData = NSData(contentsOfURL: (self.input?.fullSizeImageURL)!)!
            }
            renderedJPEGData.writeToURL(output.renderedContentURL, atomically: true)
            
            // Call completion handler to commit edit to Photos.
            completionHandler?(output)
            
            // Clean up temporary files, etc.
        }
    }
    
    var shouldShowCancelConfirmation: Bool {
        // Determines whether a confirmation to discard changes should be shown to the user on cancel.
        // (Typically, this should be "true" if there are any unsaved changes.)
        return false
    }
    
    func cancelContentEditing() {
        // Clean up temporary files, etc.
        // May be called after finishContentEditingWithCompletionHandler: while you prepare output.
    }
    
}
