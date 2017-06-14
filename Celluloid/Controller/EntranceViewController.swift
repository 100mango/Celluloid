//
//  EntranceViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit
import BSImagePicker
import Async
import Photos

class EntranceViewController: UIViewController {
    
    lazy var editPhotoButton: IconButton = {
        let button = IconButton(image: UIImage(named: "EditPhotoEntranceButton")!, title: tr(.beautify))
        button.addTarget(self, action: .editPhoto, for: .touchUpInside)
        return button
    }()
    
    lazy var makeCollageButton: IconButton = {
        let button = IconButton(image: UIImage(named: "CollageEntranceButton")!, title: tr(.collage))
        button.addTarget(self, action: .makeCollage, for: .touchUpInside)
        return button
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.editPhotoButton,self.makeCollageButton])
        
        stackView.alignment = .fill
        stackView.spacing = 0
        stackView.axis = .vertical
        stackView.distribution = .fillEqually
        
        return stackView
    }()
    
    lazy var line: UIView = {
        let line = UIView()
        line.backgroundColor = .alphaWhiteColor
        return line
    }()
    
    //View Life Cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .black
        self.view.addSubview(stackView)
        stackView.snp.makeConstraints { (make) in
            make.edges.equalTo(stackView.superview!)
        }
        
        self.view.addSubview(line)
        line.snp.makeConstraints  { (make) in
            make.width.equalTo(245)
            make.height.equalTo(1)
            make.center.equalTo(line.superview!)
        }
    }
}

//MARK: Action
private extension Selector {
    static let editPhoto = #selector(EntranceViewController.editPhoto)
    static let makeCollage = #selector(EntranceViewController.makeCollage)
}


private extension EntranceViewController {
    
    @objc func editPhoto() {
        
        let picker = BSImagePickerViewController()
        picker.maxNumberOfSelections = 1
        
        presentPicker(picker) { assets in
            Async.main {
                if let asset = assets.first {
                    
                    let editVC = EditPhotoViewController(model: PhotoModel(asset: asset))
                    let navVC = UINavigationController(rootViewController: editVC)
                    
                    self.present(navVC, animated: true, completion: nil)
                    
                }
            }
        }
    }
    
    @objc func makeCollage() {
        
        let picker = BSImagePickerViewController()
        picker.maxNumberOfSelections = 4
        
        presentPicker(picker) { assets in
            
            Async.main {
                
                if assets.count == 1 {
                    
                    let editVC = EditPhotoViewController(model: PhotoModel(asset: assets.first!))
                    let navVC = UINavigationController(rootViewController: editVC)
                    
                    self.present(navVC, animated: true, completion: nil)
                    
                } else {
                    
                    let collageVC = CollageViewController(assets: assets)
                    let navVC = UINavigationController(rootViewController: collageVC)
                    
                    self.present(navVC, animated: true, completion: nil)
                }
                
            }
        }
        
    }
    
    func presentPicker(_ picker: BSImagePickerViewController,finish: @escaping ([PHAsset]) -> Void ) {
        bs_presentImagePickerController(picker, animated: true, select: nil, deselect: nil, cancel: nil, finish: finish, completion: nil)
    }
    
}


class IconButton: UIControl {
    
    let imageWidth = 62.5
    
    lazy var imageView: UIImageView = {
        let imageView = UIImageView()
        imageView.tintColor = .alphaWhiteColor
        imageView.snp.makeConstraints ({ (make) in
            make.size.equalTo(self.imageWidth)
        })
        return imageView
    }()
    
    lazy var label: UILabel = {
        let label = UILabel()
        label.font = UIFont.systemFont(ofSize: 18)
        label.textColor = .white
        label.textAlignment = .center
        return label
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageView,self.label])
        stackView.alignment = .center
        stackView.spacing = 35
        stackView.axis = .vertical
        return stackView
    }()
    
    lazy var button: UIButton = {
        let button = UIButton()
        button.addTarget(self, action: #selector(IconButton.touchUpInside), for: .touchUpInside)
        return button
    }()
    
    func resetState() {
        imageView.tintColor = .alphaWhiteColor
        label.textColor = .alphaWhiteColor
    }
    
    //MARK: init
    init(image: UIImage, title: String) {
        
        super.init(frame: CGRect.zero)
        
        imageView.image = image
        label.text = title
        
        self.addSubview(stackView)
        stackView.snp.makeConstraints  { (make) in
            make.center.equalTo(stackView.superview!)
        }
        
        self.addSubview(button)
        button.snp.makeConstraints  { (make) in
            make.edges.equalTo(button.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: Action
    @objc func touchUpInside() {
        self.sendActions(for: .touchUpInside)
    }
    
}


