import Foundation
import SwiftUI
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

extension UTType {
    static let celluloidDocument = UTType(exportedAs: "Mango.Celluloid.document", conformingTo: .package)
}

struct NativeDocument: FileDocument, Equatable {
    static var readableContentTypes: [UTType] { [.celluloidDocument] }
    var recipe = EditRecipe()
    var originals: [UUID: Data] = [:]
    init() {}

    init(configuration: ReadConfiguration) throws { try self.init(wrapper: configuration.file) }

    init(wrapper: FileWrapper) throws {
        guard wrapper.isDirectory,
              let children = wrapper.fileWrappers,
              let manifest = children["recipe.json"], manifest.isRegularFile,
              ((manifest.fileAttributes[FileAttributeKey.size.rawValue] as? NSNumber)?.intValue ?? 0) <= 2_000_000,
              let data = manifest.regularFileContents else { throw RecipeError.invalidDocument }
        recipe = try EditRecipe.decode(data)
        guard children.count == recipe.sources.count + 1 else { throw RecipeError.invalidDocument }
        var total = 0
        for source in recipe.sources {
            guard let file = children[source.filename], file.isRegularFile,
                  ((file.fileAttributes[FileAttributeKey.size.rawValue] as? NSNumber)?.intValue ?? 0) <= RasterCodec.maxSourceBytes,
                  let bytes = file.regularFileContents else { throw RecipeError.missingSource }
            total += bytes.count
            guard total <= 64 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            let metadata = try RasterCodec.metadata(bytes)
            guard metadata.pixelWidth == source.pixelWidth, metadata.pixelHeight == source.pixelHeight else {
                throw RecipeError.invalidDocument
            }
            originals[source.id] = bytes
        }
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { try archive() }

    func archive() throws -> FileWrapper {
        guard originals.count == recipe.sources.count, originals.values.reduce(0, { $0 + $1.count }) <= 64 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        var files = ["recipe.json": FileWrapper(regularFileWithContents: try recipe.encoded())]
        for source in recipe.sources {
            guard let data = originals[source.id], data.count <= RasterCodec.maxSourceBytes else { throw RecipeError.missingSource }
            files[source.filename] = FileWrapper(regularFileWithContents: data)
        }
        return FileWrapper(directoryWithFileWrappers: files)
    }

    mutating func replaceSources(_ items: [(String, Data)]) throws {
        guard (1...4).contains(items.count), items.reduce(0, { $0 + $1.1.count }) <= 64 * 1024 * 1024 else { throw RecipeError.invalidDocument }
        var newRecipe = recipe
        let sources = try items.map { try RasterCodec.metadata($0.1, name: $0.0) }
        var bytes: [UUID: Data] = [:]
        for (source, item) in zip(sources, items) { bytes[source.id] = item.1 }
        newRecipe.sources = sources
        if sources.count == 1 {
            newRecipe.collageTemplate = nil
            newRecipe.canvasWidth = sources[0].pixelWidth; newRecipe.canvasHeight = sources[0].pixelHeight
        } else {
            newRecipe.collageTemplate = try NativeResources.templates(count: sources.count).first?.assetName
            newRecipe.canvasWidth = 800; newRecipe.canvasHeight = 800
        }
        try newRecipe.validate()
        recipe = newRecipe; originals = bytes
    }
}

/// One instance per document window. Native Undo/Redo replays the same validated value mutation.
@MainActor final class DocumentUndo: ObservableObject {
    var apply: ((NativeDocument) -> Void)?
    var historyTrimmed: (() -> Void)?
    private var retainedSources: [UUID: Int] = [:]
    private let maximumRetainedBytes: Int
    init(maximumRetainedBytes: Int = 128 * 1024 * 1024) { self.maximumRetainedBytes = maximumRetainedBytes }

    func change(from previous: NativeDocument, to next: NativeDocument, manager: UndoManager?, name: String) {
        guard previous != next else { return }
        manager?.levelsOfUndo = 20
        if manager?.isUndoing != true && manager?.isRedoing != true {
            var budget = retainedSources
            for (id, data) in previous.originals { budget[id] = data.count }
            for (id, data) in next.originals { budget[id] = data.count }
            if budget.values.reduce(0, +) > maximumRetainedBytes {
                manager?.removeAllActions(withTarget: self)
                budget = previous.originals.mapValues(\.count)
                for (id, data) in next.originals { budget[id] = data.count }
                historyTrimmed?()
            }
            retainedSources = budget
        }
        manager?.registerUndo(withTarget: self) { target in
            target.change(from: next, to: previous, manager: manager, name: name)
        }
        manager?.setActionName(NSLocalizedString(name, comment: "Undo action"))
        apply?(next)
    }
}
