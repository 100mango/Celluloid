//
//  JSONCodableExtension.swift
//  Celluloid
//
//  Created by Mango on 16/4/5.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import JSONCodable

extension JSONEncoder {
    func encode(value: CGAffineTransform, key: String) {
        object[key] = NSValue(CGAffineTransform: value)
    }
    
    func encode(value: CGRect, key: String) {
        object[key] = NSValue(CGRect: value)
    }
    
    func encode(value: CGPoint, key: String) {
        object[key] = NSValue(CGPoint: value)
    }
}

extension JSONDecoder {
    
    func decode(key: String, type: Any.Type) throws -> NSValue {
        guard let value = get(key) else {
            throw JSONDecodableError.MissingTypeError(key: key)
        }
        guard let compatible = value as? NSValue else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: NSValue.self)
        }
        guard let objcType = String.fromCString(compatible.objCType) where objcType.containsString("\(type)") else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: type)
        }
        return compatible
    }
    
    func decode(key: String) throws -> CGAffineTransform {
        return try decode(key, type: CGAffineTransform.self).CGAffineTransformValue()
    }
    
    func decode(key: String) throws -> CGRect {
        return try decode(key, type: CGRect.self).CGRectValue()
    }
    
    func decode(key: String) throws -> CGPoint {
        return try decode(key, type: CGPoint.self).CGPointValue()
    }
}