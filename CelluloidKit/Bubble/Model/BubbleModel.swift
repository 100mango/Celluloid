//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation


public class BubbleModel: NSObject, NSCoding, NSCopying {
    
    //MARK: Property
    //Stored property
    let asset: UIImage.Asset
    public var content: String
    public var transform = CGAffineTransformIdentity
    public var bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
    public var center = CGPoint(x: 100, y: 100)
    public var superViewSize = CGSize.zero
    
    //Computed property
    public var bubbleImage:UIImage {
        return UIImage(asset: self.asset)
    }
    public var area:[CGFloat] {
        return areaDic[asset.rawValue]!
    }

    
    //MARK: init
    public static let bubbles: [BubbleModel] = {
        var bubbles = [BubbleModel]()
        for asset in bubbleAssets {
            let bubble = BubbleModel(asset: asset)
            bubbles.append(bubble)
        }
        return bubbles
    }()
    
    private init(asset: UIImage.Asset){
        self.asset = asset
        self.content = ""
    }
    
    //MARK: NSCoding
    
    public required convenience init?(coder aDecoder: NSCoder) {
        guard let content = aDecoder.decodeObjectForKey(PropertyKey.content.rawValue) as? String else {
            return nil
        }
        guard let asset = UIImage.Asset(rawValue: aDecoder.decodeObjectForKey(PropertyKey.asset.rawValue) as? String ?? "" )else {
            return nil
        }
        guard let transform = (aDecoder.decodeObjectForKey(PropertyKey.transform.rawValue) as? NSValue)?.CGAffineTransformValue() else {
            return nil
        }
        guard let bounds = (aDecoder.decodeObjectForKey(PropertyKey.bounds.rawValue) as? NSValue)?.CGRectValue() else {
            return nil
        }
        guard let center = (aDecoder.decodeObjectForKey(PropertyKey.center.rawValue) as? NSValue)?.CGPointValue() else {
            return nil
        }
        guard let superViewSize = (aDecoder.decodeObjectForKey(PropertyKey.superViewSize.rawValue) as? NSValue)?.CGSizeValue() else {
            return nil
        }
        
        self.init(asset: asset)
        self.content = content
        self.transform = transform
        self.bounds = bounds
        self.center = center
        self.superViewSize = superViewSize
    }
    
    public func encodeWithCoder(aCoder: NSCoder) {
        aCoder.encodeObject(content, forKey: PropertyKey.content.rawValue)
        aCoder.encodeObject(asset.rawValue, forKey: PropertyKey.asset.rawValue)
        aCoder.encodeObject(NSValue(CGAffineTransform: transform), forKey: PropertyKey.transform.rawValue)
        aCoder.encodeObject(NSValue(CGRect: bounds), forKey: PropertyKey.bounds.rawValue)
        aCoder.encodeObject(NSValue(CGPoint: center), forKey: PropertyKey.center.rawValue)
        aCoder.encodeObject(NSValue(CGSize: superViewSize), forKey: PropertyKey.superViewSize.rawValue)
    }
    
    //MARK: NSCoping
    public func copyWithZone(zone: NSZone) -> AnyObject {
        let copy = BubbleModel(asset: asset)
        copy.content = content
        copy.transform = transform
        copy.bounds = bounds
        copy.center = center
        return copy
    }
}


//MARK: Constant
private enum PropertyKey: String {
    case content
    case asset
    case transform
    case bounds
    case center
    case superViewSize
}

private let bubbleAssets:[UIImage.Asset] = [.Aside1,.Call1,.Call2,.Call3,.Say1,.Say2,.Say3,.Think1,.Think2,.Think3]

private let areaDic:[String:[CGFloat]] = {
    let path = extensionBundle.pathForResource("bubble", ofType: "json")
    if let jsonData = NSData(contentsOfFile: path!){
        let json = try! NSJSONSerialization.JSONObjectWithData(jsonData, options: NSJSONReadingOptions.MutableContainers)
        return json as! [String:[CGFloat]]
    }else{
        return [String:[CGFloat]]()
    }
}()