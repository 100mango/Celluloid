//
//  BubblePickerViewController.swift
//  Celluloid
//
//  Created by Mango on 16/3/2.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit

private let bubbleImages:[UIImage.Asset] = [.Aside1,.Call1,.Call2,.Call3,.Say1,.Say2,.Say3,.Think1,.Think2,.Think3]


public class BubblePickerViewController:UIViewController {
    
    lazy var collectionView: UICollectionView = {
        
        let cellMargin = CGFloat(10)
        let cellWidth = (self.view.width - cellMargin * 4)/3
        let layout = UICollectionViewFlowLayout()
        layout.itemSize = CGSize(width: cellWidth, height: cellWidth)
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
    
    //MARK: init
    private func commonInit() {
        
    }
    
    override init(nibName nibNameOrNil: String?, bundle nibBundleOrNil: NSBundle?) {
        super.init(nibName: nibNameOrNil, bundle: nibBundleOrNil)
        commonInit()
        
    }

    required public init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        commonInit()
    }
    
    //MARK: View life cycle
    public override func viewDidLoad() {
        super.viewDidLoad()
        
        view.addSubview(collectionView)
        collectionView.snp_makeConstraints { (make) -> Void in
            make.top.equalTo(topLayoutGuide).offset(44)
            make.bottom.equalTo(bottomLayoutGuide)
            make.left.right.equalTo(collectionView.superview!)
        }
        
        //TODO: Swift2.2 improve #@selctor
        let buttonItem = UIBarButtonItem(title: "取消", style: .Plain, target: self, action: Selector("dismiss"))
        self.navigationItem.setLeftBarButtonItem(buttonItem, animated: false)
        self.navigationItem.title = "选择气泡"
    }
}

//MARK: Action
private extension BubblePickerViewController {
    @objc func dismiss(){
        dismissViewControllerAnimated(true, completion: nil)
    }
}

//MARK: CollectionView Data Source
extension BubblePickerViewController:UICollectionViewDataSource {
    
    public func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return bubbleImages.count
    }
    
    public func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = Style.cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        imageView.image = UIImage(asset: bubbleImages[indexPath.row])
        cell.contentView.addSubview(imageView)
        return cell
    }
    
}

//MARK: CollectionView delegate
extension BubblePickerViewController:UICollectionViewDelegate {
}

