//
//  UIViewExtension.swift
//  3D
//
//  Created by Mango on 15/12/7.
//  Copyright © 2015年 Mango. All rights reserved.
//

import UIKit

//MARK: UIView

public extension UIView{
    
    public var width: CGFloat {
        get { return self.frame.size.width }
        set { self.frame.size.width = newValue }
    }
    
    public var height: CGFloat {
        get { return self.frame.size.height }
        set { self.frame.size.height = newValue }
    }
    
    public var top: CGFloat {
        get { return self.frame.origin.y }
        set { self.frame.origin.y = newValue }
    }
    public var right: CGFloat {
        get { return self.frame.origin.x + self.width }
        set { self.frame.origin.x = newValue - self.width }
    }
    public var bottom: CGFloat {
        get { return self.frame.origin.y + self.height }
        set { self.frame.origin.y = newValue - self.height }
    }
    public var left: CGFloat {
        get { return self.frame.origin.x }
        set { self.frame.origin.x = newValue }
    }
    
    public var centerX: CGFloat{
        get { return self.center.x }
        set { self.center = CGPoint(x: newValue,y: self.centerY) }
    }
    public var centerY: CGFloat {
        get { return self.center.y }
        set { self.center = CGPoint(x: self.centerX,y: newValue) }
    }
    
    public var origin: CGPoint {
        set { self.frame.origin = newValue }
        get { return self.frame.origin }
    }
    public var size: CGSize {
        set { self.frame.size = newValue }
        get { return self.frame.size }
    }
}

public extension UIView {
    public var parentViewController: UIViewController? {
        var parentResponder: UIResponder? = self
        while let responder = parentResponder {
            parentResponder = responder.next
            if let viewController = parentResponder as? UIViewController {
                return viewController
            }
        }
        return nil
    }
}

public extension UIView {
    
    public func renderWithBounds(_ bounds: CGRect? = nil) -> UIImage {
        let bounds = bounds ?? self.bounds
        UIGraphicsBeginImageContextWithOptions(bounds.size, true, 0);
        drawHierarchy(in: CGRect(x: -bounds.origin.x, y: -bounds.origin.y, width: self.width , height: self.height), afterScreenUpdates: true)
        let screenshot = UIGraphicsGetImageFromCurrentImageContext();
        UIGraphicsEndImageContext();
        return screenshot!;
    }
    
    public func render() -> UIImage {
        UIGraphicsBeginImageContextWithOptions(self.bounds.size, false, 0);
        self.layer.render(in: UIGraphicsGetCurrentContext()!)
        let render = UIGraphicsGetImageFromCurrentImageContext()
        UIGraphicsEndImageContext()
        return render!
    }
}

//MARK: CGAffineTransform
public extension CGAffineTransform {
    public var angle:CGFloat { return atan2(self.b,self.a) }
}

//MARK: CGPoint
public func CGPointGetDistance(_ point1:CGPoint, _ point2:CGPoint) -> CGFloat {
    let fx = point2.x - point1.x;
    let fy = point2.y - point1.y;
    
    return sqrt((fx*fx + fy*fy));
}

//MARK: CGRect
public extension CGRect {
    public func scaled(_ sx: CGFloat, _ sy: CGFloat) -> CGRect {
        return CGRect(x: self.origin.x * sx, y: self.origin.y * sy, width: self.width * sx, height: self.height * sy);
    }
}

//MARK: UIButton
public extension UIButton {
    
    func alignImageAndTitleVertically(_ padding: CGFloat = 6.0) {
        let imageSize = self.imageView!.frame.size
        let titleSize = self.titleLabel!.frame.size
        let totalHeight = imageSize.height + titleSize.height + padding
        
        self.imageEdgeInsets = UIEdgeInsets(
            top: -(totalHeight - imageSize.height),
            left: 0,
            bottom: 0,
            right: -titleSize.width
        )
        
        self.titleEdgeInsets = UIEdgeInsets(
            top: 0,
            left: -imageSize.width,
            bottom: -(totalHeight - titleSize.height),
            right: 0
        )
    }
    
    
    func setImageinFrame(_ frame: CGRect){
        self.imageEdgeInsets = UIEdgeInsets(
            top: frame.minY - self.frame.minY,
            left: frame.minX - self.frame.minX,
            bottom: self.frame.maxY - frame.maxY,
            right: self.frame.maxX - frame.maxX
        )
    }
}

//MARK: imageView
public extension UIImageView {
    public var imageRect: CGRect {
        guard self.contentMode == .scaleAspectFit && self.width != 0 && self.height != 0 else {
            return self.bounds
        }
        
        if let image = self.image {
            let size = image.size
            let imageScale = CGFloat(fminf(Float(self.bounds.width/size.width), Float(self.bounds.height/size.height)))
            let scaledImageSize = CGSize(width: size.width*imageScale, height: size.height*imageScale)
            let imageRect = CGRect(x: round(CGFloat(0.5)*(self.bounds.width-scaledImageSize.width)), y: round(CGFloat(0.5)*(self.bounds.height-scaledImageSize.height)), width: round(scaledImageSize.width), height: round(scaledImageSize.height));
            return imageRect
        }else{
            return self.bounds
        }
    }
    
}

//MARK: UITableView,UITableViewCell,UICollectionView,UICollectionViewCell

public extension UITableView{
    public func registerClass(_ cellType:UITableViewCell.Type){
        register(cellType, forCellReuseIdentifier: cellType.defaultReuseIdentifier)
    }
    
    public func dequeueReusableCellForIndexPath<T: UITableViewCell>(_ indexPath: IndexPath) -> T {
        guard let cell = self.dequeueReusableCell(withIdentifier: T.defaultReuseIdentifier , for: indexPath) as? T else {
            fatalError( "Failed to dequeue a cell with identifier \(T.defaultReuseIdentifier). Ensure you have registered the cell." )
        }
        
        return cell
    }
}

public extension UITableViewCell{
    public static var defaultReuseIdentifier:String{
        return String(describing: self)
    }
}

public extension UICollectionView{
    public func registerClass(_ cellType:UICollectionViewCell.Type){
        register(cellType, forCellWithReuseIdentifier: cellType.defaultReuseIdentifier)
    }
    
    public func dequeueReusableCellForIndexPath<T: UICollectionViewCell>(_ indexPath: IndexPath) -> T {
        guard let cell = self.dequeueReusableCell(withReuseIdentifier: T.defaultReuseIdentifier, for: indexPath) as? T else {
            fatalError( "Failed to dequeue a cell with identifier \(T.defaultReuseIdentifier).  Ensure you have registered the cell" )
        }
        
        return cell
    }
}

public extension UICollectionViewCell{
    public static var defaultReuseIdentifier:String{
        return String(describing: self)
    }
}
