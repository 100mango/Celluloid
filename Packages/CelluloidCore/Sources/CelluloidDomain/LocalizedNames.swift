import Foundation

public extension FilterPreset {
    var localizedTitle: String {
        let fallback: String
        switch self {
        case .pixellateFace: fallback = "Face Pixelation"
        default: fallback = rawValue
        }
        return NSLocalizedString("filter." + rawValue, bundle: .module, value: fallback, comment: "Photo filter")
    }
}

public extension BubbleAsset {
    var localizedTitle: String {
        NSLocalizedString("bubble." + rawValue, bundle: .module, value: rawValue, comment: "Bubble artwork")
    }
}
