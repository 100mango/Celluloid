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
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Native photo editor")
        #if os(macOS)
        .background(NativeWindowAccessibility().frame(width: 0, height: 0))
        #endif
        #if os(macOS) && DEBUG
        .overlay(alignment: .bottomLeading) {
            if SandboxDiagnostics.enabled {
                Text(verbatim: SandboxDiagnostics.report).font(.system(size: 8)).lineLimit(1)
                    .padding(2).background(Color.yellow).accessibilityElement(children: .ignore)
                    .accessibilityLabel(SandboxDiagnostics.report).accessibilityIdentifier("sandbox.probe")
            }
        }
        #endif
        .toolbar {
            ToolbarItemGroup {
                Button { filePicker = true } label: { Label("Import Files", systemImage: "photo.on.rectangle") }
                    .help("Choose one photo, or two to four photos for a collage").accessibilityIdentifier("editor.import-files")
                PhotosPicker(selection: $photos, maxSelectionCount: 4, selectionBehavior: .ordered, matching: .images, preferredItemEncoding: .current) {
                    Label("Photos", systemImage: "photo")
                }.accessibilityIdentifier("editor.import-photos")
                #if os(macOS)
                Button(action: paste) { Label("Paste", systemImage: "doc.on.clipboard") }.keyboardShortcut("v", modifiers: .command)
                #endif
                Menu("Export") {
                    Button("PNG…") { prepareExport(.png) }
                    Button("JPEG…") { prepareExport(.jpeg) }
                }.accessibilityIdentifier("editor.export").disabled(document.recipe.sources.isEmpty || rendering || importing || exporting)
            }
        }
        .fileImporter(isPresented: $filePicker, allowedContentTypes: [.image], allowsMultipleSelection: true, onCompletion: importFiles)
        .fileExporter(isPresented: $exportPicker, document: exported, contentType: exportType,
                      defaultFilename: "Celluloid", onCompletion: verifyExport)
        .onChange(of: photos) { items in importPhotos(items) }
        .task(id: try? document.recipe.encoded()) { await renderPreview() }
        .onAppear {
            undo.apply = { document = $0 }
            undo.historyTrimmed = { status = NSLocalizedString("Older undo history cleared to limit memory; the last import can still be undone.", comment: "Editor message") }
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
                    Image(preview, scale: 1, label: Text("Edited photo preview")).resizable().aspectRatio(contentMode: .fit)
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
                Text(verbatim: document.recipe.sources.isEmpty ? NSLocalizedString("No photos imported", comment: "Empty editor") : "\(document.recipe.canvasWidth) × \(document.recipe.canvasHeight) px").accessibilityIdentifier("editor.dimensions")
                Spacer()
                Text(status).accessibilityIdentifier("editor.status")
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
            status = String(format: NSLocalizedString("Imported %d photo(s)", comment: "Import status"), items.count); apply(next, name: "Import Photos")
        } catch { self.error = error.localizedDescription }
    }
    private func importFiles(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard (1...4).contains(urls.count) else { error = NSLocalizedString("Choose between one and four images.", comment: "Editor message"); return }
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
                    guard let file = try await item.loadTransferable(type: NativePickedFile.self) else { throw RenderError.invalidImage }
                    defer { file.owned.discard() }
                    try Task.checkCancellation()
                    let remaining = 64 * 1024 * 1024 - imported.reduce(0, { $0 + $1.1.count })
                    let data = try await NativeImportQueue.shared.read([file.owned.url], budget: remaining)[0].1
                    imported.append((String(format: NSLocalizedString("Photo %d", comment: "Imported photo name"), index + 1), data))
                }
                finishImport(imported, generation: generation)
            } catch { if generation == importGeneration { importing = false; self.error = error.localizedDescription } }
        }
    }
    private func drop(_ providers: [NSItemProvider]) -> Bool {
        guard (1...4).contains(providers.count) else { error = NSLocalizedString("Drop between one and four images.", comment: "Editor message"); return false }
        let generation = UUID(); importGeneration = generation; importing = true
        importTask?.cancel()
        importTask = Task {
            do {
                var items: [(String, Data)] = []
                for (index, provider) in providers.enumerated() {
                    try Task.checkCancellation()
                    let remaining = 64 * 1024 * 1024 - items.reduce(0, { $0 + $1.1.count })
                    let data = try await NativeProviderImport.read(provider, limit: remaining)
                    try Task.checkCancellation()
                    items.append((provider.suggestedName ?? String(format: NSLocalizedString("Dropped Photo %d", comment: "Dropped photo name"), index + 1), data))
                }
                finishImport(items, generation: generation)
            } catch { if generation == importGeneration { importing = false; self.error = error.localizedDescription } }
        }
        return true
    }
    #if os(macOS)
    private func paste() {
        let board = NSPasteboard.general
        if let urls = board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], !urls.isEmpty {
            importFiles(.success(urls)); return
        }
        guard let bytes = board.data(forType: .png) ?? board.data(forType: .tiff) else {
            error = NSLocalizedString("The clipboard does not contain an image.", comment: "Editor message"); return
        }
        importTask?.cancel()
        let generation = UUID(); importGeneration = generation
        finishImport([(NSLocalizedString("Pasted Photo", comment: "Pasted photo name"), bytes)], generation: generation)
    }
    #endif
    private func renderPreview() async {
        guard !document.recipe.sources.isEmpty else { preview = nil; rendering = false; return }
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
                guard snapshot.recipe == document.recipe else {
                    exporting = false
                    status = NSLocalizedString("Your edit changed. Export again to include the latest changes.", comment: "Export canceled after an edit")
                    return
                }
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
                let bytes = try NativeFileAccess.readImage(url, limit: 256 * 1024 * 1024)
                guard bytes == exported?.data else { throw RenderError.exportFailed }
                _ = try RasterCodec.metadata(bytes, maximumBytes: 256 * 1024 * 1024)
                status = String(format: NSLocalizedString("Exported and verified %@", comment: "Export status"), url.lastPathComponent)
            } catch { self.error = String(format: NSLocalizedString("The export was written, but could not be read back: %@", comment: "Export status"), error.localizedDescription) }
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
