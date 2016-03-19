//
//  AdjustmentData.swift
//  Celluloid
//
//  Created by Mango on 16/3/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import CelluloidKit

public class AdjustmentData: NSObject, NSCoding {
    
    //conform StructCoding
    public typealias structType = AdjustmentData
    
    static let formatIdentifier = "Mango.CelluloidPhotoExtension"
    static let formatVersion    = "1.0"
    
    static func supportIdentifier(identifier: String, version: String) -> Bool {
        return identifier == self.formatIdentifier && version == self.formatVersion
    }
    
    //state restoration property
    var bubbles: [BubbleModel] = {
        return BubbleModel.bubbles
    }()
    
    //MARK: NSCoding
    static public func decode(data: NSData) -> AdjustmentData? {
        return NSKeyedUnarchiver.unarchiveObjectWithData(data) as? AdjustmentData
    }
    
    public func encode() -> NSData {
        return NSKeyedArchiver.archivedDataWithRootObject(self)
    }
    
    public convenience required init?(coder aDecoder: NSCoder) {
        if let bubbles = aDecoder.decodeObjectForKey(PropertyKey.bubbles.rawValue){
            self.init()
            self.bubbles = bubbles as! [BubbleModel]
        }else{
            return nil
        }
    }
    
    public func encodeWithCoder(aCoder: NSCoder) {
        aCoder.encodeObject(bubbles, forKey: PropertyKey.bubbles.rawValue)
    }
}

private enum PropertyKey: String {
    case bubbles
}
