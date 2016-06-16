//
//  BasePickerController.swift
//  Celluloid
//
//  Created by Mango on 16/4/20.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public class BasePickerController: UIViewController {
    
    lazy var collectionView: UICollectionView = {
        
        let cellMargin = CGFloat(10)
        let layout = UICollectionViewFlowLayout()
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        layout.minimumLineSpacing = cellMargin
        layout.minimumInteritemSpacing = cellMargin
        layout.scrollDirection = .Vertical
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.dataSource = self
        collectionView.delegate = self
        collectionView.backgroundColor = UIColor.whiteColor()
        collectionView.registerClass(UICollectionViewCell)
        return collectionView
    }()
    
    override public func viewDidLoad() {
        super.viewDidLoad()
        
        view.addSubview(collectionView)
        collectionView.snp_makeConstraints { (make) -> Void in
            make.top.equalTo(topLayoutGuide)
            make.bottom.equalTo(bottomLayoutGuide)
            make.left.right.equalTo(collectionView.superview!)
        }
        
        let buttonItem = UIBarButtonItem(title: tr(.Cancel), style: .Plain, target: self, action: #selector(dismiss))
        self.navigationItem.setLeftBarButtonItem(buttonItem, animated: false)
    }
    
    override public func viewDidLayoutSubviews() {
        let layout = collectionView.collectionViewLayout as! UICollectionViewFlowLayout
        let cellMargin = CGFloat(10)
        let cellWidth = (view.width - cellMargin * 3)/2
        layout.itemSize = CGSize(width: cellWidth, height: cellWidth)
    }
    
}

//MARK: Action
private extension BasePickerController {
    @objc func dismiss(){
        dismissViewControllerAnimated(true, completion: nil)
    }
}

extension BasePickerController: UICollectionViewDataSource, UICollectionViewDelegate {
    
    public func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return 0
    }
    
    public func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        return UICollectionViewCell()
    }
}