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
    case Done
    /// cancel
    case Cancel
    /// Edit
    case Edit
    /// collage
    case Collage
    /// filter
    case Filter
    /// bubble
    case Bubble
    /// sticker
    case Sticker
    /// Share
    case Share
    /// Saved
    case Saved
    /// Beautify
    case Beautify
}

extension L10n: CustomStringConvertible {
    public var description: String { return self.string }
    
    public var string: String {
        switch self {
        case .Done:
            return L10n.tr("done")
        case .Cancel:
            return L10n.tr("cancel")
        case .Edit:
            return L10n.tr("edit")
        case .Collage:
            return L10n.tr("collage")
        case .Filter:
            return L10n.tr("filter")
        case .Bubble:
            return L10n.tr("bubble")
        case .Sticker:
            return L10n.tr("sticker")
        case .Share:
            return L10n.tr("share")
        case .Saved:
            return L10n.tr("saved")
        case .Beautify:
            return L10n.tr("beautify")
        }
    }
    
    private static func tr(key: String, _ args: CVarArgType...) -> String {
        let format = NSLocalizedString(key, bundle: extensionBundle, comment: "")
        return String(format: format, arguments: args)
    }
}

public func tr(key: L10n) -> String {
    return key.string
}
