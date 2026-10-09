import UIKit
import Combine
import SwiftUI
import Photos
import PhotosUI
import CelluloidKit

/// PhotoKit requires a UIViewController protocol entry point. All editor UI,
/// recipe state and user actions are owned by the shared SwiftUI editor.
final class PhotoEditingViewController: UIViewController, PHContentEditingController {
    let session = CelluloidEditingSession()
    private var hostingController: UIHostingController<CelluloidEditorContent>?
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
        view.backgroundColor = .blackBackgroundColor
        let host = UIHostingController(rootView: CelluloidEditorContent(session: session))
        addChild(host)
        host.view.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(host.view)
        NSLayoutConstraint.activate([
            host.view.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            host.view.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            host.view.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            host.view.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor)
        ])
        host.didMove(toParent: self)
        hostingController = host
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
    private var pendingPreparation: AnyCancellable?
    private var pendingPreparationTimeout: DispatchWorkItem?
    #if DEBUG
    var outputWriterPreparedForTesting: ((PhotosOutputWrite) -> Void)?
    var preparationTimeoutForTesting: TimeInterval?
    #endif
    deinit { pendingOutputWrite?.cancel(); pendingPreparationTimeout?.cancel() }
    private func cancelPendingPreparation() {
        pendingPreparation = nil
        pendingPreparationTimeout?.cancel(); pendingPreparationTimeout = nil
    }
    private func cancelPendingOutputWrite() {
        pendingOutputWrite?.cancel(); pendingOutputWrite = nil
    }
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        AdjustmentData.supportIdentifier(adjustmentData.formatIdentifier, version: adjustmentData.formatVersion)
    }
    func startContentEditing(with input: PHContentEditingInput, placeholderImage: UIImage) {
        cancelled = false; cancelPendingPreparation(); cancelPendingOutputWrite(); sessionGeneration &+= 1
        loadViewIfNeeded(); view.isUserInteractionEnabled = true
        session.start(input: input, placeholder: placeholderImage)
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        let finish = { [weak self] in
            guard let self = self, !self.cancelled else { return }
            guard let input = self.session.input else { completionHandler(nil); return }
            self.sessionGeneration &+= 1
            self.cancelPendingPreparation()
            self.cancelPendingOutputWrite()
            if self.session.phase == .loading || self.needsLegacyCanvas {
                let generation = self.sessionGeneration
                self.view.isUserInteractionEnabled = false
                var preparationCompleted = false
                let finishPreparation: (Bool) -> Void = { [weak self] ready in
                    guard let self = self, !preparationCompleted, !self.cancelled,
                          self.sessionGeneration == generation, self.session.input === input else { return }
                    preparationCompleted = true
                    self.cancelPendingPreparation()
                    if ready { self.finishContentEditing(completionHandler: completionHandler) }
                    else {
                        self.view.isUserInteractionEnabled = true
                        completionHandler(nil)
                    }
                }
                self.pendingPreparation = Publishers.CombineLatest(self.session.$phase, self.session.$adjustment)
                    .receive(on: DispatchQueue.main)
                    .filter { [weak self] _ in
                        guard let self = self, !self.cancelled,
                              self.sessionGeneration == generation, self.session.input === input else { return false }
                        // A legacy archive has absolute preview points. Decode
                        // readiness alone does not establish that coordinate space.
                        self.view.setNeedsLayout(); self.view.layoutIfNeeded()
                        return self.session.phase != .loading && self.session.phase != .empty && !self.needsLegacyCanvas
                    }
                    .first()
                    .sink { _ in finishPreparation(true) }
                // The active host must receive a result even if its view never
                // mounts or has no drawable size. Failure never writes a raster.
                let timeout = DispatchWorkItem { finishPreparation(false) }
                self.pendingPreparationTimeout = timeout
                #if DEBUG
                let interval = self.preparationTimeoutForTesting ?? 10
                #else
                let interval: TimeInterval = 10
                #endif
                DispatchQueue.main.asyncAfter(deadline: .now() + interval, execute: timeout)
                return
            }
            if self.session.isReadOnly {
                self.view.isUserInteractionEnabled = true
                completionHandler(PHContentEditingOutput(contentEditingInput: input))
                return
            }
            let generation = self.sessionGeneration
            self.view.isUserInteractionEnabled = false
            var completed = false
            let finishCurrentSession: (PHContentEditingOutput?) -> Void = { [weak self] output in
                guard let self = self, !completed, !self.cancelled,
                      self.sessionGeneration == generation, self.session.input === input else { return }
                completed = true; self.view.isUserInteractionEnabled = true
                completionHandler(output)
            }
            self.session.export { [weak self] result in
                guard let self = self, !self.cancelled,
                      self.sessionGeneration == generation, self.session.input === input else { return }
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
                          self.sessionGeneration == generation, self.session.input === input,
                          self.pendingOutputWrite === writer else { writer.cancel(); return }
                    self.pendingOutputWrite = nil
                    guard case .success = result, writer.claimForDelivery() else {
                        writer.cancel(); finishCurrentSession(nil); return
                    }
                    finishCurrentSession(output)
                    writer.completeDelivery()
                }
            }
        }
        if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
    }
    private var needsLegacyCanvas: Bool {
        session.phase == .ready && session.adjustment.referenceCanvasSize == nil
            && (!session.adjustment.bubbles.isEmpty || !session.adjustment.stickers.isEmpty)
    }
    var shouldShowCancelConfirmation: Bool { !session.isReadOnly }
    func cancelContentEditing() {
        cancelled = true; cancelPendingPreparation(); sessionGeneration &+= 1
        cancelPendingOutputWrite(); session.cancel()
        viewIfLoaded?.isUserInteractionEnabled = true
    }

    #if DEBUG
    // Transitional inspection seams keep existing rendering/Photos tests in the
    // target while their UIKit-layout assumptions migrate. No legacy screen runs.
    var input: PHContentEditingInput? {
        get { session.input }
        set { if let input = newValue { session.start(input: input, placeholder: input.displaySizeImage) } else { session.cancel() } }
    }
    var sourceImage: UIImage? {
        get { session.sourceImage }
        set { if let image = newValue { session.startCopy(image: image) } else { session.cancel() } }
    }
    var preview: UIImageView { session.previewViewForTesting }
    var adjustmentData: AdjustmentData { session.adjustment }
    var outputImage: UIImage? { session.outputImageForTesting }
    var preservedAdjustmentData: PHAdjustmentData? { session.preservedAdjustmentData }
    var isAdjustmentReadOnly: Bool { session.isReadOnly }
    var activeExportForTesting: PhotoExportTask? { session.activeExportForTesting }
    func restoreFromData(_ data: AdjustmentData) { session.restore(data) }
    func preserveUnreadableAdjustment(_ data: PHAdjustmentData, currentImage: UIImage?) { session.preserve(data, currentImage: currentImage) }
    #endif
}
