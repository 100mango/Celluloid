//
//  Localizable.swift
//  Celluloid
//
//  Created by Mango on 16/3/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public enum L10n {
    /// done
    case done
    /// cancel
    case cancel
    /// Edit
    case edit
    /// collage
    case collage
    /// filter
    case filter
    /// bubble
    case bubble
    /// sticker
    case sticker
    /// Share
    case share
    /// Saved
    case saved
    /// Beautify
    case beautify
}

extension L10n: CustomStringConvertible {
    public var description: String { return self.string }
    
    public var string: String {
        switch self {
        case .done:
            return L10n.tr("done")
        case .cancel:
            return L10n.tr("cancel")
        case .edit:
            return L10n.tr("edit")
        case .collage:
            return L10n.tr("collage")
        case .filter:
            return L10n.tr("filter")
        case .bubble:
            return L10n.tr("bubble")
        case .sticker:
            return L10n.tr("sticker")
        case .share:
            return L10n.tr("share")
        case .saved:
            return L10n.tr("saved")
        case .beautify:
            return L10n.tr("beautify")
        }
    }
    
    fileprivate static func tr(_ key: String, _ args: CVarArg...) -> String {
        let format = NSLocalizedString(key, bundle: extensionBundle, comment: "")
        return String(format: format, arguments: args)
    }
}

public func tr(_ key: L10n) -> String {
    return key.string
}
