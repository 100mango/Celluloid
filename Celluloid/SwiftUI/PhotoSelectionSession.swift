import SwiftUI
import PhotosUI

/// Presentation-owned state, compatible with iOS 15. The service owns all
/// PhotoKit work; this object publishes only small state transitions on main.
@MainActor final class PhotoSelectionSession: ObservableObject {
    enum Phase {
        case picking
        case resolving
        case recovery(PhotoSelectionError)
        case editing([PHAsset])
    }

    @Published private(set) var phase: Phase = .picking
    @Published private(set) var authorization: PHAuthorizationStatus
    private let library: SelectedPhotoLibraryAccess
    private let maximumSelection: Int
    private var selection: [String?] = []
    private var operation: Task<Void, Never>?
    private var generation = UUID()

    convenience init(maximumSelection: Int) {
        self.init(maximumSelection: maximumSelection, library: SelectedPhotoLibrary())
    }

    init(maximumSelection: Int, library: SelectedPhotoLibraryAccess) {
        precondition((1...4).contains(maximumSelection))
        self.maximumSelection = maximumSelection
        self.library = library
        authorization = library.authorizationStatus
    }

    deinit { operation?.cancel() }

    func selected(_ results: [PHPickerResult]) {
        select(identifiers: results.map(\.assetIdentifier))
    }

    func select(identifiers: [String?]) {
        cancelPending()
        selection = identifiers
        resolveOriginals()
    }

    func requestAccess() {
        cancelPending()
        phase = .resolving
        let token = generation
        operation = Task { [weak self] in
            guard let self else { return }
            let status = await self.library.requestOriginalEditingAccess()
            guard !Task.isCancelled, self.generation == token else { return }
            self.authorization = status
            self.resolveOriginals()
        }
    }

    func resolveOriginals() {
        cancelPending()
        authorization = library.authorizationStatus
        let identity: PhotoSelectionIdentity
        do { identity = try PhotoSelectionIdentity(identifiers: selection, maximumSelection: maximumSelection) }
        catch {
            phase = .recovery((error as? PhotoSelectionError) ?? .invalidSelection)
            return
        }
        phase = .resolving
        let token = generation
        operation = Task { [weak self] in
            guard let self else { return }
            do {
                let assets = try await self.library.resolve(identity)
                guard !Task.isCancelled, self.generation == token else { return }
                // Never accept a partial result or a different identity/order.
                let verified = try identity.ordered(assets, identifier: { $0.localIdentifier })
                self.phase = .editing(verified)
            } catch {
                guard !Task.isCancelled, self.generation == token else { return }
                self.authorization = self.library.authorizationStatus
                self.phase = .recovery((error as? PhotoSelectionError) ?? .originalUnavailable)
            }
        }
    }

    func chooseAgain() {
        cancelPending()
        selection = []
        phase = .picking
    }

    func refreshAccessIfRecovering() {
        guard case .recovery = phase else { return }
        // Returning from Settings rechecks only the current confirmed selection.
        resolveOriginals()
    }

    func cancelPending() {
        generation = UUID()
        operation?.cancel()
        operation = nil
    }
}
