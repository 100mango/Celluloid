import SwiftUI
import PhotosUI
import CoreTransferable
import UniformTypeIdentifiers
import CelluloidDomain

@main struct CelluloidWatchApp: App {
    var body: some Scene { WindowGroup { WatchGalleryView() } }
}
@MainActor final class WatchGalleryModel: ObservableObject {
    @Published var photos: [WatchPhoto] = []
    @Published var error: String?
    @Published var importing = false
    let store: WatchGalleryStore?
    let transport: WatchCompanionTransport?
    init() {
        do {
            let store = try WatchGalleryStore(); self.store = store
            let transport = WatchCompanionTransport(store: store); self.transport = transport
            transport.changed = { [weak self] in Task { await self?.reload() } }
            transport.failure = { [weak self] message in self?.error = message }
            transport.activate()
        } catch { self.store = nil; self.transport = nil; self.error = Self.message(error) }
    }
    static func message(_ error: Error) -> String {
        if (error as? RecipeError) == .resourceLimit {
            return NSLocalizedString("Use a still photo up to 8 MB. The Watch gallery holds up to 20 photos and 32 MB; remove a local copy to make room.", comment: "Watch limits")
        }
        return error.localizedDescription
    }
    func reload() async { do { photos = try await store?.load() ?? [] } catch { self.error = Self.message(error) } }
    func importPhoto(_ item: PhotosPickerItem) async {
        guard let store, !importing else { return }
        importing = true; defer { importing = false }
        do {
            guard let received = try await item.loadTransferable(type: WatchSelectedFile.self) else { throw RecipeError.invalidDocument }
            let bytes = received.bytes
            guard bytes.count <= 8 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            _ = try await store.importPhoto(bytes, name: NSLocalizedString("Selected Photo", comment: "Watch photo"))
            await reload()
        } catch { self.error = Self.message(error) }
    }
    func remove(_ photo: WatchPhoto) async {
        do {
            try await transport?.cancel(photo); try await store?.remove(photo.id); await reload()
        } catch { self.error = Self.message(error) }
    }
}
struct WatchGalleryView: View {
    @StateObject private var model = WatchGalleryModel()
    @State private var selection: PhotosPickerItem?
    var body: some View {
        NavigationStack {
            List {
                PhotosPicker(selection: $selection, matching: .images) { Label("Choose Photo", systemImage: "photo") }
                    .accessibilityIdentifier("watch.import-photo").disabled(model.importing)
                if model.importing { ProgressView() }
                if model.photos.isEmpty { Text("Selected photos stay on this Watch and can be viewed offline.") }
                ForEach(model.photos) { photo in
                    NavigationLink { WatchPhotoView(model: model, id: photo.id) } label: { Text(photo.name) }
                        .accessibilityIdentifier("watch.photo." + photo.id.uuidString)
                }
                NavigationLink("Privacy Policy") {
                    ScrollView {
                        Text(Bundle.main.url(forResource: "PrivacyPolicy", withExtension: "txt").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? "https://100mango.github.io/app-privacy/")
                        Text("https://100mango.github.io/app-privacy/").font(.footnote)
                    }.padding()
                }
            }.navigationTitle("Celluloid")
        }
        .task { await model.reload() }
        .onChange(of: selection) { value in if let value { Task { await model.importPhoto(value) } } }
        .alert("Celluloid", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK", role: .cancel) { model.error = nil }
        } message: { Text(model.error ?? "") }
    }
}
private struct WatchPhotoView: View {
    @ObservedObject var model: WatchGalleryModel
    let id: UUID
    @State private var image: CGImage?
    @State private var filter = FilterPreset.original
    @State private var confirmDelete = false
    @Environment(\.dismiss) private var dismiss
    private var photo: WatchPhoto? { model.photos.first { $0.id == id } }
    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                if let image { Image(image, scale: 1, label: Text("Selected photo preview")).resizable().scaledToFit().accessibilityIdentifier("watch.preview") }
                if let photo {
                    Text("Preview up to 512 pixels").font(.footnote)
                    if let job = photo.job {
                        Text(LocalizedStringKey(job.phase.rawValue.capitalized)).accessibilityIdentifier("watch.job-status")
                        if let failure = job.result?.failure { Text(failure).font(.footnote) }
                        if job.phase == .pending || job.phase == .processing {
                            Button("Cancel Request") { Task { do { try await model.transport?.cancel(photo) } catch { model.error = error.localizedDescription } } }
                        }
                    }
                    Picker("Phone Filter", selection: $filter) {
                        ForEach(FilterPreset.allCases, id: \.rawValue) { Text($0.localizedTitle).tag($0) }
                    }
                    Button("Process on iPhone") { Task { do { try await model.transport?.request(photo, filter: filter) } catch { model.error = error.localizedDescription } } }
                        .accessibilityIdentifier("watch.process-phone")
                    Text("Sends only this selected image to your paired iPhone. A returned preview is not a Photos save. Open the phone app to save the full result.").font(.footnote)
                    Button("Remove from Watch", role: .destructive) { confirmDelete = true }
                }
            }
        }.task(id: photo?.job?.phase) {
            do { image = try await model.store?.preview(id, processed: photo?.job?.phase == .completed) }
            catch { model.error = error.localizedDescription }
        }
        .confirmationDialog("Remove this local photo?", isPresented: $confirmDelete) {
            Button("Remove from Watch", role: .destructive) { if let photo { Task { await model.remove(photo); dismiss() } } }
            Button("Cancel", role: .cancel) { }
        } message: { Text("This removes only the Watch copy. Photos and the paired iPhone stay unchanged.") }
    }
}

/// Request a temporary file representation so the encoded-byte cap is checked before allocation.
private struct WatchSelectedFile: Transferable {
    let bytes: Data
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .image) { received in
            let values = try received.file.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
            guard values.isRegularFile == true, let size = values.fileSize, size <= 8 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            let handle = try FileHandle(forReadingFrom: received.file); defer { try? handle.close() }
            var bytes = Data()
            while let part = try handle.read(upToCount: 64 * 1024), !part.isEmpty {
                guard bytes.count + part.count <= 8 * 1024 * 1024 else { throw RecipeError.resourceLimit }
                bytes.append(part)
            }
            return WatchSelectedFile(bytes: bytes)
        }
    }
}
