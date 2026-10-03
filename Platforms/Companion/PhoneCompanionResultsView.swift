import SwiftUI
import Photos
import ImageIO
import CelluloidRendering

@MainActor final class PhoneCompanionController: ObservableObject {
    static let shared = PhoneCompanionController()
    @Published var records: [PhoneCompanionRecord] = []
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
    func reload() async { do { records = try await processor?.records() ?? [] } catch { self.error = error.localizedDescription } }
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
    }
}

/// Added to the phone's navigation only with the final UIKit integration checkpoint.
struct PhoneCompanionResultsView: View {
    @ObservedObject var model: PhoneCompanionController
    @State private var selection: PhoneCompanionRecord?
    var body: some View {
        List {
            if model.records.isEmpty { Text("No Watch processing results yet. Choose a photo on your Watch and request phone processing.") }
            ForEach(model.records) { record in
                Button { selection = record } label: {
                    VStack(alignment: .leading) {
                        Text(record.request.filter.localizedTitle)
                        Text(record.created, style: .date).font(.caption)
                        if record.delivery == .pending || record.delivery == .failed {
                            Text("Ready on iPhone; Watch delivery is pending or failed.").font(.caption)
                        }
                    }
                }
            }
        }.navigationTitle("Watch Photos").task { await model.reload() }
            .sheet(item: $selection) { record in PhoneCompanionResultView(model: model, record: record) }
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
                    if let image { Image(image, scale: 1, label: Text("Processed photo")).resizable().scaledToFit() }
                    Text("Full-size result kept on this iPhone. Saving creates a new Photos image and keeps the original unchanged.")
                    Button("Save Picture to Photos") {
                        busy = true
                        Task {
                            defer { busy = false }
                            do { try await model.saveToPhotos(record); message = NSLocalizedString("Saved to Photos and verified by reading the image back.", comment: "Companion") }
                            catch { message = error.localizedDescription }
                        }
                    }.disabled(busy)
                    if busy { ProgressView() }
                    if let message { Text(message) }
                    Button("Delete Phone Result", role: .destructive) { confirmDelete = true }.disabled(busy)
                }.padding()
            }.navigationTitle("Watch Photo")
                .toolbar { Button("Done") { dismiss() } }
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
