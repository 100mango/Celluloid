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
    
    let areas: [[CGFloat]]
    
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
        
        let path =  NSBundle.mainBundle().pathForResource("collage", ofType: "json")
        if let jsonData = NSData(contentsOfFile: path!){
            let json = try! NSJSONSerialization.JSONObjectWithData(jsonData, options: NSJSONReadingOptions.MutableContainers) as! [String:AnyObject]
            let array = json[key] as! [[String:AnyObject]]
            
            return array.map{ dic -> CollageModel in
                let imageName = dic["drawable_name"] as! String
                let areas = dic["polygons"] as! [[CGFloat]]
                let collageModel = CollageModel(imageName: imageName, areas: areas)
                return collageModel
            }
        }else{
            return [CollageModel]()
        }
        
    }
    
}