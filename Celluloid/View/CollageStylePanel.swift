//
//  CollageStylePanel.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import CelluloidKit

protocol CollageStylePanelDelegate: class {
    func collageStylePanel(_ collageStylePanel: CollageStylePanel, didSelctModel model: CollageModel)
}

class CollageStylePanel: UIView {
    
    //MARK: Property
    fileprivate lazy var collectionView: UICollectionView = {
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: self.flowLayout)
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.backgroundColor = UIColor.white
        collectionView.showsHorizontalScrollIndicator = false
        collectionView.registerClass(CollageStyleCell.self)
        
        return collectionView
        
    }()
    
    fileprivate lazy var flowLayout: UICollectionViewFlowLayout = {
        
        let layout = UICollectionViewFlowLayout()
        layout.itemSize = CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.minimumInteritemSpacing = 5
        layout.scrollDirection = .horizontal
        
        return layout
    }()
    
    var collageModels: [CollageModel] {
        didSet {
            collectionView.reloadData()
        }
    }
    
    var scrollDirection: UICollectionViewScrollDirection = .horizontal {
        didSet {
            let layout = collectionView.collectionViewLayout as! UICollectionViewFlowLayout
            layout.scrollDirection = scrollDirection
        }
    }
    
    weak var delegate: CollageStylePanelDelegate?
    
    //MARK: init
    init(models: [CollageModel]) {
        self.collageModels = models
        super.init(frame: CGRect.zero)
        self.addSubview(collectionView)
        collectionView.snp.makeConstraints  { (make) in
            make.edges.equalTo(collectionView.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: layout
    override func layoutSubviews() {
        if self.width > self.height {
            flowLayout.itemSize = CGSize(width:  self.height - 20, height: self.height - 20)
        } else {
            flowLayout.itemSize = CGSize(width:  self.width - 20, height: self.width - 20)
        }
    }
    
    func reload() {
        self.collectionView.reloadData()
    }
}

//MARK: UICollectionViewDataSource
extension CollageStylePanel: UICollectionViewDataSource {
    
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return collageModels.count
    }
    
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        
        let cell = collectionView.dequeueReusableCellForIndexPath(indexPath) as CollageStyleCell
        cell.configureWithImage(collageModels[indexPath.row].collageStyleImage)
        return cell
    }
    
}

//MARK: UICollectionViewDelegate
extension CollageStylePanel: UICollectionViewDelegate {
    
    func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        self.delegate?.collageStylePanel(self, didSelctModel: collageModels[indexPath.row])
    }
    
}


//MARK: CollageStyleCell
class CollageStyleCell: UICollectionViewCell {
    
    let imageView: UIImageView = UIImageView()
    let maskview: UIView = {
        let mask = UIView()
        mask.backgroundColor = UIColor.cellLightPurple.withAlphaComponent(0.5)
        mask.isHidden = true
        return mask
    }()
    
    override init(frame: CGRect) {
        
        super.init(frame: frame)
        self.backgroundColor = .cellLightPurple
        
        self.contentView.addSubview(imageView)
        imageView.snp.makeConstraints { (make) in
            make.edges.equalTo(imageView.superview!).inset(5)
        }
        

        self.contentView.addSubview(maskview)
        maskview.snp.makeConstraints { (make) in
            make.width.height.equalTo(imageView)
            make.center.equalTo(imageView)
        }
    }
    
    override var isSelected: Bool {
        didSet {
            if isSelected {
                maskview.isHidden = false
            }else{
                maskview.isHidden = true
            }
        }
    }
    
    func configureWithImage(_ image: UIImage) {
        imageView.image = image
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
}
