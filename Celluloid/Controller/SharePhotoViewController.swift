//
//  SharePhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/27.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class SharePhotoViewController: UIViewController {
    
    lazy var shareButton: UIButton = {
        let button = UIButton()
        button.setTitle("分享", forState: .Normal)
        button.addTarget(self, action: .share, forControlEvents: .TouchUpInside)
        button.layer.cornerRadius = 22
        button.layer.borderWidth = 1
        button.layer.borderColor = UIColor.whiteColor().CGColor
        button.backgroundColor = .clearColor()
        return button
    }()
    
    let image: UIImage

    init(image: UIImage) {
        self.image = image
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        self.view.addSubview(shareButton)
        shareButton.snp_makeConstraints { (make) in
            make.center.equalTo(shareButton.superview!)
            make.height.equalTo(44)
            make.width.equalTo(140)
        }
        
    }
    
}

//MARK: Action
private extension Selector {
    static let share = #selector(SharePhotoViewController.share)
}

extension SharePhotoViewController {
    
    @objc func share() {
        let activityViewController = UIActivityViewController(activityItems: [image], applicationActivities: nil)
        activityViewController.popoverPresentationController?.sourceView = self.view
        presentViewController(activityViewController, animated: true, completion: nil)
    }
}