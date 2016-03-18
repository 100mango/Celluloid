//
//  AdjustmentData.swift
//  Celluloid
//
//  Created by Mango on 16/3/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import CelluloidKit

public struct AdjustmentData: StructCoding {
    
    //conform StructCoding
    public typealias structType = AdjustmentData
    
    static let formatIdentifier = "Mango.CelluloidPhotoExtension"
    static let formatVersion    = "1.0"
    
    static func supportIdentifier(identifier: String, version: String) -> Bool {
        return identifier == self.formatIdentifier && version == self.formatVersion
    }
    
    //state restoration property
    var bubbles = [BubbleModel]()
    
}