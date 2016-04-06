//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import JSONCodable


public struct BubbleModel {
    
    //MARK: Property
    //Stored property
    let asset: UIImage.Asset
    public var content = ""
    public var transform = CGAffineTransformIdentity
    public var bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
    public var center = CGPoint(x: 100, y: 100)
    //public var superViewSize = CGSize.zero
    
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
    }
}

//MARK: JSONCodable

extension BubbleModel: JSONEncodable {
    public func toJSON() -> AnyObject {
        do {
            return try JSONEncoder.create({ encoder in
                try encoder.encode(asset, key: PropertyKey.asset.rawValue)
                try encoder.encode(content, key: PropertyKey.content.rawValue)
                encoder.encode(transform, key: PropertyKey.transform.rawValue)
                encoder.encode(bounds, key: PropertyKey.bounds.rawValue)
                encoder.encode(center, key: PropertyKey.center.rawValue)
            })
        }catch{
            fatalError("\(error)")
        }
    }
}

extension BubbleModel: JSONDecodable {
    public init(object: JSONObject) {
        do {
            let decoder = JSONDecoder(object: object)
            asset = try decoder.decode(PropertyKey.asset.rawValue)
            content = try decoder.decode(PropertyKey.content.rawValue)
            transform = try decoder.decode(PropertyKey.transform.rawValue)
            bounds = try decoder.decode(PropertyKey.bounds.rawValue)
            center = try decoder.decode(PropertyKey.center.rawValue)
        }catch{
            fatalError("\(error)")
        }
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