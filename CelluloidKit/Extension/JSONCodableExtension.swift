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
    func encode(_ value: CGAffineTransform, key: String) {
        object[key] = NSValue(cgAffineTransform: value)
    }
    
    func encode(_ value: CGRect, key: String) {
        object[key] = NSValue(cgRect: value)
    }
    
    func encode(_ value: CGPoint, key: String) {
        object[key] = NSValue(cgPoint: value)
    }
}

extension JSONDecoder {
    
    func decode(_ key: String, type: Any.Type) throws -> NSValue {
        guard let value = get(key) else {
            throw JSONDecodableError.missingTypeError(key: key)
        }
        guard let compatible = value as? NSValue else {
            throw JSONDecodableError.incompatibleTypeError(key: key, elementType: type(of: value), expectedType: NSValue.self)
        }
        guard let objcType = String(validatingUTF8: compatible.objCType), objcType.contains("\(type)") else {
            throw JSONDecodableError.incompatibleTypeError(key: key, elementType: type(of: value), expectedType: type)
        }
        return compatible
    }
    
    func decode(_ key: String) throws -> CGAffineTransform {
        return try decode(key, type: CGAffineTransform.self).cgAffineTransformValue
    }
    
    func decode(_ key: String) throws -> CGRect {
        return try decode(key, type: CGRect.self).cgRectValue
    }
    
    func decode(_ key: String) throws -> CGPoint {
        return try decode(key, type: CGPoint.self).cgPointValue
    }
}
