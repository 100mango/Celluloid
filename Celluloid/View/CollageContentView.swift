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
    //call after set in superview
    func setup() {
        
        self.frame = model.points.frameWithNewSize(self.superview!.size)
        setupImage()
        crop()
        
        //设置 scroll view相关参数，便于恢复相关状态
        model.oldScrollViewSize = scrollView.size;
        model.contentOffset = CGPointZero;
        model.zoomScale = 1;
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
        let shape = CAShapeLayer()
        shape.frame = self.bounds;
        shape.path = path.CGPath;
        shape.lineWidth = 3
        shape.strokeColor = UIColor.blueColor().CGColor;
        shape.fillColor = UIColor.clearColor().CGColor;
        self.layer.addSublayer(shape)
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