import UIKit
import Photos
import PhotosUI
import CelluloidKit

final class PhotoEditingViewController: BaseEditPhotoController, PHContentEditingController {
    // Photos owns the navigation bar and displays this view behind it. Keep
    // only that system-chrome region semantic; the existing photo canvas stays
    // dark. No host navigation appearance or interface style is overridden.
    let hostNavigationBackground: UIView = {
        let surface = UIView()
        surface.backgroundColor = .systemBackground
        surface.isUserInteractionEnabled = false
        surface.isAccessibilityElement = false
        surface.accessibilityElementsHidden = true
        surface.translatesAutoresizingMaskIntoConstraints = false
        return surface
    }()
    override func viewDidLoad() {
        super.viewDidLoad()
        view.addSubview(hostNavigationBackground)
        NSLayoutConstraint.activate([
            hostNavigationBackground.topAnchor.constraint(equalTo: view.topAnchor),
            hostNavigationBackground.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            hostNavigationBackground.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            hostNavigationBackground.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor)
        ])
    }
    private var cancelled = false
    private var sessionGeneration: UInt64 = 0
    private var pendingOutputWrite: PhotosOutputWrite?
    #if DEBUG
    var outputWriterPreparedForTesting: ((PhotosOutputWrite) -> Void)?
    #endif
    deinit { pendingOutputWrite?.cancel() }
    private func cancelPendingOutputWrite() {
        pendingOutputWrite?.cancel()
        pendingOutputWrite = nil
    }
    private var needsUnreadableNotice = false
    private weak var unreadableNotice: UIAlertController?
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        // This is format negotiation, not validation of a particular input.
        // Inspect input.adjustmentData in start so opaque errors cannot be
        // accidentally associated with a different photo/session.
        AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
    }
    func startContentEditing(with contentEditingInput: PHContentEditingInput, placeholderImage: UIImage) {
        cancelled = false
        cancelPendingOutputWrite()
        sessionGeneration &+= 1
        needsUnreadableNotice = false
        unreadableNotice?.dismiss(animated: false)
        loadViewIfNeeded()
        view.isUserInteractionEnabled = true
        input = contentEditingInput
        if sourceImage == nil { sourceImage = placeholderImage }
        if let data = contentEditingInput.adjustmentData {
            do {
                guard AdjustmentData.supportIdentifier(data.formatIdentifier, version: data.formatVersion) else {
                    throw AdjustmentDataError.invalidValue("bound adjustment format")
                }
                restoreFromData(try AdjustmentData.decode(data.data))
            } catch {
                // Apple defines placeholderImage as the current rendered state;
                // the handled input's displaySizeImage is the earlier version.
                preserveUnreadableAdjustment(data, currentImage: placeholderImage)
                needsUnreadableNotice = true
                if view.window != nil { presentUnreadableNoticeIfNeeded() }
            }
        }
    }
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        presentUnreadableNoticeIfNeeded()
    }
    private func presentUnreadableNoticeIfNeeded() {
        guard needsUnreadableNotice, !cancelled, isAdjustmentReadOnly, presentedViewController == nil else { return }
        needsUnreadableNotice = false
        let alert = UIAlertController(title: tr(.unreadableEditsTitle), message: tr(.unreadableEditsMessage), preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: tr(.done), style: .default))
        unreadableNotice = alert
        present(alert, animated: true)
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        let finish = { [weak self] in
            guard let self = self, !self.cancelled else { return }
            guard let input = self.input else { completionHandler(nil); return }
            // A repeated finish supersedes the previous preparation just as a
            // new start does. Its canceled export cannot complete an older host
            // request or re-enable controls while this one is still rendering.
            self.sessionGeneration &+= 1
            self.cancelPendingOutputWrite()
            if self.isAdjustmentReadOnly {
                // Documented Photos no-change output: no adjustment data and no
                // write to renderedContentURL. Never replace the opaque recipe.
                completionHandler(PHContentEditingOutput(contentEditingInput: input))
                return
            }
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
                let writer = PhotosOutputWrite(destination: output.renderedContentURL)
                self.pendingOutputWrite = writer
                #if DEBUG
                self.outputWriterPreparedForTesting?(writer)
                #endif
                writer.start(jpeg: exported.jpegData) { [weak self] writer, result in
                    guard let self = self, !self.cancelled,
                          self.sessionGeneration == generation, self.input === input,
                          self.pendingOutputWrite === writer else { writer.cancel(); return }
                    self.pendingOutputWrite = nil
                    guard case .success = result, writer.claimForDelivery() else {
                        writer.cancel()
                        finishCurrentSession(nil)
                        return
                    }
                    // Claim prevents reentrant cancellation from deleting the
                    // handed-off result. Its destination remains reserved until
                    // the actual Photos completion returns.
                    finishCurrentSession(output)
                    writer.completeDelivery()
                }
            }
        }
        if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
    }
    // A protected session cannot create unsaved edits and returns a no-change
    // output. Editable sessions retain conservative confirmation, including
    // while a render/write is preparing. Existing cancellation ownership stays
    // unchanged for the render, writer and pending Photos callback.
    var shouldShowCancelConfirmation: Bool { !isAdjustmentReadOnly }
    func cancelContentEditing() {
        cancelled = true
        needsUnreadableNotice = false
        sessionGeneration &+= 1
        cancelPendingOutputWrite()
        cancelExport()
        // Release the preview and session's input URL ownership once abandoned.
        input = nil
        viewIfLoaded?.isUserInteractionEnabled = true
    }
}
