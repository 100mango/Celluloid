import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering
#if os(macOS)
import AppKit
#endif

struct EditorView: View {
    @Environment(\.undoManager) private var undoManager
    @Binding var document: NativeDocument
    @StateObject private var undo = DocumentUndo()
    @State private var photos: [PhotosPickerItem] = []
    @State private var selection: UUID?
    @State private var filePicker = false
    @State private var exportPicker = false
    @State private var exportType = UTType.png
    @State private var exported: RasterExport?
    @State private var preview: CGImage?
    @State private var rendering = false
    @State private var importing = false
    @State private var exporting = false
    @State private var error: String?
    @State private var status = ""
    @State private var importGeneration = UUID()
    @State private var importTask: Task<Void, Never>?
    @State private var exportTask: Task<Void, Never>?

    var body: some View {
        NativeEditorSplit {
            canvas.frame(minWidth: 320, maxWidth: .infinity, maxHeight: .infinity)
            EditorInspector(recipe: document.recipe, selection: $selection, change: changeRecipe)
                .frame(minWidth: 250, idealWidth: 290, maxWidth: 360)
        }
        .frame(minWidth: 640, minHeight: 480)
        .toolbar {
            ToolbarItemGroup {
                Button { filePicker = true } label: { Label("Import Files", systemImage: "photo.on.rectangle") }
                    .help("Choose one photo, or two to four photos for a collage")
                PhotosPicker(selection: $photos, maxSelectionCount: 4, selectionBehavior: .ordered, matching: .images) {
                    Label("Photos", systemImage: "photo")
                }
                #if os(macOS)
                Button(action: paste) { Label("Paste", systemImage: "doc.on.clipboard") }.keyboardShortcut("v", modifiers: .command)
                #endif
                Menu("Export") {
                    Button("PNG…") { prepareExport(.png) }
                    Button("JPEG…") { prepareExport(.jpeg) }
                }.disabled(document.recipe.sources.isEmpty || rendering || importing || exporting)
            }
        }
        .fileImporter(isPresented: $filePicker, allowedContentTypes: [.image], allowsMultipleSelection: true, onCompletion: importFiles)
        .fileExporter(isPresented: $exportPicker, document: exported, contentType: exportType,
                      defaultFilename: "Celluloid", onCompletion: verifyExport)
        .onChange(of: photos) { items in importPhotos(items) }
        .task(id: try? document.recipe.encoded()) { await renderPreview() }
        .onAppear {
            undo.apply = { document = $0 }
            undo.historyTrimmed = { status = "Older undo history cleared to limit memory; the last import can still be undone." }
        }
        .onDisappear { importGeneration = UUID(); importTask?.cancel(); exportTask?.cancel(); undo.apply = nil }
        .alert("Celluloid", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
            Button("OK", role: .cancel) { error = nil }
        } message: { Text(error ?? "") }
    }

    private var canvas: some View {
        VStack(spacing: 12) {
            ZStack {
                Rectangle().fill(Color.secondary.opacity(0.08))
                if let preview {
                    Image(decorative: preview, scale: 1).resizable().aspectRatio(contentMode: .fit)
                        .padding(16).accessibilityLabel("Edited photo preview")
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "photo.on.rectangle.angled").font(.system(size: 48))
                        Text("Start with your photos").font(.title2)
                        Text("Import one photo to edit, or 2–4 for a collage.\nYour originals stay in this editable document.")
                            .multilineTextAlignment(.center).foregroundStyle(.secondary)
                    }.padding(24)
                }
                if rendering || importing || exporting { ProgressView().padding().background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius: 10)) }
            }
            .onDrop(of: [.fileURL, .image], isTargeted: nil, perform: drop)
            .accessibilityIdentifier("editor.canvas")
            HStack {
                Text(document.recipe.sources.isEmpty ? "No photos imported" : "\(document.recipe.canvasWidth) × \(document.recipe.canvasHeight) px")
                Spacer()
                Text(status)
            }.font(.caption).foregroundStyle(.secondary).padding(.horizontal).padding(.bottom, 8)
        }
    }

    private func changeRecipe(_ next: EditRecipe, _ name: String) {
        var updated = document; updated.recipe = next
        let ids = Set(next.sources.map(\.id)); updated.originals = updated.originals.filter { ids.contains($0.key) }
        apply(updated, name: name)
    }
    private func apply(_ next: NativeDocument, name: String) {
        do {
            try next.recipe.validate()
            undo.apply = { document = $0 }
            undo.change(from: document, to: next, manager: undoManager, name: name)
        } catch { self.error = error.localizedDescription }
    }
    private func finishImport(_ items: [(String, Data)], generation: UUID) {
        guard generation == importGeneration else { return }
        defer { importing = false }
        do {
            var next = document; try next.replaceSources(items)
            status = "Imported \(items.count) photo(s)"; apply(next, name: "Import Photos")
        } catch { self.error = error.localizedDescription }
    }
    private func importFiles(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard (1...4).contains(urls.count) else { error = "Choose between one and four images."; return }
            let generation = UUID(); importGeneration = generation; importing = true
            importTask?.cancel()
            importTask = Task {
                do {
                    let items = try await NativeImportQueue.shared.read(urls)
                    try Task.checkCancellation()
                    finishImport(items, generation: generation)
                } catch { if generation == importGeneration { importing = false; self.error = error.localizedDescription } }
            }
        case .failure(let error):
            if (error as NSError).code != CocoaError.userCancelled.rawValue { self.error = error.localizedDescription }
        }
    }
    private func importPhotos(_ items: [PhotosPickerItem]) {
        guard !items.isEmpty else { return }
        let generation = UUID(); importGeneration = generation; importing = true
        importTask?.cancel()
        importTask = Task {
            do {
                var imported: [(String, Data)] = []
                for (index, item) in items.enumerated() {
                    try Task.checkCancellation()
                    guard let data = try await item.loadTransferable(type: Data.self) else { throw RenderError.invalidImage }
                    try Task.checkCancellation()
                    imported.append(("Photo \(index + 1)", data))
                }
                finishImport(imported, generation: generation)
            } catch { if generation == importGeneration { importing = false; self.error = error.localizedDescription } }
        }
    }
    nonisolated fileprivate static func readImage(_ url: URL, limit: Int = RasterCodec.maxSourceBytes) throws -> Data {
        let accessed = url.startAccessingSecurityScopedResource(); defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0, size <= limit else { throw RecipeError.resourceLimit }
        return try Data(contentsOf: url, options: .mappedIfSafe)
    }
    private func drop(_ providers: [NSItemProvider]) -> Bool {
        guard (1...4).contains(providers.count) else { error = "Drop between one and four images."; return false }
        let generation = UUID(); importGeneration = generation; importing = true
        importTask?.cancel()
        importTask = Task {
            do {
                var items: [(String, Data)] = []
                for (index, provider) in providers.enumerated() {
                    try Task.checkCancellation()
                    let data: Data
                    if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                        let urlData = try await loadData(provider, type: UTType.fileURL.identifier)
                        guard let url = URL(dataRepresentation: urlData, relativeTo: nil) else { throw RenderError.invalidImage }
                        data = try await NativeImportQueue.shared.read([url])[0].1
                    } else {
                        data = try await loadData(provider, type: UTType.image.identifier)
                    }
                    try Task.checkCancellation()
                    items.append((provider.suggestedName ?? "Dropped Photo \(index + 1)", data))
                }
                finishImport(items, generation: generation)
            } catch { if generation == importGeneration { importing = false; self.error = error.localizedDescription } }
        }
        return true
    }
    private func loadData(_ provider: NSItemProvider, type: String) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            provider.loadDataRepresentation(forTypeIdentifier: type) { data, error in
                if let data { continuation.resume(returning: data) }
                else { continuation.resume(throwing: error ?? RenderError.invalidImage) }
            }
        }
    }
    #if os(macOS)
    private func paste() {
        let board = NSPasteboard.general
        if let urls = board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], !urls.isEmpty {
            importFiles(.success(urls)); return
        }
        guard let image = NSImage(pasteboard: board), let bytes = image.tiffRepresentation else {
            error = "The clipboard does not contain an image."; return
        }
        importTask?.cancel()
        let generation = UUID(); importGeneration = generation
        finishImport([("Pasted Photo", bytes)], generation: generation)
    }
    #endif
    private func renderPreview() async {
        guard !document.recipe.sources.isEmpty else { preview = nil; return }
        rendering = true
        let snapshot = document
        do {
            let image = try await NativeRenderQueue.shared.preview(snapshot.recipe, sources: snapshot.originals)
            try Task.checkCancellation()
            preview = image; rendering = false
        } catch is CancellationError { }
        catch { if !Task.isCancelled { self.error = error.localizedDescription; rendering = false } }
    }
    private func prepareExport(_ type: UTType) {
        exporting = true; let snapshot = document
        exportTask?.cancel()
        exportTask = Task {
            do {
                let bytes = try await NativeRenderQueue.shared.export(snapshot.recipe, sources: snapshot.originals, type: type)
                try Task.checkCancellation()
                exported = RasterExport(data: bytes); exportType = type; exportPicker = true
                exporting = false
            } catch is CancellationError { exporting = false }
            catch { exporting = false; self.error = error.localizedDescription }
        }
    }
    private func verifyExport(_ result: Result<URL, Error>) {
        switch result {
        case .success(let url):
            do {
                let bytes = try Self.readImage(url, limit: 256 * 1024 * 1024)
                guard bytes == exported?.data else { throw RenderError.exportFailed }
                _ = try RasterCodec.metadata(bytes, maximumBytes: 256 * 1024 * 1024)
                status = "Exported and verified \(url.lastPathComponent)"
            } catch { self.error = "The export was written, but could not be read back: \(error.localizedDescription)" }
        case .failure(let error):
            if (error as NSError).code != CocoaError.userCancelled.rawValue { self.error = error.localizedDescription }
        }
    }
}

struct RasterExport: FileDocument {
    static var readableContentTypes: [UTType] { [.png, .jpeg] }
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws {
        guard let bytes = configuration.file.regularFileContents else { throw RenderError.invalidImage }
        data = bytes
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

private struct NativeEditorSplit<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        #if os(macOS)
        HSplitView(content: content)
        #else
        HStack(spacing: 0, content: content)
        #endif
    }
}

private actor NativeImportQueue {
    static let shared = NativeImportQueue()
    func read(_ urls: [URL]) throws -> [(String, Data)] {
        try urls.map { url in
            try Task.checkCancellation()
            return (url.lastPathComponent, try EditorView.readImage(url))
        }
    }
}
