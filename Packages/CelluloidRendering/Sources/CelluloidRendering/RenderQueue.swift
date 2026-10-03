import Foundation
import CoreGraphics
import UniformTypeIdentifiers
import CelluloidDomain

/// Process-wide serialization bounds simultaneous raster allocations across document windows.
/// This actor intentionally does not suspend inside one render. Canceled queued work checks
/// cancellation before allocating; superseded callers must also reject their stale result.
public actor NativeRenderQueue {
    public static let shared = NativeRenderQueue()
    public init() {}

    public func preview(_ recipe: EditRecipe, sources: [UUID: Data], maximumDimension: Int = 1400) throws -> CGImage {
        try Task.checkCancellation()
        let result = try RecipeRenderer().render(recipe, sources: sources, maximumDimension: maximumDimension)
        try Task.checkCancellation()
        return result
    }

    public func export(_ recipe: EditRecipe, sources: [UUID: Data], type: UTType) throws -> Data {
        try Task.checkCancellation()
        let image = try RecipeRenderer().render(recipe, sources: sources)
        try Task.checkCancellation()
        let data = try RasterCodec.encode(image, as: type)
        try Task.checkCancellation()
        return data
    }
}
