//
//  CollageViewController.swift
//  Celluloid
//
//  Created by Mango on 16/2/26.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import CelluloidKit
import Photos

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
            make.top.equalTo(self.view.safeAreaLayoutGuide.snp.top)
            make.bottom.equalTo(self.view.safeAreaLayoutGuide.snp.bottom)
            make.left.right.equalTo(stackView.superview!)
        }
        //init layout
        setupConstraintForSize(self.view.size)
        
        //setup data for views
        let models = assets.map { PhotoModel(asset: $0) }
        guard let count = CollageImageCount(rawValue: assets.count) else { return }
        let collageModels = CollageModel.collageModels(count)
        guard let first = collageModels.first else { return }
        //arrangedPanel
        imageArrangedPanel.photoModels = models
        imageArrangedPanel.reload()
        //stylePanel
        collageStylePanel.collageModels = collageModels
        //collageView
        collageView.setupWithCollageModel(first, photoModels: models)
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
        
        super.viewWillTransition(to: size, with: coordinator)
        coordinator.animate(alongsideTransition: { context  in
            self.setupConstraintForSize(self.view.size)
            self.collageView.resize()
            self.collageStylePanel.reload()
            }, completion: { context in
        })
    }
    
    fileprivate func setupConstraintForSize(_ size: CGSize) {
        let horizontal = size.width > size.height
        stackView.axis = horizontal ? .horizontal : .vertical
        collageStylePanel.scrollDirection = horizontal ? .vertical : .horizontal
        let available = view.safeAreaLayoutGuide.layoutFrame.size
        let side = max(1, min(available.width - (horizontal ? arrangedPanelConstant + stylePanelConstant : 0),
                              available.height - (horizontal ? 0 : arrangedPanelConstant + stylePanelConstant)))
        imageArrangedPanel.snp.remakeConstraints { make in
            if horizontal { make.width.equalTo(arrangedPanelConstant); make.height.equalToSuperview() }
            else { make.height.equalTo(arrangedPanelConstant); make.width.equalToSuperview() }
        }
        collageStylePanel.snp.remakeConstraints { make in
            if horizontal { make.width.equalTo(stylePanelConstant); make.height.equalToSuperview() }
            else { make.height.equalTo(stylePanelConstant); make.width.equalToSuperview() }
        }
        collageView.snp.remakeConstraints { $0.width.height.equalTo(side) }
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        setupConstraintForSize(view.bounds.size)
        collageView.resize()
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
        
        rightButtonItem.isEnabled = false
        PHPhotoLibrary.shared().performChanges({
            PHAssetChangeRequest.creationRequestForAsset(from: image).creationDate = Date()
        }) { [weak self] success, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.rightButtonItem.isEnabled = true
                if success {
                    self.navigationController?.pushViewController(SharePhotoViewController(image: image), animated: true)
                } else {
                    let alert = UIAlertController(title: NSLocalizedString("Unable to Save", comment: "Save error"), message: error?.localizedDescription, preferredStyle: .alert)
                    alert.addAction(UIAlertAction(title: tr(.done), style: .default))
                    self.present(alert, animated: true)
                }
            }
        }
    }
}
