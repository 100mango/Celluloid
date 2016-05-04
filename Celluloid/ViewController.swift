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

    override func viewDidLoad() {
        super.viewDidLoad()
        
        let button = UIButton()
        button.size = CGSize(width: 50, height: 50)
        button.backgroundColor = UIColor.redColor()
        button.center = self.view.center
        self.view.addSubview(button)
        button.addTarget(self, action: .touch, forControlEvents: .TouchUpInside)
        
        print(CollageModel.collageModels(.Two))
    }

    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
        // Dispose of any resources that can be recreated.
    }

}


//MARK: Actions
private extension Selector {
    static let touch = #selector(ViewController.touch)
}

extension ViewController {
    
    @objc func touch() {
        let vc = BSImagePickerViewController()
        vc.maxNumberOfSelections = 6
        
        bs_presentImagePickerController(vc, animated: true,
                                        select: nil, deselect: nil, cancel: nil,
                                        finish: { (assets: [PHAsset]) -> Void in
                                        
                                            Async.main {
                                                let models = assets.map { PhotoModel(asset: $0) }
                                                let arrangedView = ImageArrangedView(models: models)
                                                self.view.addSubview(arrangedView)
                                                arrangedView.snp_makeConstraints(closure: { (make) in
                                                    make.top.equalTo(self.topLayoutGuide)
                                                    make.left.right.equalTo(self.view)
                                                    make.height.equalTo(80)
                                                })
                                            }
            }
            , completion: nil)
    }
    
}
