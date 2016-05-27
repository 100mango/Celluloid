//
//  CollageViewController.swift
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

class CollageViewController: UIViewController {
    
    //MARK: Property
    var assets: [PHAsset]
    
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
    
    private lazy var leftButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Cancel), style: .Plain, target: self, action: #selector(dismiss))
    
    private lazy var rightButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Done), style: .Plain, target: self, action: #selector(done))
    
    private let collageView = CollageView()

    //MARK: View Life Cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.title = tr(.Collage)
        self.automaticallyAdjustsScrollViewInsets = false
        self.view.backgroundColor = .whiteColor()
        self.navigationItem.setLeftBarButtonItem(leftButtonItem, animated: false)
        self.navigationItem.setRightBarButtonItem(rightButtonItem, animated: false)
        
        self.view.addSubview(collageStylePanel)
        collageStylePanel.snp_makeConstraints { make in
            make.left.right.equalTo(collageStylePanel.superview!)
            make.bottom.equalTo(self.snp_bottomLayoutGuideTop)
            make.height.equalTo(120)
        }
        
        self.view.addSubview(imageArrangedPanel)
        imageArrangedPanel.snp_makeConstraints(closure: { make in
            make.top.equalTo(self.snp_topLayoutGuideBottom)
            make.left.right.equalTo(self.view)
            make.height.equalTo(80)
        })
        
        self.view.addSubview(collageView)
        collageView.snp_makeConstraints { make in
            make.height.width.equalTo(collageView.superview!.width)
            make.center.equalTo(collageView.superview!)
        }
        
        //setup data
        let models = assets.map { PhotoModel(asset: $0) }
        imageArrangedPanel.photoModels = models
        imageArrangedPanel.reload()
        
        let collageModels = CollageModel.collageModels(CollageImageCount(rawValue: assets.count)!)
        collageStylePanel.collageModels = collageModels
    }
    
    var didSetup = false
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        
        if didSetup == false {
            didSetup = true
            let models = assets.map { PhotoModel(asset: $0) }
            let collageModels = CollageModel.collageModels(CollageImageCount(rawValue: assets.count)!)
            //因为Autolayout的原因。 我们不能在ViewDidload就获取正确的frame。而collageView内部
            //生成collageContentView需要正确的frame信息。所以选择在viewDidLayoutSubviews设置
            //TODO: 限制该界面旋转
            collageView.setupWithCollageModel(collageModels.first!, photoModels: models)
        }
        
    }
    
    //MARK: init
    init(assets: [PHAsset]) {
        self.assets = assets
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

//MARK: CollageStylePanel Delegate
extension CollageViewController: CollageStylePanelDelegate {
    func collageStylePanel(collageStylePanel: CollageStylePanel, didSelctModel model: CollageModel) {
        collageView.setupWithCollageModel(model)
    }
}

//MARK: ImageArrangedPanelDelegate Delegate
extension CollageViewController: ImageArrangedPanelDelegate {
    func imageArrangedPanel(imageArrangedPanel: ImageArrangedPanel, didEditModels models: [PhotoModel]) {
        
        let oldModels = collageView.photoModels!
        if oldModels.count == models.count {
            collageView.setupWithPhotoModels(models)
        }else{
            //如果图片数量改变，则collageModel也需要改变
            let count = CollageImageCount(rawValue: models.count)
            let collageModels = CollageModel.collageModels(count!)
            collageView.setupWithCollageModel(collageModels.first!, photoModels: models)
            self.collageStylePanel.collageModels = collageModels
        }
    }
}

//MARK: Actions
private extension Selector {
}

private extension CollageViewController {
    
    @objc func dismiss() {
        dismissViewControllerAnimated(true, completion: nil)
    }
    
    @objc func done() {
        
        let holder = UIView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        let collageView = CollageView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        holder.addSubview(collageView)
        collageView.setupWithCollageModel(self.collageView.collageModel!, photoModels: self.collageView.photoModels!)
        let image = holder.render()
        
        PHPhotoLibrary.sharedPhotoLibrary().performChanges({ 
            let newRequest = PHAssetChangeRequest.creationRequestForAssetFromImage(image)
            newRequest.creationDate = NSDate()
            }) { success, error in
        }
        
        if let nav = self.navigationController {
            nav.pushViewController(SharePhotoViewController(image: image), animated: true)
        }
    }
}
