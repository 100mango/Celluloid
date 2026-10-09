import SwiftUI
import Photos

struct LegacyPrivacyScreen: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UINavigationController {
        UINavigationController(rootViewController: PrivacyPolicyViewController())
    }
    func updateUIViewController(_ uiViewController: UINavigationController, context: Context) {}
}

/// iOS 15 supports completion on limited-library management. We re-resolve the
/// exact selection after it closes, never refresh or enumerate the whole library.
struct LimitedPhotoAccessSheet: UIViewControllerRepresentable {
    let didFinish: () -> Void

    func makeUIViewController(context: Context) -> LimitedPhotoAccessController {
        LimitedPhotoAccessController(didFinish: didFinish)
    }
    func updateUIViewController(_ uiViewController: LimitedPhotoAccessController, context: Context) {}
}

final class LimitedPhotoAccessController: UIViewController {
    private let didFinish: () -> Void
    private var presented = false

    init(didFinish: @escaping () -> Void) {
        self.didFinish = didFinish
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !presented else { return }
        presented = true
        guard PHPhotoLibrary.authorizationStatus(for: .readWrite) == .limited else { didFinish(); return }
        PHPhotoLibrary.shared().presentLimitedLibraryPicker(from: self) { [weak self] _ in
            DispatchQueue.main.async { self?.didFinish() }
        }
    }
}
