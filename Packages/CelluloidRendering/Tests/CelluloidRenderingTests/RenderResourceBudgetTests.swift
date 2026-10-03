import XCTest
import CoreGraphics
import CelluloidDomain
@testable import CelluloidRendering
#if os(macOS)
import Darwin
#endif

final class RenderResourceBudgetTests: XCTestCase {
    private func fixture(width: Int, height: Int, value: CGFloat) throws -> Data {
        try autoreleasepool {
            let context = try RasterCodec.bitmap(width: width, height: height)
            context.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [value, 0.3, 1-value, 1])))
            context.fill(CGRect(x: 0, y: 0, width: width, height: height))
            return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
        }
    }
    func testConcurrentDocumentsUseOneRasterJobAndKeepDistinctResults() async throws {
        let queue = NativeRenderQueue()
        let inputs = try (0..<12).map { index -> (EditRecipe, [UUID: Data]) in
            let data = try fixture(width: 80 + index, height: 60, value: CGFloat(index) / 12)
            let source = try RasterCodec.metadata(data)
            var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 80 + index; recipe.canvasHeight = 60
            return (recipe, [source.id: data])
        }
        let dimensions = try await withThrowingTaskGroup(of: Int.self) { group in
            for (recipe, data) in inputs { group.addTask { try await queue.preview(recipe, sources: data).width } }
            var widths: [Int] = []
            for try await width in group { widths.append(width) }
            return widths.sorted()
        }
        XCTAssertEqual(dimensions, Array(80..<92))
        let maximum = await queue.maximumConcurrentRasterJobs
        let completed = await queue.completedJobs
        XCTAssertEqual(maximum, 1); XCTAssertEqual(completed, 12)
    }
    func testFourMaximumPixelSourcesHaveBoundedPreviewMemory() async throws {
        #if os(macOS)
        let data = try fixture(width: 8000, height: 6000, value: 0.7)
        var recipe = EditRecipe(); var originals: [UUID: Data] = [:]
        for index in 0..<4 {
            var source = try RasterCodec.metadata(data, name: "Synthetic \(index)")
            source.crop.zoom = 5
            recipe.sources.append(source); originals[source.id] = data
        }
        recipe.collageTemplate = try NativeResources.templates(count: 4).first!.assetName
        let queue = NativeRenderQueue()
        var firstPeak: Int64 = 0
        for iteration in 0..<3 {
            let image = try await queue.preview(recipe, sources: originals, maximumDimension: 600)
            XCTAssertEqual(image.width, 600); XCTAssertEqual(image.height, 600)
            var usage = rusage(); XCTAssertEqual(getrusage(RUSAGE_SELF, &usage), 0)
            let peak = Int64(usage.ru_maxrss)
            if iteration == 0 { firstPeak = peak }
            print("NATIVE_RENDER_MEMORY iteration=\(iteration) sources=4 source_pixels=48000000 zoom=5 preview=600 peak_resident_bytes=\(peak)")
            XCTAssertLessThan(peak, 1_500_000_000, "Maximum-size preview exceeded the practical process memory gate")
            XCTAssertLessThanOrEqual(peak - firstPeak, 256 * 1024 * 1024, "Repeated preview retained excessive additional memory")
        }
        #else
        throw XCTSkip("Peak-resident process measurement is currently a macOS gate")
        #endif
    }
}
