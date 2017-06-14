//
//  BasePickerController.swift
//  Celluloid
//
//  Created by Mango on 16/4/20.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

open class BasePickerController: UIViewController {
    
    lazy var collectionView: UICollectionView = {
        
        let cellMargin = CGFloat(10)
        let layout = UICollectionViewFlowLayout()
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        layout.minimumLineSpacing = cellMargin
        layout.minimumInteritemSpacing = cellMargin
        layout.scrollDirection = .vertical
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.dataSource = self
        collectionView.delegate = self
        collectionView.backgroundColor = UIColor.white
        collectionView.registerClass(UICollectionViewCell.self)
        return collectionView
    }()
    
    override open func viewDidLoad() {
        super.viewDidLoad()
        
        view.addSubview(collectionView)
        collectionView.snp.makeConstraints { make in

            make.top.equalTo(self.view.top)
            make.bottom.equalTo(self.view.bottom)
            make.left.right.equalTo(collectionView.superview!)
        }

        
        let buttonItem = UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(dismissSelf))
        self.navigationItem.setLeftBarButton(buttonItem, animated: false)
    }
    
    override open func viewDidLayoutSubviews() {
        let layout = collectionView.collectionViewLayout as! UICollectionViewFlowLayout
        let cellMargin = CGFloat(10)
        let cellWidth = (view.width - cellMargin * 3)/2
        layout.itemSize = CGSize(width: cellWidth, height: cellWidth)
    }
    
}

//MARK: Action
extension BasePickerController {
    @objc func dismissSelf(){
        self.dismiss(animated: true, completion: nil)
    }
}

extension BasePickerController: UICollectionViewDataSource, UICollectionViewDelegate {
    
    public func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return 0
    }
    
    public func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        return UICollectionViewCell()
    }
}
