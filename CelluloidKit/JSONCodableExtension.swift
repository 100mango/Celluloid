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
    func decode(key: String) throws -> CGAffineTransform {
        guard let value = get(key) else {
            throw JSONDecodableError.MissingTypeError(key: key)
        }
        guard let compatible = value as? NSValue else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: NSValue.self)
        }
        guard let type = String.fromCString(compatible.objCType) where type.containsString("CGAffineTransform") else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: CGAffineTransform.self)
        }
        return compatible.CGAffineTransformValue()
    }
    
    func decode(key: String) throws -> CGRect {
        guard let value = get(key) else {
            throw JSONDecodableError.MissingTypeError(key: key)
        }
        guard let compatible = value as? NSValue else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: NSValue.self)
        }
        guard let type = String.fromCString(compatible.objCType) where type.containsString("CGRect") else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: CGRect.self)
        }
        return compatible.CGRectValue()
    }
    
    
    func decode(key: String) throws -> CGPoint {
        guard let value = get(key) else {
            throw JSONDecodableError.MissingTypeError(key: key)
        }
        guard let compatible = value as? NSValue else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: NSValue.self)
        }
        guard let type = String.fromCString(compatible.objCType) where type.containsString("CGPoint") else {
            throw JSONDecodableError.IncompatibleTypeError(key: key, elementType: value.dynamicType, expectedType: CGPoint.self)
        }
        return compatible.CGPointValue()
    }
}