//
//  StickerModel.swift
//  Celluloid
//
//  Created by Mango on 16/4/20.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import UIKit

public struct StickerModel {
    let imageName: String
    public var transform = CGAffineTransform.identity
    public var bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
    public var center = CGPoint(x: 100, y: 100)

    public var stickerImage: UIImage {
        return UIImage(named: imageName, in: extensionBundle, compatibleWith: nil) ?? UIImage()
    }

    public static let stickers = (32...54).map { StickerModel(imageName: String($0)) }

    fileprivate init(imageName: String) {
        self.imageName = imageName
    }

    public func toJSON() -> AnyObject {
        return [
            "imageName": imageName,
            "transform": NSValue(cgAffineTransform: transform),
            "bounds": NSValue(cgRect: bounds),
            "center": NSValue(cgPoint: center)
        ] as NSDictionary
    }

    public init(object: [String: Any]) throws {
        let decoder = AdjustmentDictionary(object: object)
        let imageName = try decoder.string("imageName")
        guard let number = Int(imageName), (32...54).contains(number), String(number) == imageName else {
            throw AdjustmentDataError.invalidValue("imageName")
        }
        self.imageName = imageName
        transform = try decoder.transform("transform")
        bounds = try decoder.rect("bounds")
        center = try decoder.point("center")
    }
}
