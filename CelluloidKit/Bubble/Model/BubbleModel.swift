//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation


public class BubbleModel: NSObject, NSCoding {
    
    public var bubbleImage:UIImage {
        return UIImage(asset: self.asset)
    }
    public var area:[CGFloat] {
        return areaDic[asset.rawValue]!
    }
    let asset: UIImage.Asset
    public var content:String

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
    
    public required convenience init?(coder aDecoder: NSCoder) {
        guard let content = aDecoder.decodeObjectForKey(PropertyKey.content.rawValue) as? String,
        let asset = UIImage.Asset(rawValue: aDecoder.decodeObjectForKey(PropertyKey.asset.rawValue) as? String ?? "")
            else {
                return nil
        }
        self.init(asset: asset)
        self.content = content
    }
    
    
    public func encodeWithCoder(aCoder: NSCoder) {
        aCoder.encodeObject(content, forKey: PropertyKey.content.rawValue)
        aCoder.encodeObject(asset.rawValue, forKey: PropertyKey.asset.rawValue)
    }
    
}

private enum PropertyKey: String {
    case content
    case asset
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