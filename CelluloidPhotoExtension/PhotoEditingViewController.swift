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

class PhotoEditingViewController: BaseEditPhotoController {

}

// MARK: - PHContentEditingController Protocol
extension PhotoEditingViewController: PHContentEditingController {
    
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
