import UIKit
import Photos
import PhotosUI
import CelluloidKit

final class PhotoEditingViewController: BaseEditPhotoController, PHContentEditingController {
    private var cancelled = false
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
            && (try? AdjustmentData.decode(adjustmentData.data)) != nil
    }
    func startContentEditing(with contentEditingInput: PHContentEditingInput, placeholderImage: UIImage) {
        cancelled = false
        loadViewIfNeeded()
        input = contentEditingInput
        if preview.image == nil { preview.image = placeholderImage }
        if let data = contentEditingInput.adjustmentData, let decoded = try? AdjustmentData.decode(data.data) { restoreFromData(decoded) }
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        // UIView/layer rendering is main-thread-only, including in the Photos host process.
        let finish = { [weak self] in
            guard let self = self, !self.cancelled, let input = self.input,
                  let image = self.outputImage, let jpeg = image.jpegData(compressionQuality: 1),
                  let data = try? self.adjustmentData.encode() else { completionHandler(nil); return }
            let output = PHContentEditingOutput(contentEditingInput: input)
            output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: AdjustmentData.formatVersion, data: data)
            do {
                try jpeg.write(to: output.renderedContentURL, options: .atomic)
                completionHandler(self.cancelled ? nil : output)
            } catch { completionHandler(nil) }
        }
        if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
    }
    var shouldShowCancelConfirmation: Bool { true }
    func cancelContentEditing() { cancelled = true }
}
