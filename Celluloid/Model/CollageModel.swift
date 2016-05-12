//
//  CollageModel.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import JSONCodable

enum CollageImageCount: Int {
    case Two = 2
    case Three
    case Four
}

struct CollageModel {
    
    let imageName: String
    
    var collageStyleImage: UIImage { return UIImage(named: imageName)! }
    
    let areas: [[CGPoint]]
    
}

extension CollageModel {
    
    static func collageModels(imageCount: CollageImageCount) -> [CollageModel] {
        let key: String
        switch imageCount {
        case .Two:
            key = "two_pic"
        case .Three:
            key = "three_pic"
        case .Four:
            key = "four_pic"
        }
        
        
        func floatsToPoints(floats: [CGFloat]) -> [CGPoint] {
            var points = [CGPoint]()
            for index in 0.stride(to: floats.count, by: 2) {
                points.append(CGPoint(x: floats[index], y: floats[index+1]))
            }
            return points
        }
        
        let path =  NSBundle.mainBundle().pathForResource("collage", ofType: "json")
        if let jsonData = NSData(contentsOfFile: path!){
            let json = try! NSJSONSerialization.JSONObjectWithData(jsonData, options: NSJSONReadingOptions.MutableContainers) as! [String:AnyObject]
            let array = json[key] as! [[String:AnyObject]]
            
            return array.map{ dic -> CollageModel in
                let imageName = dic["drawable_name"] as! String
                let arrayOfFloats = dic["polygons"] as! [[CGFloat]]
                let arrayOfPoints = arrayOfFloats.map{
                    floatsToPoints($0)
                }
                let collageModel = CollageModel(imageName: imageName, areas: arrayOfPoints)
                return collageModel
            }
        }else{
            return [CollageModel]()
        }
        
    }
}

//MARK: [CGFloat] extension (generate frame or path form array of CGFloat)

protocol CGPointWrapper {
    var point : CGPoint { get }
}

extension CGPoint : CGPointWrapper {
    var point : CGPoint {
        return self
    }
}

private let oldSize = CGSize(width: 100, height: 100)

extension Array where Element: CGPointWrapper {
    
    
    func frameWithNewSize(newSize: CGSize) -> CGRect {
        return frameWithOldSize(oldSize, newSize: newSize)
    }
    
    func frameWithOldSize(oldSize: CGSize, newSize: CGSize) -> CGRect {
        
        let path = self.path
        var frame = CGPathGetBoundingBox(path.CGPath)
        //newSize与oldSize的比例一致,因为都是正方形,这里长宽的放缩比例相同
        let scale = newSize.width/oldSize.width;
        frame = CGRectApplyAffineTransform(frame, CGAffineTransformMakeScale(scale, scale));
        return frame;
    }
    
    func cropPath(newSize: CGSize) -> UIBezierPath {
        return pathWithOldSize(oldSize, newSize: newSize)
    }
    
    func pathWithOldSize(oldSize: CGSize, newSize: CGSize) -> UIBezierPath {
        
        let path = self.path
        
        let frame = CGPathGetBoundingBox(path.CGPath);
        //newSize与oldSize的比例一致,因为都是正方形,这里长宽的放缩比例相同
        let scale = newSize.width/oldSize.width;
        //bezierPath用于剪切ScrollView而不是整个拼图区域。需要将它回归到原点
        let move = CGAffineTransformMakeTranslation(-frame.origin.x, -frame.origin.y);
        let scaleTransform = CGAffineTransformMakeScale(scale, scale);
        let transform = CGAffineTransformConcat(move, scaleTransform);
        path.applyTransform(transform)
        return path
    }
    
    private var path: UIBezierPath {
        let path = UIBezierPath()
        
        for index in 0..<self.count {
            let point = self[index].point
            if index == 0 {
                path.moveToPoint(point)
            }else {
                path.addLineToPoint(point)
            }
        }
        path.closePath()
        return path
    }
}



