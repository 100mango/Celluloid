import Foundation
import Photos

enum CelluloidTestFixtures {
    static func syntheticAsset() -> PHAsset? {
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        var result: PHAsset?
        PHAsset.fetchAssets(with: .image, options: options).enumerateObjects { asset, _, stop in
            if asset.pixelWidth == 640, asset.pixelHeight == 480,
               let created = asset.creationDate, abs(created.timeIntervalSinceNow) < 86400 {
                result = asset
                stop.pointee = true
            }
        }
        return result
    }
}
