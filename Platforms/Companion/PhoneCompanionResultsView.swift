import SwiftUI
import Photos
import ImageIO
import CelluloidRendering
import CelluloidDomain

@MainActor final class PhoneCompanionController: ObservableObject {
    static let shared = PhoneCompanionController()
    @Published var records: [PhoneCompanionRecord] = []
    @Published var pending: [CompanionRequest] = []
    @Published var resuming = false
    @Published var error: String?
    let processor: PhoneCompanionProcessor?
    private let transport: PhoneCompanionTransport?
    private init() {
        do {
            let processor = try PhoneCompanionProcessor(); self.processor = processor
            let transport = PhoneCompanionTransport(processor: processor); self.transport = transport
            transport.changed = { [weak self] in Task { await self?.reload() } }
        } catch { self.processor = nil; self.transport = nil; self.error = error.localizedDescription }
    }
    func activate() { transport?.activate(); Task { await reload() } }
    func reload() async {
        do {
            pending = try await processor?.pendingRequests() ?? []; records = try await processor?.records() ?? []
            if let notice = processor?.inbox.recoveryNotice { error = notice }
        }
        catch { self.error = error.localizedDescription }
    }
    func resume(_ request: CompanionRequest) async {
        guard !resuming else { return }; error = nil; resuming = true; defer { resuming = false }
        do { _ = try await processor?.resumePending(request.id); await reload() }
        catch { self.error = error.localizedDescription; await reload() }
    }
    func discard(_ request: CompanionRequest) async {
        do { try await processor?.discardPending(request.id); error = nil; await reload() }
        catch { self.error = error.localizedDescription }
    }
    func delete(_ record: PhoneCompanionRecord) async {
        do { try await processor?.remove(record.id); await reload() } catch { self.error = error.localizedDescription }
    }
    func saveToPhotos(_ record: PhoneCompanionRecord) async throws {
        guard let processor else { throw RenderError.exportFailed }
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        guard status == .authorized || status == .limited else { throw CocoaError(.fileWriteNoPermission) }
        let bytes = try await processor.fullResult(record.id)
        var identifier: String?
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            request.addResource(with: .photo, data: bytes, options: nil)
            identifier = request.placeholderForCreatedAsset?.localIdentifier
        }
        guard let identifier, let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject else { throw RenderError.exportFailed }
        let options = PHImageRequestOptions(); options.version = .original; options.isNetworkAccessAllowed = false
        let actual: Data = try await withCheckedThrowingContinuation { continuation in
            PHImageManager.default().requestImageDataAndOrientation(for: asset, options: options) { data, _, _, info in
                if let error = info?[PHImageErrorKey] as? Error { continuation.resume(throwing: error) }
                else if let data { continuation.resume(returning: data) }
                else { continuation.resume(throwing: RenderError.exportFailed) }
            }
        }
        // The PNG resource is immutable; exact original-byte comparison also proves all pixels.
        guard actual == bytes else { throw RenderError.exportFailed }
        #if DEBUG
        if ProcessInfo.processInfo.environment["CELLULOID_PHONE_OUTPUT_PROOF"] == "YES" {
            guard actual.count <= 5_000_000 else { throw RecipeError.resourceLimit }
            let folder = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("PhoneOutputProof", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try actual.write(to: folder.appendingPathComponent("photos-output.png"), options: .atomic)
            let metadata: [String: Any] = ["requestID": record.id.uuidString, "sourceSHA256": record.request.sourceSHA256,
                                           "filter": record.request.filter.rawValue, "photosAssetIdentifier": identifier,
                                           "sha256": PhoneCompanionProcessor.digest(actual), "bytes": actual.count]
            try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: folder.appendingPathComponent("photos-output.json"), options: .atomic)
        }
        #endif
    }
}

/// Added to the phone's navigation only with the final UIKit integration checkpoint.
struct PhoneCompanionResultsView: View {
    @ObservedObject var model: PhoneCompanionController
    @State private var selection: PhoneCompanionRecord?
    @State private var discard: CompanionRequest?
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        List {
            if !model.pending.isEmpty {
                Text("Interrupted or queued requests are kept on this iPhone. Resume locally; to receive a new preview, request processing again from your current Watch.")
                    .font(.body).fixedSize(horizontal: false, vertical: true)
                ForEach(model.pending, id: \.id) { request in
                    VStack(alignment: .leading) {
                        Text(request.filter.localizedTitle)
                        // List's automatic row button style can join multiple
                        // controls into one row action. Keep each intent distinct.
                        Button {
                            #if DEBUG
                            print("PHONE_COMPANION_ROW_ACTION resume id=\(request.id)")
                            #endif
                            Task { await model.resume(request) }
                        } label: { Text("Resume on iPhone").foregroundStyle(.primary) }
                            .buttonStyle(.borderless).disabled(model.resuming).accessibilityIdentifier("companion.resume." + request.id.uuidString)
                        Button(role: .destructive) {
                            #if DEBUG
                            print("PHONE_COMPANION_ROW_ACTION discard id=\(request.id)")
                            #endif
                            discard = request
                        } label: { Text("Discard Pending Request").foregroundStyle(.primary) }
                            .buttonStyle(.borderless).disabled(model.resuming).accessibilityIdentifier("companion.discard." + request.id.uuidString)
                    }
                }
            }
            if let error = model.error { Text(error).foregroundStyle(.red) }
            if model.records.isEmpty { Text("No Watch processing results yet. Choose a photo on your Watch and request phone processing.")
                    .font(.body).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("companion.empty") }
            ForEach(model.records) { record in
                Button { selection = record } label: {
                    VStack(alignment: .leading) {
                        Text(record.request.filter.localizedTitle)
                        Text(record.created, style: .date).font(.caption)
                        if record.delivery == .pending || record.delivery == .failed {
                            Text("Ready on iPhone; Watch delivery is pending or failed.").font(.caption)
                        } else if record.delivery == .queued {
                            Text("Watch preview queued. Receipt is not confirmed.").font(.caption)
                        } else {
                            Text("Watch preview transfer finished. Check your Watch for the received result.").font(.caption)
                        }
                    }
                }.accessibilityIdentifier("companion.result." + record.id.uuidString)
            }
        }.navigationTitle("Watch Photos").task { await model.reload() }
            .sheet(item: $selection) { record in PhoneCompanionResultView(model: model, record: record) }
            .onChange(of: scenePhase) { phase in if phase == .active { Task { await model.reload() } } }
            .confirmationDialog("Discard this pending phone request?", isPresented: Binding(get: { discard != nil }, set: { if !$0 { discard = nil } })) {
                Button("Discard Pending Request", role: .destructive) { if let request = discard { Task { await model.discard(request) } }; discard = nil }
                Button("Cancel", role: .cancel) { discard = nil }
            } message: { Text("Only the pending phone copy is removed. The Watch photo and Photos library stay unchanged.") }
    }
}
private struct PhoneCompanionResultView: View {
    @ObservedObject var model: PhoneCompanionController
    let record: PhoneCompanionRecord
    @State private var image: CGImage?
    @State private var busy = false
    @State private var message: String?
    @State private var confirmDelete = false
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    if let image { Image(image, scale: 1, label: Text("Processed photo")).resizable().scaledToFit().accessibilityIdentifier("companion.preview") }
                    Text("The result uses the image resolution received from your Watch. Saving creates a new Photos image and keeps existing Photos assets unchanged.")
                    Button("Save Picture to Photos") {
                        busy = true
                        Task {
                            defer { busy = false }
                            do { try await model.saveToPhotos(record); message = NSLocalizedString("Saved to Photos and verified by reading the image back.", comment: "Companion") }
                            catch { message = error.localizedDescription }
                        }
                    }.disabled(busy).accessibilityIdentifier("companion.save")
                    if busy { ProgressView() }
                    if let message { Text(message).accessibilityIdentifier("companion.save-status") }
                    Button("Delete Phone Result", role: .destructive) { confirmDelete = true }.disabled(busy).accessibilityIdentifier("companion.delete")
                }.padding()
            }.navigationTitle("Watch Photo")
                .toolbar { Button("Done") { dismiss() }.accessibilityIdentifier("companion.done") }
        }.task {
            do {
                if let bytes = try await model.processor?.fullResult(record.id), let source = CGImageSourceCreateWithData(bytes as CFData, nil) {
                    image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1400, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary)
                }
            } catch { message = error.localizedDescription }
        }.confirmationDialog("Delete this phone processing result?", isPresented: $confirmDelete) {
            Button("Delete Phone Result", role: .destructive) { Task { await model.delete(record); dismiss() } }
            Button("Cancel", role: .cancel) { }
        } message: { Text("Existing Photos images and Watch copies stay unchanged.") }
    }
}
