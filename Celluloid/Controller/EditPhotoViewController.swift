//
//  EditPhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/17.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit
import Photos
import Async

class EditPhotoViewController: BaseEditPhotoController {
    
    //MARK: Property
    let model: PhotoModel
    
    private lazy var leftButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Cancel), style: .Plain, target: self, action: #selector(dismiss))
    
    private lazy var rightButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Done), style: .Plain, target: self, action: #selector(done))

    
    //MARK: init
    init(model: PhotoModel) {
        self.model = model
        super.init(nibName: nil, bundle: nil)
        requstContentEditingInput()
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: View Life Cycle 
    override func viewDidLoad() {
        super.viewDidLoad()
        self.navigationItem.title = tr(.Beautify)
        self.navigationItem.setLeftBarButtonItem(leftButtonItem, animated: false)
        self.navigationItem.setRightBarButtonItem(rightButtonItem, animated: false)
        
        startContentEditing()
    }
    
}

//MARK: Action
private extension EditPhotoViewController {
    
    @objc func dismiss() {
        dismissViewControllerAnimated(true, completion: nil)
    }
    
    @objc func done() {
        finishContentEditing()
    }
}

//MARK: Content Editing
private extension EditPhotoViewController {
    
    func requstContentEditingInput() {
        
        let option = PHContentEditingInputRequestOptions()
        option.canHandleAdjustmentData = { option in
            return AdjustmentData.supportIdentifier(option.formatIdentifier, version: option.formatVersion)
        }
        model.asset.requestContentEditingInputWithOptions(option) { (input, info) in
            self.input = input
        }
    }
    
    func startContentEditing() {
        
        preview.image = input?.displaySizeImage
        if let adjustmentData = input?.adjustmentData {
            let adjustmentData = AdjustmentData.decode(adjustmentData.data)
            //state restoration
            restoreFromData(adjustmentData)
        }
    }
    
    
    func finishContentEditing() {
        
        var shareImage: UIImage?
        Async.background {
            
            if let input = self.input {
                
                let output = PHContentEditingOutput(contentEditingInput: input)
                
                output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: AdjustmentData.formatVersion, data: self.adjustmentData.encode())
                let renderedJPEGData: NSData
                if let outputImage = self.outputImage {
                    shareImage = outputImage
                    renderedJPEGData = UIImageJPEGRepresentation(outputImage, 1.0)!
                }else{
                    renderedJPEGData = NSData(contentsOfURL: (self.input?.fullSizeImageURL)!)!
                }
                renderedJPEGData.writeToURL(output.renderedContentURL, atomically: true)
                
                PHPhotoLibrary.sharedPhotoLibrary().performChanges({ 
                    let request = PHAssetChangeRequest(forAsset: self.model.asset)
                    request.contentEditingOutput = output
                    
                    }, completionHandler: { success, error in
                        print("Finished updating asset. %@", (success ? "Success." : error))
                })

            }
            
        }.main {
            if let nav = self.navigationController,shareImage = shareImage {
                nav.pushViewController(SharePhotoViewController(image: shareImage), animated: true)
            }
        }
        
    }
}