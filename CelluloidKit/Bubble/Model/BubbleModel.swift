//
//  BubbleModel.swift
//  Celluloid
//
//  Created by Mango on 16/3/3.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import UIKit

public struct BubbleModel {
    let asset: UIImage.Asset
    public var content = ""
    public var transform = CGAffineTransform.identity
    public var bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
    public var center = CGPoint(x: 100, y: 100)

    public var bubbleImage: UIImage {
        return UIImage(asset: asset) ?? UIImage()
    }

    public var area: [CGFloat] {
        return areaDic[asset.rawValue] ?? [0, 100, 0, 100]
    }

    public static let bubbles = bubbleAssets.map { BubbleModel(asset: $0) }

    fileprivate init(asset: UIImage.Asset) {
        self.asset = asset
    }

    public func toJSON() -> AnyObject {
        return [
            "asset": asset.rawValue,
            "content": content,
            "transform": NSValue(cgAffineTransform: transform),
            "bounds": NSValue(cgRect: bounds),
            "center": NSValue(cgPoint: center)
        ] as NSDictionary
    }

    public init(object: [String: Any]) throws {
        let decoder = AdjustmentDictionary(object: object)
        let rawAsset = try decoder.string("asset")
        guard let asset = UIImage.Asset(rawValue: rawAsset), bubbleAssets.contains(asset) else {
            throw AdjustmentDataError.invalidValue("asset")
        }
        self.asset = asset
        content = try decoder.string("content")
        transform = try decoder.transform("transform")
        bounds = try decoder.rect("bounds")
        center = try decoder.point("center")
        guard hasRenderableGeometry(center: center, bounds: bounds, transform: transform) else {
            throw AdjustmentDataError.invalidValue("transformed geometry")
        }
    }
}

private let bubbleAssets: [UIImage.Asset] = [.Aside1, .Call1, .Call2, .Call3, .Say1, .Say2, .Say3, .Think1, .Think2, .Think3]

private let areaDic: [String: [CGFloat]] = {
    guard let url = extensionBundle.url(forResource: "bubble", withExtension: "json"),
          let data = try? Data(contentsOf: url),
          let json = try? JSONSerialization.jsonObject(with: data),
          let values = json as? [String: [NSNumber]] else {
        return [:]
    }
    return values.reduce(into: [String: [CGFloat]]()) { result, entry in
        let area = entry.value.map { CGFloat(truncating: $0) }
        if area.count == 4 && area.allSatisfy({ $0.isFinite }) {
            result[entry.key] = area
        }
    }
}()
