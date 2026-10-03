import AppKit
import SwiftUI
import Photos
import PhotosUI
import ImageIO
import CelluloidDomain
import CelluloidRendering

/// First native host milestone: filter-only editing. The full layered-extension gate remains open.
@MainActor final class MacPhotoEditingController: NSViewController, PHContentEditingController {
    private let session = MacPhotoSession()
    private var input: PHContentEditingInput?
    private var generation = UUID()
    private var export: Task<Void, Never>?
    override func loadView() { view = NSHostingView(rootView: MacPhotoFilterView(session: session)); view.setFrameSize(NSSize(width: 900, height: 640)) }
    func canHandle(_ adjustmentData: PHAdjustmentData) -> Bool {
        return LegacyFilterAdjustment.accepts(identifier: adjustmentData.formatIdentifier, version: adjustmentData.formatVersion, data: adjustmentData.data)
    }
    func startContentEditing(with contentEditingInput: PHContentEditingInput, placeholderImage: NSImage) {
        let previous = contentEditingInput.adjustmentData.map { LegacyFilterAdjustment.Preserved(identifier: $0.formatIdentifier, version: $0.formatVersion, data: $0.data) }
        cancelContentEditing(); input = contentEditingInput; generation = UUID(); _ = view // Access lazily loads the view on the macOS 13 floor.
        session.begin(contentEditingInput, previous: previous)
    }
    func finishContentEditing(completionHandler: @escaping (PHContentEditingOutput?) -> Void) {
        export?.cancel()
        guard let input, let document = session.snapshot else { completionHandler(nil); return }
        let token = generation, previous = session.preserved, preset = session.preset, isBakedBase = session.isBakedBase
        export = Task {
            do {
                var recipe = document.0; recipe.filter = preset
                let jpeg = try await NativeRenderQueue.shared.export(recipe, sources: document.1, type: .jpeg)
                try Task.checkCancellation()
                let output = PHContentEditingOutput(contentEditingInput: input)
                output.adjustmentData = PHAdjustmentData(formatIdentifier: LegacyFilterAdjustment.identifier, formatVersion: LegacyFilterAdjustment.outputVersion(isBakedBase: isBakedBase),
                                                        data: try LegacyFilterAdjustment.encode(preset, preserving: previous, isBakedBase: isBakedBase))
                try jpeg.write(to: output.renderedContentURL, options: .atomic)
                guard try Data(contentsOf: output.renderedContentURL) == jpeg else { throw RenderError.exportFailed }
                guard generation == token, self.input === input, !Task.isCancelled else { completionHandler(nil); return }
                completionHandler(output)
            } catch {
                if generation == token { session.error = error.localizedDescription }
                completionHandler(nil)
            }
        }
    }
    var shouldShowCancelConfirmation: Bool { true }
    func cancelContentEditing() { generation = UUID(); export?.cancel(); export = nil; session.cancel(); input = nil }
}

@MainActor final class MacPhotoSession: ObservableObject {
    @Published var preset = FilterPreset.original
    @Published var preview: CGImage?
    @Published var error: String?
    @Published var busy = false
    @Published var isBakedBase = false
    private(set) var snapshot: (EditRecipe, [UUID: Data])?
    private(set) var preserved: LegacyFilterAdjustment.Preserved?
    private var task: Task<Void, Never>?
    private var generation = UUID()
    func cancel() { generation = UUID(); task?.cancel(); task = nil; snapshot = nil; preserved = nil; preview = nil; error = nil; busy = false }
    func begin(_ input: PHContentEditingInput, previous: LegacyFilterAdjustment.Preserved?) {
        cancel(); let token = generation; busy = true; preset = .original; isBakedBase = true
        // With no associated metadata, do not infer a pristine system original or
        // borrow the last canHandle probe. A native baked-base version is safest.
        if let previous {
            if previous.identifier == LegacyFilterAdjustment.identifier, previous.version == LegacyFilterAdjustment.version,
               let filter = try? LegacyFilterAdjustment.decode(previous.data) { preset = filter; isBakedBase = false }
            else { preserved = previous; isBakedBase = true }
        }
        task = Task {
            do {
                guard let url = input.fullSizeImageURL else { throw RenderError.invalidImage }
                let data = try await NativeImportQueue.shared.read([url])[0].1
                try Task.checkCancellation()
                guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                      let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
                      (properties[kCGImagePropertyOrientation] as? Int ?? 1) == Int(input.fullSizeImageOrientation) else { throw RenderError.invalidImage }
                let image = try RasterCodec.metadata(data)
                var recipe = EditRecipe(); recipe.sources = [image]; recipe.canvasWidth = image.pixelWidth; recipe.canvasHeight = image.pixelHeight
                guard token == generation else { return }
                snapshot = (recipe, [image.id: data]); busy = false; render()
            } catch { if token == generation { busy = false; self.error = error.localizedDescription } }
        }
    }
    func render() {
        guard let snapshot else { return }
        var recipe = snapshot.0
        let sources = snapshot.1
        task?.cancel(); recipe.filter = preset; busy = true; let token = generation
        task = Task {
            do {
                let image = try await NativeRenderQueue.shared.preview(recipe, sources: sources)
                try Task.checkCancellation(); guard token == generation else { return }
                preview = image; busy = false
            } catch is CancellationError { }
            catch { if token == generation { self.error = error.localizedDescription; busy = false } }
        }
    }
}
private struct MacPhotoFilterView: View {
    @ObservedObject var session: MacPhotoSession
    var body: some View {
        HStack(spacing: 20) {
            ZStack {
                if let preview = session.preview { Image(preview, scale: 1, label: Text("Edited photo preview")).resizable().aspectRatio(contentMode: .fit) }
                if session.busy { ProgressView() }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            VStack(alignment: .leading, spacing: 18) {
                Text("Celluloid").font(.title)
                Picker("Filter", selection: $session.preset) {
                    ForEach(FilterPreset.allCases, id: \.rawValue) { filter in
                        Text(filter == .original && session.isBakedBase ? NSLocalizedString("Starting image", comment: "Photos fallback") : filter.localizedTitle).tag(filter)
                    }
                }.accessibilityIdentifier("photos-extension.filter")
                if session.preset == .pixellateFace { Text("Face detection can miss faces. Check the result before sharing.").font(.caption) }
                if session.isBakedBase { Text("The starting image is preserved as provided by Photos. Previous layers cannot be restored here.").font(.callout) }
                Text("This native Photos extension currently edits filters. Use the Celluloid document app for stickers, bubbles and collages.").font(.callout)
                if let error = session.error { Text(error).foregroundStyle(.red) }
                Spacer()
            }.frame(width: 260)
        }.padding(20).frame(minWidth: 640, minHeight: 440)
            .onChange(of: session.preset) { _ in session.render() }
    }
}
