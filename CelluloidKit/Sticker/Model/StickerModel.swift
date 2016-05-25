//
//  StickerModel.swift
//  Celluloid
//
//  Created by Mango on 16/4/20.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import JSONCodable

public struct StickerModel {
    
    //MARK: Property
    //Stored property
    let imageName: String
    public var transform = CGAffineTransformIdentity
    public var bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
    public var center = CGPoint(x: 100, y: 100)
    //Computed property
    public var stickerImage: UIImage {
        return UIImage(named: imageName, inBundle: extensionBundle, compatibleWithTraitCollection: nil)!
    }

    //MARK: init
    public static let stickers: [StickerModel] = {
        var stickers = [StickerModel]()
        for i in 32...54 {
            let sticker = StickerModel(imageName: String(i))
            stickers.append(sticker)
        }
        return stickers
    }()
    
    private init(imageName: String) {
        self.imageName = imageName
    }
}

//MARK: JSONCodable
extension StickerModel: JSONEncodable {
    public func toJSON() -> AnyObject {
        do {
            return try JSONEncoder.create({ encoder in
                try encoder.encode(imageName, key: .imageName)
                encoder.encode(transform, key: .transform)
                encoder.encode(bounds, key: .bounds)
                encoder.encode(center, key: .center)
            })
        }catch{
            fatalError("\(error)")
        }
    }
}

extension StickerModel: JSONDecodable {
    public init(object: JSONObject) {
        do {
            let decoder = JSONDecoder(object: object)
            imageName = try decoder.decode(.imageName)
            transform = try decoder.decode(.transform)
            bounds = try decoder.decode(.bounds)
            center = try decoder.decode(.center)
        }catch{
            fatalError("\(error)")
        }
    }
}

//MARK: Constant
private extension String {
    static let imageName = "imageName"
    static let transform = "transform"
    static let bounds = "bounds"
    static let center = "center"
}
