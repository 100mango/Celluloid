import Foundation
import Photos

enum CelluloidTestFixtures {
    static func syntheticAsset(width: Int = 640, height: Int = 480) -> PHAsset? {
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        var result: PHAsset?
        PHAsset.fetchAssets(with: .image, options: options).enumerateObjects { asset, _, stop in
            if asset.pixelWidth == width, asset.pixelHeight == height,
               let created = asset.creationDate, abs(created.timeIntervalSinceNow) < 86400 {
                result = asset
                stop.pointee = true
            }
        }
        return result
    }
}
