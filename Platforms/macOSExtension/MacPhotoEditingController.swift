import AppKit
import SwiftUI
import Photos
import PhotosUI
import CelluloidDomain
import CelluloidRendering

@MainActor final class MacPhotoEditingController: NSViewController, PHContentEditingController {
    let session = MacPhotoSession()
    private var input: PHContentEditingInput?
    private var generation = UUID()
    private var active = false
    private var pendingWrite: PhotosOutputWrite?
    private let finish = PhotosHostFinishCoordinator<PreparedPhotoOutput>()
    private struct PreparedPhotoOutput {
        let output: PHContentEditingOutput
        let writer: PhotosOutputWrite
    }
    deinit { pendingWrite?.cancel() }
    override func loadView() {
        // The principal object is an NSViewController; the hosted SwiftUI root has
        // real child containment and a resizable, Photos-sized content view.
        let host = NSHostingController(rootView: MacPhotoEditorView(session: session))
        addChild(host); view = NSView(frame: NSRect(x: 0, y: 0, width: 900, height: 640))
        host.view.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(host.view)
        NSLayoutConstraint.activate([host.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            host.view.trailingAnchor.constraint(equalTo: view.trailingAnchor), host.view.topAnchor.constraint(equalTo: view.topAnchor),
            host.view.bottomAnchor.constraint(equalTo: view.bottomAnchor)])
    }
    func canHandle(_ data: PHAdjustmentData) -> Bool {
        // Format negotiation is pure; validation uses only the actual start input.
        // Returning true for damaged supported bytes lets us preserve them with a
        // no-change result instead of replacing them with a flattened recipe.
        MacPhotoAdjustment.supports(identifier: data.formatIdentifier, version: data.formatVersion)
    }
    func startContentEditing(with input: PHContentEditingInput, placeholderImage: NSImage) {
        cancelContentEditing(); self.input = input; active = true; generation = UUID(); _ = view
        session.begin(url: input.fullSizeImageURL, orientation: input.fullSizeImageOrientation,
            previous: input.adjustmentData.map { .init(identifier: $0.formatIdentifier, version: $0.formatVersion, bytes: $0.data) },
            placeholder: placeholderImage)
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        guard active else { return }
        generation = UUID(); finish.cancel(); pendingWrite?.cancel(); pendingWrite = nil
        guard let input else { completionHandler(nil); return }
        // Commit active native text editing before taking the frozen snapshot.
        guard view.window?.makeFirstResponder(nil) != false else { completionHandler(nil); return }
        let snapshot: MacPhotoSnapshot
        switch session.prepareHostFinish() {
        case .noChange:
            // Apple's explicit no-change contract preserves the adjustment bytes,
            // current raster, and original PhotoKit resources without any rewrite.
            completionHandler(PHContentEditingOutput(contentEditingInput: input)); return
        case .unavailable:
            completionHandler(nil); return
        case .render(let prepared):
            snapshot = prepared
        }
        let token = generation
        finish.finish(preparing: { [weak session] in session?.finishing = $0 }, failed: { [weak session] in session?.report($0) }, operation: { [weak self] in
            let adjustmentBytes = try snapshot.adjustment.encode()
            let jpeg = try await MacPhotoRenderQueue.shared.export(snapshot.adjustment, source: snapshot.source, bytes: snapshot.bytes)
            try Task.checkCancellation()
            guard let self, active, generation == token, self.input === input else { throw CancellationError() }
            let output = PHContentEditingOutput(contentEditingInput: input)
            output.adjustmentData = PHAdjustmentData(formatIdentifier: MacPhotoAdjustment.identifier,
                formatVersion: MacPhotoAdjustment.version, data: adjustmentBytes)
            let writer = PhotosOutputWrite(destination: output.renderedContentURL)
            pendingWrite = writer
            return try await withTaskCancellationHandler(operation: {
                try await withCheckedThrowingContinuation { continuation in
                    writer.start(jpeg: jpeg) { writer, result in
                        switch result {
                        case .success: continuation.resume(returning: PreparedPhotoOutput(output: output, writer: writer))
                        case .failure(let error): writer.cancel(); continuation.resume(throwing: error)
                        }
                    }
                }
            }, onCancel: { writer.cancel() })
        }, completion: { [weak self] prepared in
            guard let self, active, generation == token, self.input === input else { prepared?.writer.cancel(); return }
            guard let prepared else { pendingWrite?.cancel(); pendingWrite = nil; completionHandler(nil); return }
            guard pendingWrite === prepared.writer, prepared.writer.claimForDelivery() else {
                prepared.writer.cancel(); pendingWrite = nil; completionHandler(nil); return
            }
            pendingWrite = nil
            completionHandler(prepared.output)
            prepared.writer.completeDelivery()
        })
    }
    var shouldShowCancelConfirmation: Bool { session.changed }
    func cancelContentEditing() {
        active = false; generation = UUID(); finish.cancel(); pendingWrite?.cancel(); pendingWrite = nil
        session.cancel(); input = nil
    }
}
