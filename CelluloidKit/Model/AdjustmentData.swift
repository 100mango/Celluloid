//
//  AdjustmentData.swift
//  Celluloid
//
//  Created by Mango on 16/3/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import UIKit

public struct AdjustmentData {
    public var bubbles = [BubbleModel]()
    public var stickers = [StickerModel]()
    public var filterType = FilterType.Original
    /// Optional additive 1.0 metadata. Legacy archives contain absolute preview
    /// points with no recoverable canvas size, so nil must preserve that behavior.
    public var referenceCanvasSize: CGSize?

    public init() {}
}

public extension AdjustmentData {
    static let formatIdentifier = "Mango.CelluloidPhotoExtension"
    static let formatVersion = "1.0"

    static func supportIdentifier(_ identifier: String, version: String) -> Bool {
        return identifier == formatIdentifier && version == formatVersion
    }

    /// Aspect-fit canvas dimensions are rounded UIKit points (minimum one).
    /// Exclude numerically degenerate metadata before any ratio/product occurs.
    static func isValidReferenceCanvas(_ size: CGSize) -> Bool {
        [size.width, size.height].allSatisfy {
            $0.isFinite && $0 >= 1 && $0 <= CGFloat.greatestFiniteMagnitude.squareRoot()
        }
    }

    /// Reads the original dictionary/NSValue archive without instantiating arbitrary classes.
    /// Secure decoding also accepts legacy archives written without requiring secure coding.
    static func decode(_ data: Data) throws -> AdjustmentData {
        let classes: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
        guard let object = try NSKeyedUnarchiver.unarchivedObject(ofClasses: classes, from: data) as? [String: Any] else {
            throw AdjustmentDataError.invalidArchive
        }
        return try AdjustmentData(object: object)
    }

    func encode() throws -> Data {
        let object = archiveObject
        // Public geometry is mutable. Never save nonfinite or otherwise invalid state.
        _ = try AdjustmentData(object: object)
        return try NSKeyedArchiver.archivedData(withRootObject: object, requiringSecureCoding: true)
    }

    /// Retained for callers of the original API; the contents are an archive dictionary,
    /// not JSON text, because geometry has always been stored as NSValue.
    func toJSON() -> AnyObject {
        return archiveObject as NSDictionary
    }

    init(object: [String: Any]) throws {
        let decoder = AdjustmentDictionary(object: object)
        let rawFilter = try decoder.string("filterType")
        guard let filter = FilterType(rawValue: rawFilter) else {
            throw AdjustmentDataError.invalidValue("filterType")
        }
        bubbles = try decoder.objects("bubbles").map { try BubbleModel(object: $0) }
        stickers = try decoder.objects("stickers").map { try StickerModel(object: $0) }
        filterType = filter
        if let rawSize = object["referenceCanvasSize"] {
            guard let value = rawSize as? NSValue,
                  String(cString: value.objCType) == String(cString: NSValue(cgSize: .zero).objCType) else {
                throw AdjustmentDataError.invalidValue("referenceCanvasSize")
            }
            let size = value.cgSizeValue
            guard Self.isValidReferenceCanvas(size) else {
                throw AdjustmentDataError.invalidValue("referenceCanvasSize")
            }
            referenceCanvasSize = size
        }
    }
}

private extension AdjustmentData {
    var archiveObject: [String: Any] {
        var object: [String: Any] = ["filterType": filterType.rawValue]
        if let size = referenceCanvasSize { object["referenceCanvasSize"] = NSValue(cgSize: size) }
        // Preserve the historical omission of empty arrays as well as every field name.
        if !bubbles.isEmpty { object["bubbles"] = bubbles.map { $0.toJSON() } }
        if !stickers.isEmpty { object["stickers"] = stickers.map { $0.toJSON() } }
        return object
    }
}
