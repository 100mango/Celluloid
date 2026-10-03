import UIKit
import Photos
import PhotosUI
import CelluloidKit

final class PhotoEditingViewController: BaseEditPhotoController, PHContentEditingController {
    private var cancelled = false
    private var sessionGeneration: UInt64 = 0
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
            && (try? AdjustmentData.decode(adjustmentData.data)) != nil
    }
    func startContentEditing(with contentEditingInput: PHContentEditingInput, placeholderImage: UIImage) {
        cancelled = false
        sessionGeneration &+= 1
        loadViewIfNeeded()
        view.isUserInteractionEnabled = true
        input = contentEditingInput
        if sourceImage == nil { sourceImage = placeholderImage }
        if let data = contentEditingInput.adjustmentData, canHandle(data),
           let decoded = try? AdjustmentData.decode(data.data) { restoreFromData(decoded) }
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        let finish = { [weak self] in
            guard let self = self, !self.cancelled else { return }
            guard let input = self.input else { completionHandler(nil); return }
            // A repeated finish supersedes the previous preparation just as a
            // new start does. Its canceled export cannot complete an older host
            // request or re-enable controls while this one is still rendering.
            self.sessionGeneration &+= 1
            let generation = self.sessionGeneration
            self.view.isUserInteractionEnabled = false
            // The export task completes cancellation once for its own callers.
            // Photos has a different contract: after cancelContentEditing, its
            // pending completion must not be invoked, even with a nil output.
            // https://developer.apple.com/documentation/photosui/phcontenteditingcontroller/cancelcontentediting()
            // A replacement session likewise cannot receive an older response.
            var completed = false
            let finishCurrentSession: (PHContentEditingOutput?) -> Void = { [weak self] output in
                guard let self = self, !completed, !self.cancelled,
                      self.sessionGeneration == generation, self.input === input else { return }
                completed = true
                self.view.isUserInteractionEnabled = true
                completionHandler(output)
            }
            self.exportPhoto { [weak self] result in
                guard let self = self, !self.cancelled,
                      self.sessionGeneration == generation, self.input === input else { return }
                guard case .success(let exported) = result else { finishCurrentSession(nil); return }
                let output = PHContentEditingOutput(contentEditingInput: input)
                output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
                    formatVersion: AdjustmentData.formatVersion, data: exported.adjustmentData)
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        try exported.jpegData.write(to: output.renderedContentURL, options: .atomic)
                        DispatchQueue.main.async { finishCurrentSession(output) }
                    } catch { DispatchQueue.main.async { finishCurrentSession(nil) } }
                }
            }
        }
        if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
    }
    var shouldShowCancelConfirmation: Bool { true }
    func cancelContentEditing() {
        cancelled = true
        sessionGeneration &+= 1
        cancelExport()
        // Release the preview and session's input URL ownership once abandoned.
        input = nil
        viewIfLoaded?.isUserInteractionEnabled = true
    }
}
