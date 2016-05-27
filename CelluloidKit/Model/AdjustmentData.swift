//
//  AdjustmentData.swift
//  Celluloid
//
//  Created by Mango on 16/3/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import JSONCodable

public struct AdjustmentData {
    
    //state restoration property
    public var bubbles = [BubbleModel]()
    public var stickers = [StickerModel]()
    public var filterType = FilterType.Original
    
    public init() {}
}

public extension AdjustmentData {
    
    static let formatIdentifier = "Mango.CelluloidPhotoExtension"
    static let formatVersion    = "1.0"
    
    static func supportIdentifier(identifier: String, version: String) -> Bool {
        return identifier == self.formatIdentifier && version == self.formatVersion
    }
    
    static func decode(data: NSData) -> AdjustmentData {
        let dic = NSKeyedUnarchiver.unarchiveObjectWithData(data) as! [String:AnyObject]
        return AdjustmentData(object: dic)
    }
    
    func encode() -> NSData {
        return NSKeyedArchiver.archivedDataWithRootObject(self.toJSON())
    }
}

//MARK: JSONCodable
extension AdjustmentData: JSONEncodable {
    public func toJSON() -> AnyObject {
        do {
            return try JSONEncoder.create({ encoder in
                try encoder.encode(bubbles, key: .bubbles)
                try encoder.encode(stickers, key: .stickers)
                try encoder.encode(filterType, key: .filterType)
            })
        }catch{
            fatalError("\(error)")
        }
    }
}

extension AdjustmentData: JSONDecodable {
    public init(object: JSONObject) {
        do {
            let decoder = JSONDecoder(object: object)
            bubbles = try decoder.decode(.bubbles)
            stickers = try decoder.decode(.stickers)
            filterType = try decoder.decode(.filterType)
        }catch{
            fatalError("\(error)")
        }
    }
}

//MARK: propertyKey
private extension String {
    static let bubbles = "bubbles"
    static let stickers = "stickers"
    static let filterType = "filterType"
}

