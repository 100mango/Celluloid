import XCTest
import UIKit
import CoreImage
import CryptoKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidPhoneCompanion

/// Uses the original, unmodified UIKit Filters and AdjustmentData source in this validation host.
final class LegacyFilterAndFaceTests: XCTestCase {
    func testActuallyMacAuthoredFilterArchivesDecodeAndRenderThroughUIKit() throws {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("mac-filter-fixtures.json")
        let rows = try JSONDecoder().decode([Fixture].self, from: Data(contentsOf: url))
        XCTAssertEqual(Set(rows.map(\.filter)), Set(FilterPreset.allCases.map(\.rawValue)))
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        for x in 0..<120 { bitmap.setFillColor(CGColor(srgbRed: CGFloat(x)/119, green: 0.4, blue: 0.8, alpha: 1)); bitmap.fill(CGRect(x: x,y: 0,width: 1,height: 80)) }
        let image = UIImage(cgImage: try XCTUnwrap(bitmap.makeImage()))
        for row in rows {
            let data = try XCTUnwrap(Data(base64Encoded: row.base64))
            XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), row.sha256)
            let decoded = try AdjustmentData.decode(data)
            XCTAssertEqual(decoded.filterType.rawValue, row.filter); XCTAssertTrue(decoded.bubbles.isEmpty); XCTAssertTrue(decoded.stickers.isEmpty)
            XCTAssertNil(decoded.referenceCanvasSize)
            let rendered = image.filteredImage(Filters.filter(decoded.filterType))
            XCTAssertEqual(rendered.cgImage?.width, 120); XCTAssertEqual(rendered.cgImage?.height, 80)
            XCTAssertEqual(try AdjustmentData.decode(decoded.encode()).filterType.rawValue, row.filter)
        }
        print("MAC_NEW_FILTER_UIKIT_ROUNDTRIP all newly authored filter-only archives decoded/rendered/reencoded by original UIKit source")
    }
    func testMacBakedFallbackIsDeclinedByOriginalUIKitReader() throws {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("mac-baked-filter-fixture.json")
        let row = try JSONDecoder().decode(BakedFixture.self, from: Data(contentsOf: url))
        let data = try XCTUnwrap(Data(base64Encoded: row.base64))
        XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), row.sha256)
        XCTAssertEqual(row.identifier, AdjustmentData.formatIdentifier)
        XCTAssertEqual(row.version, "2.0-baked-base")
        XCTAssertFalse(AdjustmentData.supportIdentifier(row.identifier, version: row.version),
                       "Original UIKit must request Photos' baked appearance, never replay a partial edit on the original")
        print("MAC_BAKED_BASE_DECLINED_BY_UIKIT exact newly authored Mac discriminator keeps old reader on Photos-rendered fallback")
    }
    private struct BakedFixture: Decodable { let identifier: String; let version: String; let sha256: String; let base64: String }
    func testRealFaceDetectorNativeRenderMatchesOriginalUIKitPath() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "OriginalFilter", withExtension: "png"))
        let data = try Data(contentsOf: url)
        XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), "378e569e25716ffc36c3e7622708ae1fab41ce99c870ae02f5874bb8aec45bfb")
        let original = try XCTUnwrap(UIImage(data: data)), cg = try XCTUnwrap(original.cgImage)
        let input = CIImage(cgImage: cg), context = CIContext()
        let detector = try XCTUnwrap(CIDetector(ofType: CIDetectorTypeFace, context: context, options: [CIDetectorAccuracy:CIDetectorAccuracyHigh]))
        let faces = detector.features(in: input).map(\.bounds)
        XCTAssertFalse(faces.isEmpty, "The genuine detector must find a face in the existing public bundled fixture")
        let legacy = try XCTUnwrap(original.filteredImage(Filters.filter(.PixellateFace)).cgImage)
        let source = try RasterCodec.metadata(data)
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = source.pixelWidth; recipe.canvasHeight = source.pixelHeight; recipe.filter = .pixellateFace
        let native = try RecipeRenderer().render(recipe, sources: [source.id:data])
        let expected = pixels(CIImage(cgImage: legacy), input.extent, context)
        let actual = pixels(CIImage(cgImage: native), input.extent, context)
        XCTAssertLessThanOrEqual(zip(expected,actual).map { abs(Int($0)-Int($1)) }.max() ?? 0, 2)
        for face in faces {
            let inside = CGRect(x: floor(face.midX)-4,y: floor(face.midY)-4,width: 8,height: 8)
            XCTAssertTrue(pixels(input,inside,context) != pixels(CIImage(cgImage:native),inside,context))
        }
        var outsideChecks = 0
        for x in stride(from: 0, to: Int(input.extent.width)-8, by: 20) {
            for y in stride(from: 0, to: Int(input.extent.height)-8, by: 20) {
                let center = CGPoint(x:x+4,y:y+4)
                if faces.allSatisfy({ hypot(center.x-$0.midX,center.y-$0.midY)>min($0.width,$0.height/1.5)+10 }) {
                    let rect=CGRect(x:x,y:y,width:8,height:8)
                    XCTAssertTrue(pixels(input,rect,context) == pixels(CIImage(cgImage:native),rect,context));outsideChecks += 1
                }
            }
        }
        XCTAssertGreaterThan(outsideChecks,0)
        print("FACE_DETECTOR_ACTUAL detected=\(faces.count) outsideRegions=\(outsideChecks) UIKit/native max2-level oracle; no anonymization guarantee")
    }
    func testGenuineDetectorNoFacePreservesBlankImage() throws {
        let context = CIContext(), input = CIImage(color: CIColor(red: 0.2,green: 0.4,blue: 0.8)).cropped(to: CGRect(x: 0,y: 0,width: 128,height: 96))
        let detector = try XCTUnwrap(CIDetector(ofType: CIDetectorTypeFace,context:context,options:[CIDetectorAccuracy:CIDetectorAccuracyHigh]))
        XCTAssertTrue(detector.features(in: input).isEmpty)
        let sourceImage = try XCTUnwrap(context.createCGImage(input,from:input.extent))
        let data = try RasterCodec.encode(sourceImage,as:.png), source = try RasterCodec.metadata(data)
        var recipe = EditRecipe();recipe.sources=[source];recipe.canvasWidth=128;recipe.canvasHeight=96;recipe.filter = .pixellateFace
        let native = try RecipeRenderer().render(recipe,sources:[source.id:data])
        let legacy = try XCTUnwrap(UIImage(cgImage:sourceImage).filteredImage(Filters.filter(.PixellateFace)).cgImage)
        XCTAssertTrue(pixels(CIImage(cgImage:sourceImage),input.extent,context) == pixels(CIImage(cgImage:native),input.extent,context))
        XCTAssertTrue(pixels(CIImage(cgImage:legacy),input.extent,context) == pixels(CIImage(cgImage:native),input.extent,context))
    }
    private struct Fixture: Decodable { let filter: String; let sha256: String; let base64: String }
    private func pixels(_ image: CIImage, _ bounds: CGRect, _ context: CIContext) -> [UInt8] {
        var data=[UInt8](repeating:0,count:Int(bounds.width*bounds.height)*4)
        data.withUnsafeMutableBytes { context.render(image,toBitmap:$0.baseAddress!,rowBytes:Int(bounds.width)*4,bounds:bounds,format:.RGBA8,colorSpace:RasterCodec.colorSpace) }
        return data
    }
}
