//
//  ViewController.swift
//  Celluloid
//
//  Created by Mango on 16/2/26.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit
import BSImagePicker
import Photos
import Async

class ViewController: UIViewController {
    
    //MARK: Property
    private lazy var collageStylePanel: CollageStylePanel = {
        let panel = CollageStylePanel(models: [])
        panel.delegate = self
        return panel
    }()
    
    private lazy var imageArrangedPanel: ImageArrangedPanel = {
        let panel = ImageArrangedPanel(models: [])
        panel.delegate = self
        return panel
    }()
    
    private let collageView = CollageView()

    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.view.backgroundColor = .whiteColor()
        
        self.view.addSubview(collageStylePanel)
        collageStylePanel.snp_makeConstraints { make in
            make.left.right.bottom.equalTo(collageStylePanel.superview!)
            make.height.equalTo(120)
        }
        
        self.view.addSubview(imageArrangedPanel)
        imageArrangedPanel.snp_makeConstraints(closure: { make in
            make.top.equalTo(self.topLayoutGuide)
            make.left.right.equalTo(self.view)
            make.height.equalTo(80)
        })
        
        self.view.addSubview(collageView)
        collageView.snp_makeConstraints { make in
            make.height.width.equalTo(collageView.superview!.width)
            make.center.equalTo(collageView.superview!)
        }
        
        let button = UIButton()
        button.size = CGSize(width: 50, height: 50)
        button.backgroundColor = UIColor.redColor()
        button.center = self.view.center
        self.view.addSubview(button)
        button.addTarget(self, action: .touch, forControlEvents: .TouchUpInside)
    }

}

//MARK: CollageStylePanel Delegate
extension ViewController: CollageStylePanelDelegate {
    func collageStylePanel(collageStylePanel: CollageStylePanel, didSelctModel model: CollageModel) {
        collageView.setupWithCollageModel(model)
    }
}

//MARK: ImageArrangedPanelDelegate Delegate
extension ViewController: ImageArrangedPanelDelegate {
    func imageArrangedPanel(imageArrangedPanel: ImageArrangedPanel, didEditModels models: [PhotoModel]) {
        collageView.setupWithPhotoModels(models)
    }
}

//MARK: Actions
private extension Selector {
    static let touch = #selector(ViewController.touch)
}

extension ViewController {
    
    @objc func touch() {
        let vc = BSImagePickerViewController()
        vc.maxNumberOfSelections = 4
        
        bs_presentImagePickerController(vc, animated: true,
                                        select: nil, deselect: nil, cancel: nil,
                                        finish: { (assets: [PHAsset]) -> Void in
                                        
                                            Async.main {
                                                let models = assets.map { PhotoModel(asset: $0) }
                                                self.imageArrangedPanel.photoModels = models
                                                self.imageArrangedPanel.reload()
                                                
                                                let collageModels = CollageModel.collageModels(CollageImageCount(rawValue: assets.count)!)
                                                self.collageStylePanel.collageModels = collageModels
                                                self.collageView.setupWithCollageModel(collageModels.first!, photoModels: models)
                                            }
            }
            , completion: nil)
    }
    
}
