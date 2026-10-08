import UIKit
import CelluloidKit
import Photos

final class PhotoModel {
    let asset: PHAsset
    private(set) var loadedImage: UIImage?
    private var pending: [(Result<UIImage, Error>) -> Void] = []
    private var loading = false
    var points: [CGPoint] = []
    var zoomScale: CGFloat = 1
    var contentOffset: CGPoint = .zero
    var oldScrollViewSize: CGSize = .zero

    init(asset: PHAsset) { self.asset = asset }

    func requstImage(_ completion: @escaping (UIImage) -> Void) {
        loadImage { result in if case .success(let image) = result { completion(image) } }
    }

    /// Coalesces repeated layout requests and always completes success or failure on main.
    func loadImage(_ completion: @escaping (Result<UIImage, Error>) -> Void) {
        if let image = loadedImage { completion(.success(image)); return }
        pending.append(completion)
        guard !loading else { return }
        loading = true
        let options = PHImageRequestOptions()
        options.isNetworkAccessAllowed = true
        options.deliveryMode = .highQualityFormat
        options.resizeMode = .exact
        PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 1600, height: 1600), contentMode: .aspectFit, options: options) { [weak self] image, info in
            if (info?[PHImageResultIsDegradedKey] as? Bool) == true { return }
            DispatchQueue.main.async {
                guard let self = self, self.loading else { return }
                self.loading = false
                let result: Result<UIImage, Error>
                if let image = image { self.loadedImage = image; result = .success(image) }
                else { result = .failure((info?[PHImageErrorKey] as? Error) ?? PhotoLoadError.unavailable) }
                let callbacks = self.pending
                self.pending.removeAll()
                callbacks.forEach { $0(result) }
            }
        }
    }
}
private enum PhotoLoadError: LocalizedError {
    case unavailable
    var errorDescription: String? { NSLocalizedString("A photo could not be loaded. Check your connection and Photos access, then retry.", comment: "Photo unavailable") }
}
