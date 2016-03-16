//
//  StructCoding.swift
//  Celluloid
//
//  Created by Mango on 16/3/16.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public protocol StructCoding {
    typealias structType
    
    mutating func encode() -> NSData
    
    static func decode(data: NSData) -> Self
}

public extension StructCoding {
    
    public mutating func encode() -> NSData {
        return withUnsafePointer(&self) { p in
            NSData(bytes: p, length: sizeofValue(self))
        }
    }
    
    public static func decode(data: NSData) -> structType {
        let pointer = UnsafeMutablePointer<structType>.alloc(sizeof(structType))
        data.getBytes(pointer, length: sizeof(structType))
        return pointer.move()
    }
}