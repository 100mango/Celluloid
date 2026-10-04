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
    
    fileprivate lazy var leftButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(dismissSelf))
    
    fileprivate lazy var rightButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.done), style: .plain, target: self, action: #selector(done))

    fileprivate lazy var activityIndicator: UIActivityIndicatorView = {
       let indicator = UIActivityIndicatorView(activityIndicatorStyle: .whiteLarge)
       self.view.addSubview(indicator)
       indicator.snp.makeConstraints  { make in
           make.center.equalTo(self.view)
       }
       indicator.hidesWhenStopped = true
       return indicator
    }()
    
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
        self.navigationItem.title = tr(.beautify)
        self.navigationItem.setLeftBarButton(leftButtonItem, animated: false)
        self.navigationItem.setRightBarButton(rightButtonItem, animated: false)
        
        startContentEditing()
    }
    
}

//MARK: Action
private extension EditPhotoViewController {
    
    @objc func dismissSelf() {
        dismiss(animated: true, completion: nil)
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
        model.asset.requestContentEditingInput(with: option) { (input, info) in
            self.input = input!
        }
    }
    
    func startContentEditing() {
        
        preview.image = input.displaySizeImage
        if let adjustmentData = input.adjustmentData {
            let adjustmentData = AdjustmentData.decode(adjustmentData.data)
            //state restoration
            restoreFromData(adjustmentData)
        }
    }
    
    
    func finishContentEditing() {
        
        activityIndicator.startAnimating()
        UIApplication.shared.beginIgnoringInteractionEvents()
        
        var shareImage: UIImage?
        Async.background {
            
            let output = PHContentEditingOutput(contentEditingInput: self.input)
            
            output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: AdjustmentData.formatVersion, data: self.adjustmentData.encode())
            let renderedJPEGData: NSData
            if let outputImage = self.outputImage {
                shareImage = outputImage
                renderedJPEGData = UIImageJPEGRepresentation(outputImage, 1.0)! as NSData
            }else{
                renderedJPEGData = NSData(contentsOf: (self.input.fullSizeImageURL)!)!
            }
            renderedJPEGData.write(to: output.renderedContentURL, atomically: true)
            
            PHPhotoLibrary.shared().performChanges({
                let request = PHAssetChangeRequest(for: self.model.asset)
                request.contentEditingOutput = output
                
            }, completionHandler: { success, error in
                DispatchQueue.main.async {
                    self.activityIndicator.stopAnimating()
                    UIApplication.shared.endIgnoringInteractionEvents()

                    if success {
                        if let nav = self.navigationController, let shareImage = shareImage {
                            nav.pushViewController(SharePhotoViewController(image: shareImage), animated: true)
                        }
                    } else {
                        let message = error?.localizedDescription ?? "The photo could not be saved."
                        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
                        alert.addAction(UIAlertAction(title: tr(.done), style: .default, handler: nil))
                        self.present(alert, animated: true, completion: nil)
                    }
                }
            })
        }
    }
}
