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
    
    fileprivate lazy var collageStylePanel: CollageStylePanel = {
        let panel = CollageStylePanel(models: [])
        panel.delegate = self
        return panel
    }()
    
    fileprivate lazy var imageArrangedPanel: ImageArrangedPanel = {
        let panel = ImageArrangedPanel(models: [])
        panel.delegate = self
        return panel
    }()
    
    fileprivate let collageView = CollageView()
    
    fileprivate lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageArrangedPanel,self.collageView,self.collageStylePanel])
        stackView.axis = .vertical
        stackView.distribution = .equalSpacing
        stackView.alignment = .center
        return stackView
    }()

    fileprivate lazy var leftButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(dismissSelf))
    
    fileprivate lazy var rightButtonItem: UIBarButtonItem = UIBarButtonItem(title: tr(.done), style: .plain, target: self, action: #selector(done))
    
    //MARK: View Life Cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.title = tr(.collage)
        self.automaticallyAdjustsScrollViewInsets = false
        self.view.backgroundColor = .white
        self.navigationItem.setLeftBarButton(leftButtonItem, animated: false)
        self.navigationItem.setRightBarButton(rightButtonItem, animated: false)
        
        self.view.addSubview(stackView)
        stackView.snp.makeConstraints { (make) in
            make.top.equalTo(self.view.snp.top)
            make.bottom.equalTo(self.view.snp.bottom)
            make.left.right.equalTo(stackView.superview!)
        }
        //init layout
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
    
    //MARK: init
    init(assets: [PHAsset]) {
        self.assets = assets
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

//MARK: Layout

private let arrangedPanelConstant: CGFloat = 80
private let stylePanelConstant: CGFloat = 120

extension CollageViewController {
    
    override func viewWillTransition(to size: CGSize, with coordinator: UIViewControllerTransitionCoordinator) {
        
        coordinator.animate(alongsideTransition: { context  in
            self.setupConstraintForSize(self.view.size)
            self.collageView.resize()
            self.collageStylePanel.reload()
            }, completion: { context in
        })
    }
    
    fileprivate func setupConstraintForSize(_ size: CGSize) {
        
        if size.width > size.height {
            imageArrangedPanel.snp.makeConstraints({ (make) in
                make.width.equalTo(arrangedPanelConstant)
                make.height.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .vertical
            collageStylePanel.snp.makeConstraints({ (make) in
                make.width.equalTo(stylePanelConstant)
                make.height.equalTo(collageStylePanel.superview!)
            })
            collageView.snp.makeConstraints({ (make) in
                make.height.width.equalTo(collageView.superview!.snp.height)
            })
            stackView.axis = .horizontal
            stackView.layoutIfNeeded()
        } else {
            imageArrangedPanel.snp.makeConstraints({ (make) in
                make.height.equalTo(arrangedPanelConstant)
                make.width.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .horizontal
            collageStylePanel.snp.makeConstraints({ (make) in
                make.height.equalTo(stylePanelConstant)
                make.width.equalTo(collageStylePanel.superview!)
            })
            collageView.snp.makeConstraints({ (make) in
                make.height.width.equalTo(collageView.superview!.snp.height)
            })
            fixCornerCaseLayout(size)
            stackView.axis = .vertical
            stackView.layoutIfNeeded()
        }
    }
    
    fileprivate func fixCornerCaseLayout(_ size: CGSize) {
        /*用于修复Split View,Landscape Slide Over,Window Bounds: w:694 h:768时的界面问题*/
        let overflow: Bool = (size.width + arrangedPanelConstant + stylePanelConstant) > size.height
        if overflow {
            collageView.snp.makeConstraints ({ (make) in
                make.height.width.equalTo(400)
            })
        }
        //fix 3.5 inshes devices
        if Device.screen == .inches_3_5 {
            imageArrangedPanel.snp.makeConstraints({ (make) in
                make.height.equalTo(40)
                make.width.equalTo(imageArrangedPanel.superview!)
            })
            collageStylePanel.scrollDirection = .horizontal
            collageStylePanel.snp.makeConstraints({ (make) in
                make.height.equalTo(60)
                make.width.equalTo(collageStylePanel.superview!)
            })
            collageView.snp.makeConstraints({ (make) in
                make.height.width.equalTo(collageView.superview!.snp.height)
            })
        }
    }
}


//MARK: CollageStylePanel Delegate
extension CollageViewController: CollageStylePanelDelegate {
    func collageStylePanel(_ collageStylePanel: CollageStylePanel, didSelctModel model: CollageModel) {
        collageView.setupWithCollageModel(model)
    }
}

//MARK: ImageArrangedPanelDelegate Delegate
extension CollageViewController: ImageArrangedPanelDelegate {
    func imageArrangedPanel(_ imageArrangedPanel: ImageArrangedPanel, didEditModels models: [PhotoModel]) {
        
        let oldModels = collageView.photoModels!
        if oldModels.count == models.count {
            collageView.setupWithPhotoModels(models)
        } else {
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
    
    @objc func dismissSelf() {
        self.dismiss(animated: true, completion: nil)
    }
    
    @objc func done() {
        
        let holder = UIView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        let collageView = CollageView(frame: CGRect(x: 0, y: 0, width: 800, height: 800))
        holder.addSubview(collageView)
        collageView.setupWithCollageModel(self.collageView.collageModel!, photoModels: self.collageView.photoModels!,forEdit: false)
        let image = holder.render()
        
        PHPhotoLibrary.shared().performChanges({ 
            let newRequest = PHAssetChangeRequest.creationRequestForAsset(from: image)
            newRequest.creationDate = Date()
            }) { success, error in
        }
        
        if let nav = self.navigationController {
            nav.pushViewController(SharePhotoViewController(image: image), animated: true)
        }
    }
}
