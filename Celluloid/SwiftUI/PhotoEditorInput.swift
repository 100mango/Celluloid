import Foundation
import PhotosUI

/// Future SwiftUI editor input boundary. Cases are deliberately not convertible:
/// a provider cannot silently stand in for an original Photos editing session.
enum PhotoEditorInput {
    case originals(PhotoSelectionIdentity)
    case importedCopies([OwnedPhotoCopy])
}

/// Construct only after an explicit import-copy confirmation and successful
/// worker-owned copy of the provider's temporary file. The owner must keep this
/// file alive for the entire editing/export session and remove it on cancellation.
/// This entry migration does not expose import-copy until that pipeline is wired.
struct OwnedPhotoCopy: Identifiable {
    let id: UUID
    let fileURL: URL
    let originalAssetIdentifier: String?
}

/// A lightweight provider handle is not an imported photo and grants no right to
/// overwrite the original. Selection order is its array position, not UUID order.
struct SelectedPhotoProvider: Identifiable {
    let id: UUID
    let assetIdentifier: String?
    let provider: NSItemProvider

    init(result: PHPickerResult) {
        id = UUID()
        assetIdentifier = result.assetIdentifier
        provider = result.itemProvider
    }
}

/// The copy pipeline must be user-confirmed before it asks any provider for
/// bytes. These states are an integration contract, not enabled entry buttons.
enum PhotoCopyImportState {
    case unavailable
    case awaitingConfirmation([SelectedPhotoProvider])
    case importing(sessionID: UUID)
    case ready([OwnedPhotoCopy])
    case failed(PhotoCopyImportFailure)
}

enum PhotoCopyImportFailure: Error {
    case cancelled
    case unavailableInCloud
    case unreadableImage
    case resourceLimit
    case ownedFileUnavailable
}
