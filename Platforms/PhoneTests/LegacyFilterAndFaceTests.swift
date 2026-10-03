import XCTest
import UIKit
import CoreImage
import CryptoKit
import ImageIO
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
        let cg = try XCTUnwrap(bitmap.makeImage()), image = UIImage(cgImage: cg)
        let sourceBytes = try RasterCodec.encode(cg, as: .png), source = try RasterCodec.metadata(sourceBytes)
        for row in rows {
            let data = try XCTUnwrap(Data(base64Encoded: row.base64))
            XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), row.sha256)
            let decoded = try AdjustmentData.decode(data)
            XCTAssertEqual(decoded.filterType.rawValue, row.filter); XCTAssertTrue(decoded.bubbles.isEmpty); XCTAssertTrue(decoded.stickers.isEmpty)
            XCTAssertNil(decoded.referenceCanvasSize)
            let rendered = image.filteredImage(Filters.filter(decoded.filterType))
            XCTAssertEqual(rendered.cgImage?.width, 120); XCTAssertEqual(rendered.cgImage?.height, 80)
            var nativeRecipe = EditRecipe(); nativeRecipe.sources = [source]; nativeRecipe.canvasWidth = 120; nativeRecipe.canvasHeight = 80
            nativeRecipe.filter = try XCTUnwrap(FilterPreset(rawValue: row.filter))
            let native = try RecipeRenderer().render(nativeRecipe, sources: [source.id:sourceBytes])
            let bounds = CGRect(x:0,y:0,width:120,height:80), context = CIContext()
            let difference = maximumDelta(pixels(CIImage(cgImage:try XCTUnwrap(rendered.cgImage)),bounds,context), pixels(CIImage(cgImage:native),bounds,context))
            print("MAC_NEW_FILTER_UIKIT_PIXELS filter=\(row.filter) maximumChannelDifference=\(difference)")
            if difference > 2 {
                try diagnoseInputPaths(data:sourceBytes,preset:nativeRecipe.filter,uiCG:cg,legacy:try XCTUnwrap(rendered.cgImage),tag:row.filter)
                let input = try RasterCodec.image(sourceBytes)
                let graph = try RecipeRenderer().apply(nativeRecipe.filter,to:input)
                diagnoseMaterialization(graph:graph,legacy:try XCTUnwrap(rendered.cgImage),native:native,tag:row.filter)
                let decoded = try XCTUnwrap(UIImage(data:sourceBytes))
                let sameEncodedLegacy = try XCTUnwrap(decoded.filteredImage(Filters.filter(decodedFilter(row.filter))).cgImage)
                print("NATIVE_MATERIALIZATION sameEncodedUIKit filter=\(row.filter) max=\(maximumDelta(pixels(CIImage(cgImage:sameEncodedLegacy),bounds,context),pixels(CIImage(cgImage:native),bounds,context)))")
            }
            XCTAssertLessThanOrEqual(difference,2,"New native filter archive must mean the same rendered edit to UIKit")
            XCTAssertEqual(try AdjustmentData.decode(decoded.encode()).filterType.rawValue, row.filter)
        }
        print("MAC_NEW_FILTER_UIKIT_ROUNDTRIP completed newly authored archive decode/render/reencode comparisons; XCTest assertions determine equivalence")
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
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("PublicFaceFixture.original")
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
        let nativeInput = try RasterCodec.image(data)
        let nativeFaces = detector.features(in: nativeInput).map(\.bounds)
        var originalRecipe = recipe; originalRecipe.filter = .original
        let nativeOriginal = try RecipeRenderer().render(originalRecipe, sources: [source.id:data])
        let legacyOriginal = try XCTUnwrap(original.filteredImage(Filters.filter(.Original)).cgImage)
        let inputDelta = maximumDelta(pixels(input,input.extent,context), pixels(nativeInput,input.extent,context))
        let baselineDelta = maximumDelta(pixels(CIImage(cgImage:legacyOriginal),input.extent,context),pixels(CIImage(cgImage:nativeOriginal),input.extent,context))
        let sameInputGraph = try RecipeRenderer().apply(.pixellateFace, to: input)
        let legacyGraph = Filters.filter(.PixellateFace)(input)
        let sameInputDelta = maximumDelta(pixels(legacyGraph,input.extent,context),pixels(sameInputGraph,input.extent,context))
        print("FACE_DETECTOR_ACTUAL_DIAGNOSTICS UIImageSpace=\(cg.colorSpace?.name as String? ?? "nil") nativeInputSpace=\(nativeInput.colorSpace?.name as String? ?? "nil") inputDelta=\(inputDelta) originalRenderDelta=\(baselineDelta) sameInputMaskGraphDelta=\(sameInputDelta) UIKitFaces=\(faces) nativeFaces=\(nativeFaces)")
        XCTAssertLessThanOrEqual(sameInputDelta,2,"Mask graph equivalence on identical decoded input")
        let expected = pixels(CIImage(cgImage: legacy), input.extent, context)
        let actual = pixels(CIImage(cgImage: native), input.extent, context)
        let actualDelta = maximumDelta(expected,actual)
        print("FACE_DETECTOR_ACTUAL_OUTPUT maximumChannelDifference=\(actualDelta)")
        try diagnoseInputPaths(data:data,preset:.pixellateFace,uiCG:cg,legacy:legacy,tag:"portrait")
        diagnoseMaterialization(graph:try RecipeRenderer().apply(.pixellateFace,to:nativeInput),legacy:legacy,native:native,tag:"portrait")
        XCTAssertLessThanOrEqual(actualDelta, 2)
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
                    let before = pixels(input,rect,context), after = pixels(CIImage(cgImage:native),rect,context)
                    let legacyOutside = pixels(CIImage(cgImage:legacy),rect,context)
                    if before != after { print("FACE_DETECTOR_ACTUAL_OUTSIDE_PATHS regionX=\(x) regionY=\(y) legacyVersusInput=\(maximumDelta(before,legacyOutside)) nativeVersusInput=\(maximumDelta(before,after)) nativeVersusLegacy=\(maximumDelta(legacyOutside,after))") }
                    if before != after {
                        let changed = stride(from:0,to:before.count,by:4).filter { Array(before[$0..<$0+4]) != Array(after[$0..<$0+4]) }.prefix(4)
                        for offset in changed { print("FACE_DETECTOR_ACTUAL_OUTSIDE regionX=\(x) regionY=\(y) storageColumn=\((offset/4)%8) storageRow=\((offset/4)/8) original=\(Array(before[offset..<offset+4])) native=\(Array(after[offset..<offset+4]))") }
                    }
                    XCTAssertEqual(before,after,"Outside region x=\(x) y=\(y)");outsideChecks += 1
                }
            }
        }
        XCTAssertGreaterThan(outsideChecks,0)
        print("FACE_DETECTOR_ACTUAL detected=\(faces.count) outsideRegions=\(outsideChecks) measuredDelta=\(actualDelta) requiredMaximum=2; assertions determine pass/fail; no anonymization guarantee")
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
    private func decodedFilter(_ raw: String) -> FilterType { FilterType(rawValue:raw)! }
    /// Diagnostic only: none of these variants replace the strict production oracle.
    private func diagnoseInputPaths(data:Data,preset:FilterPreset,uiCG:CGImage,legacy:CGImage,tag:String) throws {
        let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData,nil))
        let decoded = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source,0,[kCGImageSourceShouldCache:false] as CFDictionary))
        let ui = CIImage(cgImage:uiCG), read = CIContext(), bounds = ui.extent
        let variants:[(String,CIImage)] = [("UIImageCG",ui),("ImageIOCG",CIImage(cgImage:decoded)),("CIData",try RasterCodec.image(data))]
        func floats(_ image:CIImage)->[Float] {
            var result=[Float](repeating:0,count:Int(bounds.width*bounds.height)*4)
            result.withUnsafeMutableBytes { read.render(image,toBitmap:$0.baseAddress!,rowBytes:Int(bounds.width)*16,bounds:bounds,format:.RGBAf,colorSpace:RasterCodec.colorSpace) }
            return result
        }
        let expectedInput=floats(ui),expected=pixels(CIImage(cgImage:legacy),bounds,read)
        let originalLegacyGraph=Filters.filter(decodedFilter(preset.rawValue))(ui)
        let expectedGraph=floats(originalLegacyGraph)
        for (name,input) in variants {
            let values=floats(input),floatDelta=zip(values,expectedInput).map {abs($0-$1)}.max() ?? 0
            let graph=try RecipeRenderer().apply(preset,to:input),graphValues=floats(graph)
            let graphDelta=zip(graphValues,expectedGraph).map {abs($0-$1)}.max() ?? 0
            let nativeCG=try XCTUnwrap(read.createCGImage(graph,from:bounds))
            let legacyGraph=Filters.filter(decodedFilter(preset.rawValue))(input)
            let legacyCG=try XCTUnwrap(read.createCGImage(legacyGraph,from:bounds))
            print("NATIVE_INPUT_PRECISION tag=\(tag) source=\(name) inputFloatMax=\(floatDelta) graphFloatMax=\(graphDelta) nativeGraphCGMax=\(maximumDelta(expected,pixels(CIImage(cgImage:nativeCG),bounds,read))) legacyGraphCGMax=\(maximumDelta(expected,pixels(CIImage(cgImage:legacyCG),bounds,read)))")
            let offsets=values.indices.filter {values[$0] != expectedInput[$0]}.prefix(4)
            for offset in offsets { print("NATIVE_INPUT_PRECISION_SAMPLE tag=\(tag) source=\(name) offset=\(offset) expected=\(expectedInput[offset]) actual=\(values[offset])") }
        }
    }
    private func diagnoseMaterialization(graph: CIImage, legacy: CGImage, native: CGImage, tag: String) {
        let bounds = graph.extent, read = CIContext()
        let expected = pixels(CIImage(cgImage:legacy),bounds,read)
        print("NATIVE_MATERIALIZATION tag=\(tag) legacyAlpha=\(legacy.alphaInfo.rawValue) nativeAlpha=\(native.alphaInfo.rawValue) legacyBits=\(legacy.bitsPerComponent)/\(legacy.bitsPerPixel) nativeBits=\(native.bitsPerComponent)/\(native.bitsPerPixel) legacyBitmap=\(legacy.bitmapInfo.rawValue) nativeBitmap=\(native.bitmapInfo.rawValue)")
        let contexts: [(String,[CIContextOption:Any])] = [("default",[:]),("cacheOff",[.cacheIntermediates:false]),("native",[.outputColorSpace:RasterCodec.colorSpace,.cacheIntermediates:false])]
        for (label,options) in contexts {
            let materializer = CIContext(options:options)
            for explicit in [false,true] {
                for identityAndCrop in [false,true] {
                    let candidate = identityAndCrop ? graph.transformed(by:.identity).cropped(to:bounds) : graph
                    let rendered = explicit ? materializer.createCGImage(candidate,from:bounds,format:.RGBA8,colorSpace:RasterCodec.colorSpace) : materializer.createCGImage(candidate,from:bounds)
                    guard let rendered else { XCTFail("Diagnostic materialization failed"); continue }
                    let raw = pixels(CIImage(cgImage:rendered),bounds,read)
                    print("NATIVE_MATERIALIZATION tag=\(tag) context=\(label) explicit=\(explicit) identityCrop=\(identityAndCrop) directMax=\(maximumDelta(expected,raw)) alpha=\(rendered.alphaInfo.rawValue) bits=\(rendered.bitsPerComponent) bitmap=\(rendered.bitmapInfo.rawValue)")
                    if label == "native" && explicit && identityAndCrop {
                        for quality in [CGInterpolationQuality.none,.high] {
                            guard let canvas = try? RasterCodec.bitmap(width:legacy.width,height:legacy.height) else { continue }
                            canvas.interpolationQuality = quality; canvas.draw(rendered,in:bounds)
                            if let result = canvas.makeImage() { print("NATIVE_MATERIALIZATION tag=\(tag) canvasQuality=\(quality.rawValue) max=\(maximumDelta(expected,pixels(CIImage(cgImage:result),bounds,read)))") }
                        }
                    }
                }
            }
            materializer.clearCaches()
        }
        for background in [Optional<CGFloat>.none,0,1] {
            func normalized(_ image:CGImage) -> [UInt8] {
                let c = try! RasterCodec.bitmap(width:image.width,height:image.height)
                if let gray = background { c.setFillColor(CGColor(gray:gray,alpha:1));c.fill(bounds) }
                c.draw(image,in:bounds)
                return Array(UnsafeBufferPointer(start:c.data!.assumingMemoryBound(to:UInt8.self),count:image.width*image.height*4))
            }
            print("NATIVE_MATERIALIZATION tag=\(tag) CGContextBackground=\(background.map { String(describing:$0) } ?? "transparent") max=\(maximumDelta(normalized(legacy),normalized(native)))")
        }
    }
    private func maximumDelta(_ lhs: [UInt8], _ rhs: [UInt8]) -> Int {
        zip(lhs,rhs).map { abs(Int($0)-Int($1)) }.max() ?? 0
    }
    private struct Fixture: Decodable { let filter: String; let sha256: String; let base64: String }
    private func pixels(_ image: CIImage, _ bounds: CGRect, _ context: CIContext) -> [UInt8] {
        var data=[UInt8](repeating:0,count:Int(bounds.width*bounds.height)*4)
        data.withUnsafeMutableBytes { context.render(image,toBitmap:$0.baseAddress!,rowBytes:Int(bounds.width)*4,bounds:bounds,format:.RGBA8,colorSpace:RasterCodec.colorSpace) }
        return data
    }
}
