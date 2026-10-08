//
//  JSONCodableExtension.swift
//  CelluloidKit
//
//  Foundation-backed helpers for the original Photos adjustment archive.
//  Keep NSValue geometry rather than changing the version 1.0 wire format.
//

import Foundation
import UIKit

public enum AdjustmentDataError: Error {
    case invalidArchive
    case missingValue(String)
    case invalidValue(String)
}

struct AdjustmentDictionary {
    let object: [String: Any]

    func string(_ key: String) throws -> String {
        guard let value = object[key] else {
            throw AdjustmentDataError.missingValue(key)
        }
        guard let string = value as? String else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return string
    }

    func objects(_ key: String) throws -> [[String: Any]] {
        // JSONCodable 3 omitted empty collections in existing Photos archives.
        guard let value = object[key] else { return [] }
        guard let objects = value as? [[String: Any]] else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return objects
    }

    private func value(_ key: String, matching expected: NSValue) throws -> NSValue {
        guard let rawValue = object[key] else {
            throw AdjustmentDataError.missingValue(key)
        }
        guard let value = rawValue as? NSValue,
              String(cString: value.objCType) == String(cString: expected.objCType) else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return value
    }

    func transform(_ key: String) throws -> CGAffineTransform {
        let transform = try value(key, matching: NSValue(cgAffineTransform: .identity)).cgAffineTransformValue
        guard [transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty].allSatisfy({ $0.isFinite }) else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return transform
    }

    func rect(_ key: String) throws -> CGRect {
        let rect = try value(key, matching: NSValue(cgRect: .zero)).cgRectValue
        guard [rect.origin.x, rect.origin.y, rect.size.width, rect.size.height].allSatisfy({ $0.isFinite }),
              rect.size.width >= 0, rect.size.height >= 0 else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return rect
    }

    func point(_ key: String) throws -> CGPoint {
        let point = try value(key, matching: NSValue(cgPoint: .zero)).cgPointValue
        guard point.x.isFinite, point.y.isFinite else {
            throw AdjustmentDataError.invalidValue(key)
        }
        return point
    }
}

/// Pure arithmetic validation before creating CALayer/UIView geometry. Finite
/// components alone are insufficient when their products or extents overflow.
func hasRenderableGeometry(center: CGPoint, bounds: CGRect, transform: CGAffineTransform) -> Bool {
    let raw = [center.x, center.y, bounds.minX, bounds.minY, bounds.maxX, bounds.maxY,
               bounds.width, bounds.height, transform.a, transform.b, transform.c,
               transform.d, transform.tx, transform.ty]
    guard raw.allSatisfy({ $0.isFinite }), bounds.width >= 0, bounds.height >= 0 else { return false }
    let transformed = bounds.applying(transform)
    let halfWidth = transformed.width / 2, halfHeight = transformed.height / 2
    return [transformed.minX, transformed.minY, transformed.maxX, transformed.maxY,
            transformed.width, transformed.height,
            center.x + transform.tx - halfWidth, center.x + transform.tx + halfWidth,
            center.y + transform.ty - halfHeight, center.y + transform.ty + halfHeight].allSatisfy { $0.isFinite }
}
