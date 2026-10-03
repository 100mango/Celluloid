//
//  Style.swift
//  Celluloid
//
//  Created by Mango on 16/3/2.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public extension UIColor {
    @nonobjc public static let cellLightPurple = UIColor(hex6: 0xeff1ff)
    @nonobjc public static let alphaWhiteColor = UIColor.white.withAlphaComponent(0.7)
    @nonobjc public static let alphaBlackColor = UIColor.black.withAlphaComponent(0.7)
    @nonobjc public static let blackBackgroundColor = UIColor(hex6: 0x1f1f1f)
    @nonobjc public static let bubbleBackgroundColor = UIColor(hex6: 0xe3e6ee)
}

private extension UIColor {
    convenience init(hex6: UInt32) {
        self.init(red: CGFloat((hex6 >> 16) & 255) / 255,
                  green: CGFloat((hex6 >> 8) & 255) / 255,
                  blue: CGFloat(hex6 & 255) / 255, alpha: 1)
    }
}
