import SwiftUI
import PhotosUI

/// iOS 15-compatible system UI. Rendering, thumbnails, library browsing and
/// iCloud browsing stay in Photos' process, outside the app's main-thread work.
@MainActor struct SystemPhotoPicker: UIViewControllerRepresentable {
    let maximumSelection: Int
    let didFinish: ([PHPickerResult]) -> Void

    static func configuration(maximumSelection: Int) -> PHPickerConfiguration {
        precondition((1...4).contains(maximumSelection))
        // Supplying the library retains PHAsset identity. A data-only picker
        // cannot safely drive the existing non-destructive original-edit path.
        var configuration = PHPickerConfiguration(photoLibrary: .shared())
        configuration.filter = .images
        configuration.selectionLimit = maximumSelection
        configuration.selection = .ordered
        configuration.preferredAssetRepresentationMode = .current
        return configuration
    }

    func makeUIViewController(context: Context) -> PHPickerViewController {
        let picker = PHPickerViewController(configuration: Self.configuration(maximumSelection: maximumSelection))
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(didFinish: didFinish) }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        private let didFinish: ([PHPickerResult]) -> Void
        private var finished = false

        init(didFinish: @escaping ([PHPickerResult]) -> Void) { self.didFinish = didFinish }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            // A coordinator belongs to one picker presentation. Duplicate
            // callbacks must not launch two editors or replace a newer session.
            guard !finished else { return }
            finished = true
            didFinish(results)
        }
    }
}
