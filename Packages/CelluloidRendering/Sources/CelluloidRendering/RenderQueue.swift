import Foundation
import CoreGraphics
import UniformTypeIdentifiers
import CelluloidDomain

/// Process-wide serialization bounds simultaneous raster allocations across document windows.
/// This actor intentionally does not suspend inside one render. Canceled queued work checks
/// cancellation before allocating; superseded callers must also reject their stale result.
public actor NativeRenderQueue {
    public static let shared = NativeRenderQueue()
    // Actor initializers run on the caller. Create CIContext only after the
    // first actor hop, never while a SwiftUI/MainActor model initializes shared.
    private var storedRenderer: RecipeRenderer?
    private var renderer: RecipeRenderer {
        if let storedRenderer { return storedRenderer }
        let renderer = RecipeRenderer()
        storedRenderer = renderer
        return renderer
    }
    public init() {}
    private var activeRasterJobs = 0
    private(set) var maximumConcurrentRasterJobs = 0
    private(set) var completedJobs = 0

    public func preview(_ recipe: EditRecipe, sources: [UUID: Data], maximumDimension: Int = 1400) throws -> CGImage {
        try Task.checkCancellation()
        beginJob(); defer { endJob() }
        let result = try autoreleasepool { try renderer.render(recipe, sources: sources, maximumDimension: maximumDimension) }
        try Task.checkCancellation()
        return result
    }

    public func export(_ recipe: EditRecipe, sources: [UUID: Data], type: UTType) throws -> Data {
        try Task.checkCancellation()
        beginJob(); defer { endJob() }
        let data = try autoreleasepool {
            let image = try renderer.render(recipe, sources: sources)
            try Task.checkCancellation()
            return try RasterCodec.encode(image, as: type)
        }
        try Task.checkCancellation()
        return data
    }
    private func beginJob() {
        activeRasterJobs += 1
        maximumConcurrentRasterJobs = max(maximumConcurrentRasterJobs, activeRasterJobs)
    }
    private func endJob() { activeRasterJobs -= 1; completedJobs += 1 }
}
