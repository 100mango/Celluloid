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
        input = contentEditingInput
        if sourceImage == nil { sourceImage = placeholderImage }
        if let data = contentEditingInput.adjustmentData, canHandle(data),
           let decoded = try? AdjustmentData.decode(data.data) { restoreFromData(decoded) }
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        let finish = { [weak self] in
            guard let self = self, !self.cancelled, let input = self.input else { completionHandler(nil); return }
            let generation = self.sessionGeneration
            self.exportPhoto { [weak self] result in
                guard let self = self, !self.cancelled, self.sessionGeneration == generation, self.input === input,
                      case .success(let exported) = result else { completionHandler(nil); return }
                let output = PHContentEditingOutput(contentEditingInput: input)
                output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
                    formatVersion: AdjustmentData.formatVersion, data: exported.adjustmentData)
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        try exported.jpegData.write(to: output.renderedContentURL, options: .atomic)
                        DispatchQueue.main.async { [weak self] in
                            guard let self = self, !self.cancelled, self.sessionGeneration == generation, self.input === input else { completionHandler(nil); return }
                            completionHandler(output)
                        }
                    } catch { DispatchQueue.main.async { completionHandler(nil) } }
                }
            }
        }
        if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
    }
    var shouldShowCancelConfirmation: Bool { true }
    func cancelContentEditing() { cancelled = true; sessionGeneration &+= 1; cancelExport() }
}
