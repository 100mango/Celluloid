import XCTest
import UIKit
import CoreImage
@testable import CelluloidKit

@MainActor
final class AsyncImagePipelineTests: XCTestCase {
    private func fixture(width: Int = 120, height: Int = 80) -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format).image { context in
            for x in 0..<width {
                UIColor(red: CGFloat(x) / CGFloat(width), green: 0.3, blue: 0.8, alpha: 1).setFill()
                context.fill(CGRect(x: x, y: 0, width: 1, height: height))
            }
        }
    }
    private func pixels(_ image: UIImage) throws -> [UInt8] {
        let cg = try XCTUnwrap(image.cgImage)
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: cg.width, height: cg.height, bitsPerComponent: 8,
                                           bytesPerRow: cg.width * 4, space: space,
                                           bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        bitmap.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        return Array(UnsafeBufferPointer(start: try XCTUnwrap(bitmap.data).assumingMemoryBound(to: UInt8.self), count: cg.width * cg.height * 4))
    }

    func testAsyncFiltersKeepLegacyPixelsAndOrientationBelowPreviewLimit() async throws {
        let image = fixture(), pipeline = LegacyFilterPreviewPipeline()
        for orientation in [UIImage.Orientation.up, .down, .left, .right, .upMirrored, .downMirrored, .leftMirrored, .rightMirrored] {
            let source = UIImage(cgImage: try XCTUnwrap(image.cgImage), scale: 2, orientation: orientation)
            for filter in [FilterType.Original, .Sepia, .Chrome, .Fade, .Invert, .Posterize, .Sketch, .Comic, .Crystal, .PixellateFace] {
                let result = try await pipeline.image(source: source, filter: filter)
                let expected = source.filteredImage(Filters.filter(filter))
                XCTAssertEqual(result.size, expected.size)
                XCTAssertEqual(result.scale, expected.scale)
                XCTAssertEqual(result.imageOrientation, expected.imageOrientation)
                let actualPixels = try pixels(result), expectedPixels = try pixels(expected)
                XCTAssertEqual(actualPixels.count, expectedPixels.count)
                let maximum = zip(actualPixels, expectedPixels).map { abs(Int($0) - Int($1)) }.max() ?? 0
                XCTAssertLessThanOrEqual(maximum, 2, "\(filter), \(orientation)")
            }
        }
    }

    func testBoundedPreviewRetainsLogicalCanvasAndOriginalSource() async throws {
        let original = fixture(width: 1200, height: 800)
        let source = UIImage(cgImage: try XCTUnwrap(original.cgImage), scale: 2, orientation: .left)
        let result = try await LegacyFilterPreviewPipeline().image(source: source, filter: .Sepia, maximumDimension: 300)
        XCTAssertEqual(max(try XCTUnwrap(result.cgImage).width, try XCTUnwrap(result.cgImage).height), 300)
        XCTAssertEqual(result.size, source.size)
        XCTAssertEqual(source.cgImage?.width, 1200)
        XCTAssertEqual(source.cgImage?.height, 800)
    }

    func testExactCompatibilityPreviewPreservesOddSizedCanvas() async throws {
        let original = fixture(width: 2049, height: 1365)
        let source = UIImage(cgImage: try XCTUnwrap(original.cgImage), scale: 2, orientation: .right)
        let result = try await LegacyFilterPreviewPipeline().image(source: source, filter: .Invert, maximumDimension: nil)
        XCTAssertEqual(result.cgImage?.width, 2049)
        XCTAssertEqual(result.cgImage?.height, 1365)
        XCTAssertEqual(result.size, source.size)
        XCTAssertEqual(result.scale, source.scale)
        XCTAssertEqual(result.imageOrientation, source.imageOrientation)
        XCTAssertEqual(try pixels(result), try pixels(source.filteredImage(Filters.filter(.Invert))))
    }

    func testSourceReplacementAndOriginalCancelSupersededPreview() async throws {
        let editor = BaseEditPhotoController()
        editor.sourceImage = fixture(width: 1200, height: 800)
        var filtered = AdjustmentData(); filtered.filterType = .Sketch
        editor.restoreFromData(filtered)
        let replacement = fixture(width: 120, height: 80)
        editor.input = nil
        editor.sourceImage = replacement
        XCTAssertTrue(editor.preview.image === replacement)
        // Drain the same serial image executor through a new independent job.
        _ = try await LegacyFilterPreviewPipeline().image(source: replacement, filter: .Sepia)
        XCTAssertTrue(editor.preview.image === replacement, "Old completion replaced a new input session")
        XCTAssertFalse(editor.isPreviewRendering)
    }

    func testStandaloneExportServiceUsesFullOriginalAndSnapshot() async throws {
        let source = fixture(width: 600, height: 400)
        let service = PhotoExportService()
        var snapshot = AdjustmentData(); snapshot.filterType = .Sepia
        let result: Result<PhotoExport, PhotoExportError> = await withCheckedContinuation { continuation in
            service.export(snapshot: snapshot, source: .importedCopy(source), isReadOnly: false) {
                continuation.resume(returning: $0)
            }
        }
        withExtendedLifetime(service) {}
        let output = try result.get()
        XCTAssertEqual(output.image.cgImage?.width, 600)
        XCTAssertEqual(output.image.cgImage?.height, 400)
        XCTAssertEqual(try AdjustmentData.decode(output.adjustmentData).filterType, .Sepia)
        XCTAssertFalse(output.jpegData.isEmpty)
    }

    func testExportRejectsOpaqueStateAndMissingPhotosOriginal() async {
        let service = PhotoExportService()
        for readOnly in [true, false] {
            let result: Result<PhotoExport, PhotoExportError> = await withCheckedContinuation { continuation in
                service.export(snapshot: AdjustmentData(), source: .photosOriginal(url: nil, orientation: 1), isReadOnly: readOnly) {
                    continuation.resume(returning: $0)
                }
            }
            switch result {
            case .success: XCTFail("Read-only/missing original export succeeded")
            case .failure(let error):
                switch (readOnly, error) {
                case (true, .invalidState), (false, .missingImage): break
                default: XCTFail("Unexpected failure \(error)")
                }
            }
        }
        withExtendedLifetime(service) {}
    }
}
