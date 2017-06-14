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
    
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        return AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
    }
    
    func startContentEditing(with contentEditingInput: PHContentEditingInput, placeholderImage: UIImage) {
        input = contentEditingInput
        preview.image = input.displaySizeImage
        if let adjustmentData = contentEditingInput.adjustmentData {
            let adjustmentData = AdjustmentData.decode(adjustmentData.data)
            //state restoration
            restoreFromData(adjustmentData)
        }
    }
    
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        
        
        
        // Render and provide output on a background queue.
        DispatchQueue.global().async {
            // Create editing output from the editing input.
            let output = PHContentEditingOutput(contentEditingInput: self.input)
            
            // Provide new adjustments and render output to given location.
            // output.adjustmentData = <#new adjustment data#>
            // let renderedJPEGData = <#output JPEG#>
            // renderedJPEGData.writeToURL(output.renderedContentURL, atomically: true)
            
            output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: AdjustmentData.formatVersion, data: self.adjustmentData.encode())
            
            
            
            
            
            
            let renderedJPEGData: Data
            if let outputImage = self.outputImage {
                renderedJPEGData = UIImageJPEGRepresentation(outputImage, 1.0)!
            }else{
                guard let url = self.input.fullSizeImageURL
                    else { fatalError("missing input image url") }
                renderedJPEGData = try! Data(contentsOf: url)
            }
            try! renderedJPEGData.write(to: output.renderedContentURL)
            
            
            // Call completion handler to commit edit to Photos.
            completionHandler(output)
            
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
