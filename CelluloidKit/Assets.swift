//
//  Assets.swift
//  Celluloid
//
//  Created by Mango on 16/2/29.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

let buddleIndentifier = "Mango.CelluloidKit"

public extension UIImage {
    public enum Asset: String {
        case Aside1 = "aside1"
        case Call1 = "call1"
        case Call2 = "call2"
        case Call3 = "call3"
        case Say1 = "say1"
        case Say2 = "say2"
        case Say3 = "say3"
        case Think1 = "think1"
        case Think2 = "think2"
        case Think3 = "think3"
        
        public var image: UIImage {
            return UIImage(asset: self)
        }
    }
    
    public convenience init!(asset: Asset) {
        let bundle = NSBundle(identifier: buddleIndentifier)
        self.init(named: asset.rawValue, inBundle: bundle, compatibleWithTraitCollection: nil)
    }
}
