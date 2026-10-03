import Foundation
import CryptoKit
import SwiftUI
import CelluloidDomain
import CelluloidRendering

struct TVSavedRecipe: Codable, Equatable {
    var version = 1
    var recipe: EditRecipe
    var photoIDs: [UUID: String]
    var fingerprints: [UUID: String]
    static let maximumBytes = 192 * 1024
    func encoded() throws -> Data {
        try recipe.validate()
        guard version == 1, Set(photoIDs.keys) == Set(recipe.sources.map(\.id)), Set(fingerprints.keys) == Set(photoIDs.keys),
              fingerprints.values.allSatisfy({ $0.count == 64 && $0.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) } }),
              photoIDs.values.allSatisfy({ !$0.isEmpty && $0.utf8.count <= 4096 }) else { throw RecipeError.invalidDocument }
        let bytes = try JSONEncoder().encode(self)
        guard bytes.count <= Self.maximumBytes else { throw RecipeError.resourceLimit }
        return bytes
    }
    static func fingerprint(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    func verify(_ data: Data, sourceID: UUID) throws {
        guard fingerprints[sourceID] == Self.fingerprint(data) else { throw TVPhotoError.changed }
    }
    static func decode(_ bytes: Data) throws -> Self {
        guard bytes.count <= maximumBytes else { throw RecipeError.resourceLimit }
        let value = try JSONDecoder().decode(Self.self, from: bytes)
        _ = try value.encoded(); return value
    }
}

@MainActor final class TVEditorModel: ObservableObject {
    @Published private(set) var recipe = EditRecipe()
    @Published private(set) var preview: CGImage?
    @Published private(set) var busy = false
    @Published var error: String?
    @Published var status = ""
    @Published var selectedLayer: UUID?
    private(set) var photoIDs: [UUID: String] = [:]
    private(set) var fingerprints: [UUID: String] = [:]
    private(set) var originals: [UUID: Data] = [:]
    private var history: [EditRecipe] = []
    private var renderTask: Task<Void, Never>?
    private var operation = UUID()
    private let defaults: UserDefaults
    static let savedKey = "celluloid.tv.recipe.v1"
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    var hasSavedRecipe: Bool { defaults.data(forKey: Self.savedKey) != nil }
    var canUndo: Bool { !history.isEmpty }

    func importPhotos(_ ids: [String], library: any TVPhotoDataSource) async {
        guard !busy else { return }
        guard (1...4).contains(ids.count), Set(ids).count == ids.count else { error = TVPhotoError.tooMany.localizedDescription; return }
        let generation = UUID(); operation = generation; busy = true
        defer { if operation == generation { busy = false } }
        do {
            var next = EditRecipe(), data: [UUID: Data] = [:], references: [UUID: String] = [:], hashes: [UUID: String] = [:]
            for (index, id) in ids.enumerated() {
                let bytes = try await library.currentImageData(id, limit: 64 * 1024 * 1024 - data.values.reduce(0, { $0 + $1.count }))
                guard data.values.reduce(0, { $0 + $1.count }) + bytes.count <= 64 * 1024 * 1024 else { throw RecipeError.resourceLimit }
                let source = try RasterCodec.metadata(bytes, name: String(format: NSLocalizedString("Photo %d", comment: "Imported photo name"), index + 1))
                next.sources.append(source); data[source.id] = bytes; references[source.id] = id; hashes[source.id] = TVSavedRecipe.fingerprint(bytes)
            }
            try Self.configureCanvas(&next)
            guard operation == generation else { return }
            recipe = next; originals = data; photoIDs = references; fingerprints = hashes; history.removeAll(); selectedLayer = nil
            render(); status = NSLocalizedString("Photos imported. Save the finished picture to Photos before leaving.", comment: "TV status")
        } catch { if operation == generation { self.error = error.localizedDescription } }
    }
    static func configureCanvas(_ recipe: inout EditRecipe) throws {
        if recipe.sources.count == 1, let source = recipe.sources.first {
            recipe.canvasWidth = source.pixelWidth; recipe.canvasHeight = source.pixelHeight; recipe.collageTemplate = nil
        } else {
            recipe.canvasWidth = 800; recipe.canvasHeight = 800
            recipe.collageTemplate = try NativeResources.templates(count: recipe.sources.count).first?.assetName
        }
        try recipe.validate()
    }
    func change(_ mutate: (inout EditRecipe) -> Void) {
        guard !busy else { return }
        var next = recipe; mutate(&next)
        do {
            try next.validate()
            guard next != recipe else { return }
            history.append(recipe); if history.count > 20 { history.removeFirst() }
            recipe = next; render()
        } catch { self.error = error.localizedDescription }
    }
    func undo() { if let previous = history.popLast() { recipe = previous; render() } }
    func add(_ overlay: Overlay) { change { $0.overlays.append(overlay) }; selectedLayer = overlay.id }
    func editLayer(_ mutate: (inout Overlay) -> Void) {
        guard let index = recipe.overlays.firstIndex(where: { $0.id == selectedLayer }) else { return }
        change { mutate(&$0.overlays[index]) }
    }
    func keepRecipe() {
        do {
            let snapshot = TVSavedRecipe(recipe: recipe, photoIDs: photoIDs.filter { id, _ in recipe.sources.contains { $0.id == id } }, fingerprints: fingerprints.filter { id, _ in recipe.sources.contains { $0.id == id } })
            let bytes = try snapshot.encoded()
            // Only one bounded metadata record. No image data, thumbnails or documents in defaults.
            defaults.set(bytes, forKey: Self.savedKey)
            guard defaults.data(forKey: Self.savedKey) == bytes else { throw RecipeError.invalidDocument }
            #if DEBUG
            if let mode = ProcessInfo.processInfo.environment["CELLULOID_TV_COMPOSITION_PROOF"], ["2","3","4"].contains(mode) {
                let root = try FileManager.default.url(for:.cachesDirectory,in:.userDomainMask,appropriateFor:nil,create:true).appendingPathComponent("TVCompositionProof/" + mode,isDirectory:true)
                try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
                for source in recipe.sources {
                    guard let original = originals[source.id], original.count <= 5_000_000 else { throw RecipeError.resourceLimit }
                    try original.write(to:root.appendingPathComponent(source.id.uuidString + ".image"),options:.atomic)
                }
                // The bytes actually accepted by defaults, not a separately fabricated recipe.
                try bytes.write(to:root.appendingPathComponent("kept-recipe.json"),options:.atomic)
            }
            #endif
            status = NSLocalizedString("Recipe kept on this TV. Source photos must remain available in Photos.", comment: "TV status")
        } catch { self.error = error.localizedDescription }
    }
    func reopen(library: any TVPhotoDataSource) async {
        guard !busy else { return }
        guard let bytes = defaults.data(forKey: Self.savedKey) else { return }
        busy = true; defer { busy = false }
        do {
            let saved = try TVSavedRecipe.decode(bytes)
            var data: [UUID: Data] = [:]
            for source in saved.recipe.sources {
                guard let id = saved.photoIDs[source.id] else { throw TVPhotoError.missing }
                let bytes = try await library.currentImageData(id, limit: 64 * 1024 * 1024 - data.values.reduce(0, { $0 + $1.count }))
                try saved.verify(bytes, sourceID: source.id)
                let info = try RasterCodec.metadata(bytes)
                guard info.pixelWidth == source.pixelWidth, info.pixelHeight == source.pixelHeight,
                      data.values.reduce(0, { $0 + $1.count }) + bytes.count <= 64 * 1024 * 1024 else { throw RecipeError.resourceLimit }
                data[source.id] = bytes
            }
            recipe = saved.recipe; originals = data; photoIDs = saved.photoIDs; fingerprints = saved.fingerprints; history.removeAll(); render()
            status = NSLocalizedString("Editable recipe reopened from Photos sources.", comment: "TV status")
        } catch { self.error = error.localizedDescription }
    }
    func saveToPhotos(library: any TVPhotoDataSource) async {
        guard !busy, !recipe.sources.isEmpty else { return }
        busy = true; defer { busy = false }
        do {
            let bytes = try await NativeRenderQueue.shared.export(recipe, sources: originals, type: .png)
            _ = try await library.saveVerifiedPNG(bytes)
            status = NSLocalizedString("Saved to Photos and verified by reading the image back.", comment: "TV status")
        } catch { self.error = error.localizedDescription }
    }
    private func render() {
        renderTask?.cancel()
        let snapshot = recipe, data = originals
        renderTask = Task {
            do {
                let image = try await NativeRenderQueue.shared.preview(snapshot, sources: data, maximumDimension: 1600)
                try Task.checkCancellation(); preview = image
            } catch is CancellationError { }
            catch { if !Task.isCancelled { self.error = error.localizedDescription } }
        }
    }
}
