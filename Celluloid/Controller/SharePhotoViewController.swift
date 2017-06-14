//
//  SharePhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/27.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit

class SharePhotoViewController: UIViewController {
    
    lazy var shareButton: UIButton = {
        let button = UIButton()
        button.setTitle(tr(.share), for: .normal)
        button.addTarget(self, action: .share, for: .touchUpInside)
        button.layer.cornerRadius = 22
        button.layer.borderWidth = 1
        button.layer.borderColor = UIColor.white.cgColor
        button.backgroundColor = .clear
        return button
    }()
    
    lazy var doneButton: UIButton = {
        let button = UIButton()
        button.setTitle(tr(.done), for: .normal)
        button.addTarget(self, action: .done, for: .touchUpInside)
        button.layer.cornerRadius = 22
        button.layer.borderWidth = 1
        button.layer.borderColor = UIColor.white.cgColor
        button.backgroundColor = .clear
        return button
    }()
    
    let savedIcon = UIImageView(image: UIImage(named: "saved"))
    let savedLabel: UILabel = {
        let label = UILabel()
        label.text = tr(.saved)
        label.font = .systemFont(ofSize: 20)
        label.textColor = .white
        return label
    }()
    
    
    let image: UIImage

    init(image: UIImage) {
        self.image = image
        super.init(nibName: nil, bundle: nil)
        self.view.backgroundColor = .blackBackgroundColor
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.navigationItem.hidesBackButton = true
        
        self.view.addSubview(shareButton)
        shareButton.snp.makeConstraints  { (make) in
            make.centerX.equalTo(shareButton.superview!)
            make.centerY.equalTo(shareButton.superview!).offset(100)
            make.width.equalTo(140)
            make.height.equalTo(44)
        }
        
        self.view.addSubview(doneButton)
        doneButton.snp.makeConstraints  { (make) in
            make.top.equalTo(shareButton.snp.bottom).offset(20)
            make.centerX.equalTo(shareButton)
            make.width.equalTo(140)
            make.height.equalTo(44)
        }
        
        self.view.addSubview(savedIcon)
        savedIcon.snp.makeConstraints  { (make) in
            make.centerY.equalTo(savedIcon.superview!).offset(-100)
            make.centerX.equalTo(savedIcon.superview!)
        }
        
        self.view.addSubview(savedLabel)
        savedLabel.snp.makeConstraints  { (make) in
            make.top.equalTo(savedIcon.snp.bottom).offset(30)
            make.centerX.equalTo(savedIcon)
        }
    }
    
}

//MARK: Action
private extension Selector {
    static let share = #selector(SharePhotoViewController.share)
    static let done =  #selector(SharePhotoViewController.done)
}

extension SharePhotoViewController {
    
    @objc func share() {
        let activityViewController = UIActivityViewController(activityItems: [image], applicationActivities: nil)
        activityViewController.popoverPresentationController?.sourceView = self.shareButton
        present(activityViewController, animated: true, completion: nil)
    }
    
    @objc func done() {
        dismiss(animated: true, completion: nil)
    }
}
