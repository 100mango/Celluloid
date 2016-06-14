//
//  CollageContentView.swift
//  Celluloid
//
//  Created by Mango on 16/5/10.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

class CollageContentView: UIView {
    
    private lazy var scrollView: UIScrollView = {
        let scrollView = UIScrollView()
        scrollView.backgroundColor = .clearColor()
        scrollView.delegate = self
        scrollView.minimumZoomScale = 1
        scrollView.maximumZoomScale = 5
        scrollView.bounces = false
        scrollView.showsVerticalScrollIndicator = false
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.addSubview(self.imageView)
        
        return scrollView
    }()
    
    private let imageView: UIImageView = UIImageView()
    
    private let border = CAShapeLayer()
    
    var model: PhotoModel
    
    init(model: PhotoModel) {
        self.model = model
        super.init(frame: CGRect.zero)
        self.addSubview(scrollView)
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    
}

//MARK: layout
extension CollageContentView {
    
    //call in superview's layout subviews method
    func layout() {
        setup()
    }
    
    private func setup() {
        self.frame = model.points.frameWithNewSize(self.superview!.size)
        scrollView.frame = self.bounds
        setupImage()
        crop()
    }
    
    //call after added as a subview
    func setupForEdit() {
        
        setup()
        //设置 scroll view相关参数，便于恢复相关状态
        model.oldScrollViewSize = scrollView.size;
    }
    
    func setupForRender() {
        
        setup()
        //从model的相关参数恢复相关放大，偏移状态
        let scale = scrollView.size.width / model.oldScrollViewSize.width
        let tranfrom = CGAffineTransformMakeScale(scale, scale)
        let newOffset = CGPointApplyAffineTransform(model.contentOffset, tranfrom)
        scrollView.zoomScale = model.zoomScale
        scrollView.contentOffset = newOffset
        //设置Preview所需状态
        scrollView.scrollEnabled = false
        let tap = UITapGestureRecognizer(target: self, action: #selector(CollageContentView.touch))
        self.addGestureRecognizer(tap)
    }
    
    private func setupImage() {
        model.requstImage { image in
            self.imageView.image = image
            var imageViewSize = CGSize.zero
            //确保imageView保持image的宽高比,且占满ScrollView
            if (self.width >= self.height) {
                imageViewSize.width = self.width
                imageViewSize.height = imageViewSize.width * (image.size.height/image.size.width)
                if imageViewSize.height < self.height {
                    imageViewSize.height = self.height;
                    imageViewSize.width = imageViewSize.height * (image.size.width/image.size.height);
                }
            }else{
                imageViewSize.height = self.height;
                imageViewSize.width = imageViewSize.height * (image.size.width/image.size.height);
                if (imageViewSize.width < self.width) {
                    imageViewSize.width = self.width;
                    imageViewSize.height = imageViewSize.width * (image.size.height/image.size.width);
                }
            }
            
            self.imageView.size = imageViewSize;
            self.scrollView.contentSize = imageViewSize;
        }
    }
    
    private func crop() {
        let path = model.points.cropPath(self.superview!.size)
        let shapeLayer = CAShapeLayer()
        shapeLayer.frame = self.bounds
        shapeLayer.path = path.CGPath
        self.layer.mask = shapeLayer
        
        //边框线
        border.frame = self.bounds;
        border.path = path.CGPath;
        border.lineWidth = 3
        border.strokeColor = UIColor.blackColor().CGColor;
        border.fillColor = UIColor.clearColor().CGColor;
        if border.superlayer == nil {
            self.layer.addSublayer(border)
        }
    }
}

//MARK: Action
private extension CollageContentView {
    @objc func touch() {
        
    }
}

//MARK: UIScrollViewDelegate
extension CollageContentView: UIScrollViewDelegate {
    
    func viewForZoomingInScrollView(scrollView: UIScrollView) -> UIView? {
        return imageView
    }
    
    func scrollViewDidZoom(scrollView: UIScrollView) {
        model.zoomScale = scrollView.zoomScale
    }
    
    func scrollViewDidScroll(scrollView: UIScrollView) {
        model.contentOffset = scrollView.contentOffset
    }
    
}