import CelluloidKit
import Photos
import SwiftUI

/// Receives the system picker's ordered, verified PHAsset identities.
@MainActor
struct CelluloidEditorView: View {
    let assets: [PHAsset]
    var body: some View {
        Group {
            if assets.count == 1, let asset = assets.first {
                CelluloidOriginalPhotoEditor(asset: asset)
            } else if (2...4).contains(assets.count) {
                CelluloidCollageEditorView(assets: assets)
            } else {
                Text(NSLocalizedString("Select between one and four photos.", comment: ""))
            }
        }
    }
}

@MainActor
private struct CelluloidOriginalPhotoEditor: View {
    let asset: PHAsset
    @Environment(\.dismiss) private var dismiss
    @StateObject private var session = CelluloidEditingSession()
    @State private var requestID: PHContentEditingInputRequestID?
    @State private var currentPreviewRequestID: PHImageRequestID?
    @State private var requestGeneration = UUID()
    @State private var saveGeneration = UUID()
    @State private var saving = false
    @State private var committing = false
    @State private var savedImage: UIImage?
    @State private var errorMessage: String?

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if let image = savedImage {
                    CelluloidSavedPhotoView(image: image, onDone: cancelAndDismiss)
                } else {
                    CelluloidEditorContent(session: session)
                        .disabled(saving)
                }
            }
            .navigationTitle(savedImage == nil ? tr(.beautify) : "")
            .navigationBarBackButtonHidden(savedImage != nil)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if savedImage == nil {
                        Button(tr(.cancel), action: cancelAndDismiss)
                            .disabled(committing)
                            .accessibilityIdentifier("editor-cancel")
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if savedImage == nil {
                        Button(tr(.done), action: save)
                            .accessibilityIdentifier("editor-done")
                            .disabled(!session.canEdit || saving)
                    }
                }
            }
            .overlay {
                if saving { ProgressView().padding(24).background(.regularMaterial).cornerRadius(12) }
            }
            .alert(NSLocalizedString("Unable to Edit Photo", comment: ""), isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })) {
                    Button(NSLocalizedString("Retry", comment: "")) { errorMessage = nil; load() }
                    Button(tr(.cancel), role: .cancel) { errorMessage = nil }
                } message: { Text(errorMessage ?? "") }
        }
        .navigationViewStyle(.stack)
        .onAppear { if session.phase == .empty { load() } }
        .onDisappear {
            if !committing && !session.isPresentingTool { abandon() }
        }
    }
    private func load() {
        if let requestID = requestID { asset.cancelContentEditingInputRequest(requestID) }
        let token = UUID(); requestGeneration = token
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = true
        options.canHandleAdjustmentData = { AdjustmentData.supportIdentifier($0.formatIdentifier, version: $0.formatVersion) }
        requestID = asset.requestContentEditingInput(with: options) { input, _ in
            DispatchQueue.main.async {
                guard requestGeneration == token else { return }
                requestID = nil
                guard let input = input else {
                    errorMessage = NSLocalizedString("The photo could not be loaded. Check your connection and Photos access, then try again.", comment: "")
                    return
                }
                // Request the current rendered preview for opaque recipes. It
                // must never be borrowed from a different selected PHAsset.
                session.start(input: input, placeholder: nil)
                if input.adjustmentData != nil {
                    let imageOptions = PHImageRequestOptions()
                    imageOptions.isNetworkAccessAllowed = true
                    imageOptions.deliveryMode = .highQualityFormat
                    currentPreviewRequestID = PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 1600, height: 1600), contentMode: .aspectFit, options: imageOptions) { image, info in
                        guard info?[PHImageResultIsDegradedKey] as? Bool != true, let image = image else { return }
                        DispatchQueue.main.async {
                            guard requestGeneration == token, session.input === input else { return }
                            currentPreviewRequestID = nil
                            session.replaceReadOnlyPreview(image, for: input)
                        }
                    }
                }
            }
        }
    }
    private func save() {
        guard !saving, session.canEdit, let input = session.input else { return }
        saving = true
        let token = UUID(); saveGeneration = token
        session.export { result in
            guard token == saveGeneration, session.input === input else { return }
            switch result {
            case .failure(let error):
                saving = false
                if case .adjustmentTooComplex = error { session.notice = tr(.editTooComplex) }
                else { session.notice = NSLocalizedString("The edited image could not be rendered. Your original photo is unchanged.", comment: "") }
            case .success(let exported):
                let output = PHContentEditingOutput(contentEditingInput: input)
                output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
                    formatVersion: AdjustmentData.formatVersion, data: exported.adjustmentData)
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        try exported.jpegData.write(to: output.renderedContentURL, options: .atomic)
                        DispatchQueue.main.async {
                            guard token == saveGeneration, session.input === input else {
                                try? FileManager.default.removeItem(at: output.renderedContentURL); return
                            }
                            committing = true
                            PHPhotoLibrary.shared().performChanges({
                                PHAssetChangeRequest(for: asset).contentEditingOutput = output
                            }) { success, error in
                                DispatchQueue.main.async {
                                    committing = false; saving = false
                                    if success { savedImage = exported.image }
                                    else { session.notice = error?.localizedDescription ?? NSLocalizedString("The photo could not be saved. Your original photo is unchanged.", comment: "") }
                                }
                            }
                        }
                    } catch {
                        DispatchQueue.main.async {
                            guard token == saveGeneration else { return }
                            saving = false; session.notice = error.localizedDescription
                        }
                    }
                }
            }
        }
    }
    private func abandon() {
        requestGeneration = UUID(); saveGeneration = UUID()
        if let requestID = requestID { asset.cancelContentEditingInputRequest(requestID) }
        requestID = nil
        if let id = currentPreviewRequestID { PHImageManager.default().cancelImageRequest(id) }
        currentPreviewRequestID = nil; session.cancel()
    }
    private func cancelAndDismiss() { guard !committing else { return }; abandon(); dismiss() }
}

