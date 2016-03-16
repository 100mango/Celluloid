//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation


public struct BubbleModel: StructCoding{
    
    public typealias structType = BubbleModel
    
    public var bubbleImage:UIImage {
        return UIImage(asset: self.asset)
    }
    public var content:String
    public let area:[CGFloat]
    let asset: UIImage.Asset
    
    public static let bubbles: [BubbleModel] = {
        var bubbles = [BubbleModel]()
        for asset in bubbleAssets {
            let bubble = BubbleModel(asset: asset)
            bubbles.append(bubble)
        }
        return bubbles
    }()
    
    private init(asset:UIImage.Asset){
        self.asset = asset
        self.content = ""
        self.area = areaDic[asset.rawValue]!
    }
    
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