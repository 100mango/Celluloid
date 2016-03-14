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

    var input: PHContentEditingInput?
    @IBOutlet weak var preview: UIImageView!
    @IBOutlet weak var panel: EditPhotoPanel!
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        panel.delegate = self
    }

    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
        // Dispose of any resources that can be recreated.
    }
}

// MARK: - EditPhotoPanelDelegate
extension PhotoEditingViewController: EditPhotoPanelDelegate {
    func editPhotoPanel(editPhotoPanel: EditPhotoPanel, didSelectBubble bubble: BubbleModel) {
        
        let view = BubbleView(bubbleModel: bubble)
        view.frame = CGRect(x: 40, y: 100, width: 100, height: 100)
        self.view.addSubview(view)
    }
}

// MARK: - PHContentEditingController
extension PhotoEditingViewController: PHContentEditingController{
    
    func canHandleAdjustmentData(adjustmentData: PHAdjustmentData?) -> Bool {
        // Inspect the adjustmentData to determine whether your extension can work with past edits.
        // (Typically, you use its formatIdentifier and formatVersion properties to do this.)
        return false
    }
    
    func startContentEditingWithInput(contentEditingInput: PHContentEditingInput?, placeholderImage: UIImage) {
        // Present content for editing, and keep the contentEditingInput for use when closing the edit session.
        // If you returned true from canHandleAdjustmentData:, contentEditingInput has the original image and adjustment data.
        // If you returned false, the contentEditingInput has past edits "baked in".
        preview.image = placeholderImage
        input = contentEditingInput
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
