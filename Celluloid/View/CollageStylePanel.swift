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
    func collageStylePanel(collageStylePanel: CollageStylePanel, didSelctModel model: CollageModel)
}

class CollageStylePanel: UIView {
    
    //MARK: Property
    private lazy var collectionView: UICollectionView = {
        
        let collectionView = UICollectionView(frame: .zero, collectionViewLayout: self.flowLayout)
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.backgroundColor = UIColor.whiteColor()
        collectionView.showsHorizontalScrollIndicator = false
        collectionView.registerClass(CollageStyleCell)
        
        return collectionView
        
    }()
    
    private lazy var flowLayout: UICollectionViewFlowLayout = {
        
        let layout = UICollectionViewFlowLayout()
        layout.itemSize = CGSize(width: 100, height: 100)
        layout.sectionInset = UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)
        layout.minimumLineSpacing = 5
        layout.minimumInteritemSpacing = 5
        layout.scrollDirection = .Horizontal
        
        return layout
    }()
    
    var collageModels: [CollageModel] {
        didSet {
            collectionView.reloadData()
        }
    }
    
    var scrollDirection: UICollectionViewScrollDirection = .Horizontal {
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
        collectionView.snp_makeConstraints { (make) in
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
        }else {
            flowLayout.itemSize = CGSize(width:  self.width - 20, height: self.width - 20)
        }
    }
}

//MARK: UICollectionViewDataSource
extension CollageStylePanel: UICollectionViewDataSource {
    
    func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return collageModels.count
    }
    
    func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell =  collectionView.dequeueReusableCellWithReuseIdentifier(CollageStyleCell.defaultReuseIdentifier, forIndexPath: indexPath) as! CollageStyleCell
        cell.configureWithImage(collageModels[indexPath.row].collageStyleImage)
        return cell
    }
    
}

//MARK: UICollectionViewDelegate
extension CollageStylePanel: UICollectionViewDelegate {
    
    func collectionView(collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: NSIndexPath) {
        self.delegate?.collageStylePanel(self, didSelctModel: collageModels[indexPath.row])
    }
    
}


//MARK: CollageStyleCell
class CollageStyleCell: UICollectionViewCell {
    
    let imageView: UIImageView = UIImageView()
    let mask: UIView = {
        let mask = UIView()
        mask.backgroundColor = UIColor.cellLightPurple.colorWithAlphaComponent(0.5)
        mask.hidden = true
        return mask
    }()
    
    override init(frame: CGRect) {
        
        super.init(frame: frame)
        self.backgroundColor = .cellLightPurple
        
        self.contentView.addSubview(imageView)
        imageView.snp_makeConstraints { (make) in
            make.edges.equalTo(imageView.superview!).inset(5)
        }
        self.contentView.addSubview(mask)
        mask.snp_makeConstraints { (make) in
            make.width.height.equalTo(imageView)
            make.center.equalTo(imageView)
        }
    }
    
    override var selected: Bool {
        didSet {
            if selected {
                mask.hidden = false
            }else{
                mask.hidden = true
            }
        }
    }
    
    func configureWithImage(image: UIImage) {
        imageView.image = image
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
}