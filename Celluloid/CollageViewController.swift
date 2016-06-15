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
import AssistantKit

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
    
    private let collageView = CollageView()
    
    private lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageArrangedPanel,self.collageView,self.collageStylePanel])
        stackView.axis = .Vertical
        stackView.distribution = .EqualSpacing
        stackView.alignment = .Center
        return stackView
    }()

    private lazy var leftButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Cancel), style: .Plain, target: self, action: #selector(dismiss))
    
    private lazy var rightButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.Done), style: .Plain, target: self, action: #selector(done))

    //MARK: View Life Cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.title = tr(.Collage)
        self.automaticallyAdjustsScrollViewInsets = false
        self.view.backgroundColor = .whiteColor()
        self.navigationItem.setLeftBarButtonItem(leftButtonItem, animated: false)
        self.navigationItem.setRightBarButtonItem(rightButtonItem, animated: false)
        
        self.view.addSubview(stackView)
        stackView.snp_makeConstraints { (make) in
            make.top.equalTo(self.snp_topLayoutGuideBottom)
            make.bottom.equalTo(self.snp_bottomLayoutGuideTop)
            make.left.right.equalTo(stackView.superview!)
        }
        setupConstraintForSize(self.view.size)
        
        //setup data for views
        let models = assets.map { PhotoModel(asset: $0) }
        let collageModels = CollageModel.collageModels(CollageImageCount(rawValue: assets.count)!)
        //arrangedPanel
        imageArrangedPanel.photoModels = models
        imageArrangedPanel.reload()
        //stylePanel
        collageStylePanel.collageModels = collageModels
        //collageView
        collageView.setupWithCollageModel(collageModels.first!, photoModels: models)
    }
    
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        
        collageView.resize()
    }
    
    override func viewWillTransitionToSize(size: CGSize, withTransitionCoordinator
        coordinator: UIViewControllerTransitionCoordinator) {
        super.viewWillTransitionToSize(size, withTransitionCoordinator: coordinator)
        setupConstraintForSize(size)
    }
    
    private let arrangedPanelConstant: CGFloat = 80
    private let stylePanelConstant: CGFloat = 120
    
    private func setupConstraintForSize(size: CGSize) {
        
        if size.width > size.height {
            imageArrangedPanel.snp_remakeConstraints(closure: { (make) in
                make.width.equalTo(arrangedPanelConstant)
                make.height.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .Vertical
            collageStylePanel.snp_remakeConstraints(closure: { (make) in
                make.width.equalTo(stylePanelConstant)
                make.height.equalTo(collageStylePanel.superview!)
            })
            collageView.snp_remakeConstraints(closure: { (make) in
                make.height.width.equalTo(collageView.superview!.snp_height)
            })
            stackView.axis = .Horizontal
            stackView.layoutIfNeeded()
        } else {
            imageArrangedPanel.snp_remakeConstraints(closure: { (make) in
                make.height.equalTo(arrangedPanelConstant)
                make.width.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .Horizontal
            collageStylePanel.snp_remakeConstraints(closure: { (make) in
                make.height.equalTo(stylePanelConstant)
                make.width.equalTo(collageStylePanel.superview!)
            })
            collageView.snp_remakeConstraints(closure: { (make) in
                make.height.width.equalTo(collageView.superview!.snp_width)
            })
            fixCornerCaseLayout(size)
            stackView.axis = .Vertical
            stackView.layoutIfNeeded()
        }
    }
    
    private func fixCornerCaseLayout(size: CGSize) {
        /*用于修复Split View,Landscape Slide Over,Window Bounds: w:694 h:768时的界面问题*/
        let overflow: Bool = (size.width + arrangedPanelConstant + stylePanelConstant) > size.height
        if overflow {
            collageView.snp_remakeConstraints(closure: { (make) in
                make.height.width.equalTo(400)
            })
        }
        //fix 3.5 inshes devices
        if Device.screen == .Inches_3_5 {
            imageArrangedPanel.snp_remakeConstraints(closure: { (make) in
                make.height.equalTo(40)
                make.width.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .Horizontal
            collageStylePanel.snp_remakeConstraints(closure: { (make) in
                make.height.equalTo(60)
                make.width.equalTo(collageStylePanel.superview!)
            })
            collageView.snp_remakeConstraints(closure: { (make) in
                make.height.width.equalTo(collageView.superview!.snp_width)
            })
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
        collageView.setupWithCollageModel(self.collageView.collageModel!, photoModels: self.collageView.photoModels!,forEdit: false)
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
