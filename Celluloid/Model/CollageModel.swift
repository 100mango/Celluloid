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
    case two = 2
    case three
    case four
}

struct CollageModel {
    
    let imageName: String
    
    var collageStyleImage: UIImage { return UIImage(named: imageName)! }
    
    let areas: [[CGPoint]]
    
}

extension CollageModel {
    
    static func collageModels(_ imageCount: CollageImageCount) -> [CollageModel] {
        let key: String
        switch imageCount {
        case .two:
            key = "two_pic"
        case .three:
            key = "three_pic"
        case .four:
            key = "four_pic"
        }
        
        
        func floatsToPoints(_ floats: [CGFloat]) -> [CGPoint] {
            var points = [CGPoint]()
            for index in stride(from: 0, to: floats.count, by: 2) {
                points.append(CGPoint(x: floats[index], y: floats[index+1]))
            }
            return points
        }
        
        let path =  Bundle.main.path(forResource: "collage", ofType: "json")
        if let jsonData = try? Data(contentsOf: URL(fileURLWithPath: path!)){
            let json = try! JSONSerialization.jsonObject(with: jsonData, options: JSONSerialization.ReadingOptions.mutableContainers) as! [String:AnyObject]
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
    
    
    func frameWithNewSize(_ newSize: CGSize) -> CGRect {
        return frameWithOldSize(oldSize, newSize: newSize)
    }
    
    func frameWithOldSize(_ oldSize: CGSize, newSize: CGSize) -> CGRect {
        
        let path = self.path
        var frame = path.cgPath.boundingBox
        //newSize与oldSize的比例一致,因为都是正方形,这里长宽的放缩比例相同
        let scale = newSize.width/oldSize.width;
        frame = frame.applying(CGAffineTransform(scaleX: scale, y: scale));
        return frame;
    }
    
    func cropPath(_ newSize: CGSize) -> UIBezierPath {
        return pathWithOldSize(oldSize, newSize: newSize)
    }
    
    func pathWithOldSize(_ oldSize: CGSize, newSize: CGSize) -> UIBezierPath {
        
        let path = self.path
        
        let frame = path.cgPath.boundingBox;
        //newSize与oldSize的比例一致,因为都是正方形,这里长宽的放缩比例相同
        let scale = newSize.width/oldSize.width;
        //bezierPath用于剪切ScrollView而不是整个拼图区域。需要将它回归到原点
        let move = CGAffineTransform(translationX: -frame.origin.x, y: -frame.origin.y);
        let scaleTransform = CGAffineTransform(scaleX: scale, y: scale);
        let transform = move.concatenating(scaleTransform);
        path.apply(transform)
        return path
    }
    
    fileprivate var path: UIBezierPath {
        let path = UIBezierPath()
        
        for index in 0..<self.count {
            let point = self[index].point
            if index == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
        }
        path.close()
        return path
    }
}



