import XCTest
import AppKit
import CryptoKit
import CoreGraphics
import CoreText
import ImageIO
import CelluloidDomain
import CelluloidRendering

final class MacPhotoAdjustmentTests: XCTestCase {
    func fixture(_ name: String) throws -> (Data, [String: Any]) {
        let bundle = Bundle(for: Self.self)
        let archive = try Data(contentsOf: XCTUnwrap(bundle.url(forResource: name, withExtension: "base64")))
        let data = try XCTUnwrap(Data(base64Encoded: archive, options: .ignoreUnknownCharacters))
        let expected = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: XCTUnwrap(bundle.url(forResource: name, withExtension: "json")))) as? [String: Any])
        XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), expected["sha256"] as? String)
        return (data, expected)
    }
    func testActualUIKitFixtureRetainsAllAffineAndBoundsComponents() throws {
        let (bytes, oracle) = try fixture("reference-canvas")
        let decoded = try MacPhotoAdjustment.decode(bytes)
        XCTAssertEqual(decoded.filter, .chrome); XCTAssertEqual(decoded.referenceCanvas, CGSize(width: 480, height: 640))
        XCTAssertEqual(decoded.bubbles.count, 1); XCTAssertEqual(decoded.stickers.count, 1)
        for (layer, key) in [(decoded.bubbles[0], "bubble"), (decoded.stickers[0], "sticker")] {
            let expected = try XCTUnwrap(oracle[key] as? [String: Any])
            XCTAssertEqual([layer.center.x, layer.center.y].map(Double.init), expected["center"] as? [Double])
            XCTAssertEqual([layer.bounds.origin.x, layer.bounds.origin.y, layer.bounds.width, layer.bounds.height].map(Double.init), expected["bounds"] as? [Double])
            let t = layer.transform
            XCTAssertEqual([t.a, t.b, t.c, t.d, t.tx, t.ty].map(Double.init), expected["transform"] as? [Double])
        }
        let roundtrip = try MacPhotoAdjustment.decode(decoded.encode())
        XCTAssertEqual(roundtrip.bubbles[0].text, "Hello, 世界 🎬")
        XCTAssertEqual(roundtrip.bubbles[0].transform, decoded.bubbles[0].transform)
        XCTAssertEqual(roundtrip.stickers[0].bounds, decoded.stickers[0].bounds)
    }
    func testHistoricalSchemaMissingCanvasIsDecodedButNeverMadeEditableOrRewritten() throws {
        let (bytes, _) = try fixture("legacy-points")
        let decoded = try MacPhotoAdjustment.decode(bytes)
        XCTAssertNil(decoded.referenceCanvas)
        XCTAssertEqual(decoded.bubbles[0].center, CGPoint(x: 240, y: 320))
        XCTAssertThrowsError(try decoded.requireEditableCanvas())
        XCTAssertThrowsError(try decoded.encode(), "An absent canvas must not be invented by the writer")
    }
    func testNewManufacturedValuesKeepUIKitTypesAndAllFields() throws {
        var adjustment = MacPhotoAdjustment(); adjustment.filter = .fade; adjustment.referenceCanvas = CGSize(width: 480, height: 640)
        var bubble = MacPhotoLayer(kind: .bubble, asset: "say1", text: "Hello, 世界 🎬", canvas: adjustment.referenceCanvas!)
        bubble.center = CGPoint(x: 240, y: 320); bubble.bounds = CGRect(x: 0, y: 0, width: 180, height: 96)
        bubble.transform = CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4)
        var sticker = MacPhotoLayer(kind: .sticker, asset: "32", canvas: adjustment.referenceCanvas!)
        sticker.center = CGPoint(x: 44, y: -12); sticker.bounds = CGRect(x: 2, y: 3, width: 72, height: 80)
        sticker.transform = CGAffineTransform(a: 0.5, b: 0, c: 0, d: 0.75, tx: 0, ty: 0)
        adjustment.bubbles = [bubble]; adjustment.stickers = [sticker]
        let bytes = try adjustment.encode()
        let root = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self], from: bytes) as? [String: Any])
        XCTAssertEqual(Set(root.keys), ["filterType", "referenceCanvasSize", "bubbles", "stickers"])
        let bitmap = try RasterCodec.bitmap(width: 480, height: 640)
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.6, blue: 0.8, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 480, height: 640))
        let sourceBytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        let source = try RasterCodec.metadata(sourceBytes)
        let native = try MacPhotoRenderer().render(adjustment, source: source, bytes: sourceBytes)
        let rendered = try RasterCodec.encode(native, as: .png)
        func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        // Same native production renderer and source, with one component at a
        // time. The UIKit consumer independently renders each through its
        // original controller, so a failed full image is diagnosable in one run.
        let components: [[String: String]] = try ["filtered-base", "bubble-artwork", "sticker-artwork", "all-artwork"].map { name in
            var component = adjustment
            component.bubbles = component.bubbles.map { var layer = $0; layer.text = ""; return layer }
            if name == "filtered-base" || name == "sticker-artwork" { component.bubbles = [] }
            if name == "filtered-base" || name == "bubble-artwork" { component.stickers = [] }
            let image = try MacPhotoRenderer().render(component, source: source, bytes: sourceBytes)
            let png = try RasterCodec.encode(image, as: .png)
            return ["name": name, "sha256": digest(png), "base64": png.base64EncodedString()]
        }
        let asset = try NativeResources.legacyPhotosBubbleImage(named: bubble.asset)
        let textRect = try XCTUnwrap(MacPhotoRenderer.bubbleTextRect(bounds: bubble.bounds, imageWidth: asset.width,
            imageHeight: asset.height, area: NativeResources.bubbleArea(named: bubble.asset)))
        let layout = try MacPhotoTextLayout.make(bubble.text, rect: textRect)
        let textRaster = try MacPhotoTextRaster.make(layout, bounds: textRect.size)
        print("MAC_LAYER_UIKIT_COMPOSITOR_NATIVE_LAYOUT asset=\(asset.width)x\(asset.height) textRect=\(textRect) fontSize=\(layout.fontSize) height=\(layout.height) font=\(CTFontCopyPostScriptName(layout.font)) ascent=\(CTFontGetAscent(layout.font)) descent=\(CTFontGetDescent(layout.font)) leading=\(CTFontGetLeading(layout.font)) backing=\(textRaster.width)x\(textRaster.height) backingScale=\(MacPhotoTextRaster.scale)")
        let lines = CTFrameGetLines(layout.frame) as! [CTLine]
        var origins = [CGPoint](repeating: .zero, count: lines.count)
        CTFrameGetLineOrigins(layout.frame, CFRange(location: 0, length: 0), &origins)
        for (index, line) in lines.enumerated() {
            let runs = CTLineGetGlyphRuns(line) as! [CTRun]
            let fonts = runs.map { run -> String in
                let font = (CTRunGetAttributes(run) as NSDictionary)[kCTFontAttributeName] as! CTFont
                return "\(CTFontCopyPostScriptName(font)):size=\(CTFontGetSize(font)):ascent=\(CTFontGetAscent(font)):descent=\(CTFontGetDescent(font))"
            }
            print("MAC_LAYER_UIKIT_COMPOSITOR_NATIVE_LINE index=\(index) origin=\(origins[index]) range=\(CTLineGetStringRange(line)) width=\(CTLineGetTypographicBounds(line, nil, nil, nil)) runFonts=\(fonts)")
        }
        let backingAttachment = XCTAttachment(data: try RasterCodec.encode(textRaster, as: .png), uniformTypeIdentifier: "public.png")
        backingAttachment.name = "native-mac-layer-text-backing-2x"; backingAttachment.lifetime = .keepAlways
        add(backingAttachment)
        let textPNG = try RasterCodec.encode(textRaster, as: .png)
        let candidateObservation: [String: Any] = ["schema": "Celluloid.TextObservation.1", "kind": "actual-native-coretext-backing",
            "archiveSHA256": digest(bytes), "scale": MacPhotoTextRaster.scale, "padding": 0,
            "width": textRaster.width, "height": textRaster.height, "logicalBounds": NSStringFromSize(textRect.size),
            "text": bubble.text, "pngSHA256": digest(textPNG), "pngBase64": textPNG.base64EncodedString(),
            "scope": "Actual candidate backing before affine mapping; not independent expected output"]
        print("CELLULOID_TEXT_OBSERVATION " + String(decoding: try JSONSerialization.data(withJSONObject: candidateObservation, options: [.sortedKeys]), as: UTF8.self))
        try diagnoseNativeText(bubble.text, bounds: textRect.size, archiveHash: digest(bytes))
        let record: [String: Any] = ["identifier": MacPhotoAdjustment.identifier, "version": MacPhotoAdjustment.version,
            "name": "manufactured-affine", "sha256": digest(bytes), "base64": bytes.base64EncodedString(),
            "sourceSHA256": digest(sourceBytes), "sourceBase64": sourceBytes.base64EncodedString(),
            "renderedSHA256": digest(rendered), "renderedBase64": rendered.base64EncodedString(), "components": components]
        print("MAC_LAYER_ADJUSTMENT_FIXTURE " + String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
        try diagnoseProductionSmoothing(adjustment, source: source, sourceBytes: sourceBytes, archive: bytes, full: rendered)
        try compareCurrentMacWithOriginalUIKit2x(archive: bytes, source: sourceBytes, full: rendered, components: components)
        let decoded = try MacPhotoAdjustment.decode(bytes)
        XCTAssertEqual(decoded.bubbles[0].transform, bubble.transform); XCTAssertEqual(decoded.stickers[0].bounds, sticker.bounds)
        // This is NOT itself UIKit interoperability proof. The matching phone
        // test consumes these actual emitted bytes through its original reader.
    }
    /// Probe only the two smoothing flags on the actual production glyph path.
    /// The historical backing is a separate original UILabel diagnostic, never
    /// a replacement for the independent final 2x compositor or AppKit oracle.
    private func diagnoseProductionSmoothing(_ adjustment: MacPhotoAdjustment, source: SourceImage,
                                             sourceBytes: Data, archive: Data, full: Data) throws {
        func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        func packet(_ name: String, expected: String) throws -> (Data, [String: Any]) {
            let bytes = try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "json")))
            XCTAssertEqual(digest(bytes), expected)
            guard digest(bytes) == expected else { throw NSError(domain: "MacSmoothingProbe", code: 1) }
            return (bytes, try XCTUnwrap(JSONSerialization.jsonObject(with: bytes) as? [String: Any]))
        }
        let (controlData, controls) = try packet("platform-rendering-controls", expected: "7b03cc5efba3a4bfdf40f1be5e33ff67d94eb6166d9659f2f8acc114540cb7b1")
        let (backingData, backingControl) = try packet("original-uikit-2x-backing", expected: "e2f7b7c4fa0cee8d866c7a3475b052fa5ab6328c31b95465ae5c170a31fc0bdf")
        let profiles = try XCTUnwrap(controls["profiles"] as? [String: Any])
        let profile = try XCTUnwrap(profiles["2x"] as? [String: Any])
        let fullImages = try XCTUnwrap(profile["images"] as? [String: Any])
        let fullControl = try XCTUnwrap(fullImages["full"] as? [String: Any])
        let originalFull = try XCTUnwrap(Data(base64Encoded: XCTUnwrap(fullControl["base64"] as? String)))
        XCTAssertEqual(digest(originalFull), fullControl["sha256"] as? String)
        let backingImage = try XCTUnwrap(backingControl["image"] as? [String: Any])
        let originalBacking = try XCTUnwrap(Data(base64Encoded: XCTUnwrap(backingImage["pngBase64"] as? String)))
        XCTAssertEqual(digest(originalBacking), "f867ce60c648fde2e504a0d7afd181ada660a2fcc3e4e3327b7cc9a5077d4958")
        let bubble = try XCTUnwrap(adjustment.bubbles.first)
        let asset = try NativeResources.legacyPhotosBubbleImage(named: bubble.asset)
        let rect = try XCTUnwrap(MacPhotoRenderer.bubbleTextRect(bounds: bubble.bounds, imageWidth: asset.width,
            imageHeight: asset.height, area: NativeResources.bubbleArea(named: bubble.asset)))
        let layout = try MacPhotoTextLayout.make(bubble.text, rect: rect)
        func rgba(_ bytes: Data, width: Int, height: Int) throws -> [UInt8] {
            let input = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
            let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(input, 0, nil))
            XCTAssertEqual(image.width, width); XCTAssertEqual(image.height, height)
            guard image.width == width, image.height == height else { throw NSError(domain: "MacSmoothingProbe", code: 2) }
            let bitmap = try RasterCodec.bitmap(width: width, height: height)
            bitmap.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            let storage = try XCTUnwrap(bitmap.data).assumingMemoryBound(to: UInt8.self)
            return Array(UnsafeBufferPointer(start: storage, count: width * height * 4))
        }
        func compare(_ actual: Data, _ expected: Data, name: String, width: Int, height: Int, rows: Range<Int>) throws -> [String: Any] {
            let a = try rgba(actual, width: width, height: height), b = try rgba(expected, width: width, height: height)
            var maxima = [Int](repeating: 0, count: 4), count = 0
            var minX = width, minY = height, maxX = -1, maxY = -1
            for y in rows { for x in 0..<width {
                var changed = false
                for channel in 0..<4 {
                    let index = (y * width + x) * 4 + channel
                    let delta = abs(Int(a[index]) - Int(b[index]))
                    maxima[channel] = max(maxima[channel], delta); changed = changed || delta > 2
                }
                if changed { count += 1; minX = min(minX, x); minY = min(minY, y); maxX = max(maxX, x); maxY = max(maxY, y) }
            } }
            return ["name": name, "rect": [0, rows.lowerBound, width, rows.count],
                "maximumChannelDifference": maxima.max() ?? 0, "channelMaximumsRGBA": maxima,
                "pixelsAboveTwo": count, "boundsAboveTwo": [minX, minY, maxX, maxY]]
        }
        XCTAssertFalse(MacPhotoTextRaster.diagnosticDisableFontSmoothing)
        let defaultBacking = try RasterCodec.encode(MacPhotoTextRaster.make(layout, bounds: rect.size), as: .png)
        let retainedBacking = try RasterCodec.encode(MacPhotoTextRaster.makeBacking(layout, bounds: rect.size).image, as: .png)
        XCTAssertEqual(try rgba(defaultBacking, width: 56, height: 88), try rgba(retainedBacking, width: 56, height: 88),
                       "This fixture's diagnostic surface must equal actual retained production backing")
        let disabled: (Data, Data) = try MacPhotoTextRaster.$diagnosticDisableFontSmoothing.withValue(true) {
            XCTAssertTrue(MacPhotoTextRaster.diagnosticDisableFontSmoothing)
            let fullImage = try MacPhotoRenderer().render(adjustment, source: source, bytes: sourceBytes)
            let backing = try MacPhotoTextRaster.make(layout, bounds: rect.size)
            return (try RasterCodec.encode(fullImage, as: .png), try RasterCodec.encode(backing, as: .png))
        }
        XCTAssertFalse(MacPhotoTextRaster.diagnosticDisableFontSmoothing)
        let restored = try RasterCodec.encode(MacPhotoRenderer().render(adjustment, source: source, bytes: sourceBytes), as: .png)
        XCTAssertEqual(digest(restored), digest(full), "The scoped diagnostic must not change subsequent default output")
        func imageRecord(_ bytes: Data) -> [String: String] { ["sha256": digest(bytes), "base64": bytes.base64EncodedString()] }
        var variants: [[String: Any]] = []
        for (name, rendered, backing) in [("default", full, defaultBacking), ("smoothing-disabled", disabled.0, disabled.1)] {
            let comparisons = try [compare(rendered, originalFull, name: "full", width: 480, height: 640, rows: 0..<640),
                compare(backing, originalBacking, name: "backing-all", width: 56, height: 88, rows: 0..<88),
                compare(backing, originalBacking, name: "latin", width: 56, height: 88, rows: 0..<34),
                compare(backing, originalBacking, name: "cjk", width: 56, height: 88, rows: 34..<55),
                compare(backing, originalBacking, name: "emoji", width: 56, height: 88, rows: 55..<88)]
            variants.append(["name": name, "full": imageRecord(rendered), "backing": imageRecord(backing), "comparisons": comparisons])
        }
        // Record real fallback metadata; never manufacture missing historical
        // UIKit fallback/font-version evidence or change glyph positions.
        let ctRuns = (CTFrameGetLines(layout.frame) as! [CTLine]).flatMap { CTLineGetGlyphRuns($0) as! [CTRun] }.filter { CTRunGetGlyphCount($0) > 0 }
        let glyphRuns = try MacPhotoTextRaster.glyphRuns(layout, bounds: rect.size, padding: 0)
        XCTAssertEqual(ctRuns.count, glyphRuns.count)
        let fonts: [[String: Any]] = zip(ctRuns, glyphRuns).map { ctRun, run in
            let font = (CTRunGetAttributes(ctRun) as NSDictionary)[kCTFontAttributeName] as! CTFont
            let m = run.textMatrix
            return ["font": CTFontCopyPostScriptName(font) as String, "size": CTFontGetSize(font),
                "version": (CTFontCopyName(font, kCTFontVersionNameKey) as String?) ?? "unavailable",
                "glyphs": run.glyphs.map(Int.init), "positions": run.positions.map { [$0.x, $0.y] },
                "sourceRange": [run.sourceRange.location, run.sourceRange.length], "textMatrix": [m.a, m.b, m.c, m.d, m.tx, m.ty]]
        }
        let record: [String: Any] = ["schema": "Celluloid.MacSmoothingProbe.1", "scope": "synthetic-pre-host-only",
            "archiveSHA256": digest(archive), "sourcePNG_SHA256": digest(sourceBytes),
            "controlFileSHA256": digest(controlData), "originalBackingFixtureSHA256": digest(backingData),
            "originalBackingPNG_SHA256": digest(originalBacking),
            "layout": ["textRect": [rect.minX, rect.minY, rect.width, rect.height], "fontSize": layout.fontSize,
                "lineHeight": layout.lineHeight, "naturalBlockHeight": layout.typographicHeight,
                "frameAllocationHeight": layout.height, "backingScale": MacPhotoTextRaster.scale] as [String: Any],
            "fonts": fonts, "variants": variants, "defaultRestoredPNG_SHA256": digest(restored),
            "diagnosticScopeRestored": !MacPhotoTextRaster.diagnosticDisableFontSmoothing,
            "layeredPhotosOutputQualified": false]
        let data = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        XCTAssertLessThanOrEqual(data.count, 100_000)
        print("MAC_SMOOTHING_PROBE " + String(decoding: data, as: UTF8.self))
    }

    /// A strict current-render versus immutable original-UIKit 2x probe.
    /// This is pre-host evidence; the production layered Photos guard stays on.
    private func compareCurrentMacWithOriginalUIKit2x(archive: Data, source: Data, full: Data,
                                                    components: [[String: String]]) throws {
        struct ImageRecord: Decodable { let sha256: String, base64: String }
        struct Profile: Decodable { let scale: Int; let images: [String: ImageRecord] }
        struct Controls: Decodable {
            let schema: String, sourceSHA: String, runtimeVersion: String, runtimeBuild: String, architecture: String
            let archiveSHA256: String, sourcePNG_SHA256: String
            let inputArchive: ImageRecord
            let profiles: [String: Profile], common: [String: ImageRecord]
        }
        func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "platform-rendering-controls", withExtension: "json"))
        let packet = try Data(contentsOf: url)
        XCTAssertLessThanOrEqual(packet.count, 200_000)
        XCTAssertEqual(digest(packet), "7b03cc5efba3a4bfdf40f1be5e33ff67d94eb6166d9659f2f8acc114540cb7b1")
        let controls = try JSONDecoder().decode(Controls.self, from: packet)
        XCTAssertEqual(controls.schema, "Celluloid.PlatformControls.1")
        XCTAssertEqual(controls.sourceSHA, "52bf7a9c04e2d91880ca4e8fd3418cd94d32bb7e")
        XCTAssertEqual(controls.runtimeVersion, "27.0"); XCTAssertEqual(controls.runtimeBuild, "24A434")
        XCTAssertEqual(controls.architecture, "arm64")
        XCTAssertEqual(digest(source), controls.sourcePNG_SHA256)
        let profile = try XCTUnwrap(controls.profiles["2x"])
        XCTAssertEqual(profile.scale, 2)
        let originalArchive = try XCTUnwrap(Data(base64Encoded: controls.inputArchive.base64))
        XCTAssertEqual(digest(originalArchive), controls.inputArchive.sha256)
        XCTAssertEqual(controls.inputArchive.sha256, controls.archiveSHA256)
        // The lane must additionally validate both complete typed archive graphs.
        // Preserve their raw hashes; do not substitute native re-encoding hashes.
        func rgba(_ bytes: Data) throws -> [UInt8] {
            let source = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
            XCTAssertEqual(CGImageSourceGetCount(source), 1)
            let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
            XCTAssertEqual(image.width, 480); XCTAssertEqual(image.height, 640)
            guard image.width == 480, image.height == 640 else {
                throw NSError(domain: "Celluloid.Mac2xProbe", code: 1)
            }
            let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
            let bitmap = try XCTUnwrap(CGContext(data: nil, width: 480, height: 640, bitsPerComponent: 8,
                bytesPerRow: 480 * 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            bitmap.draw(image, in: CGRect(x: 0, y: 0, width: 480, height: 640))
            let storage = try XCTUnwrap(bitmap.data).assumingMemoryBound(to: UInt8.self)
            return Array(UnsafeBufferPointer(start: storage, count: 480 * 640 * 4))
        }
        var actual: [String: Data] = ["full": full]
        XCTAssertEqual(components.count, 4)
        for component in components {
            let name = try XCTUnwrap(component["name"])
            XCTAssertNil(actual[name], "Duplicate rendered component")
            let data = try XCTUnwrap(Data(base64Encoded: XCTUnwrap(component["base64"])))
            XCTAssertEqual(digest(data), component["sha256"])
            actual[name] = data
        }
        let names = ["full", "filtered-base", "bubble-artwork", "sticker-artwork", "all-artwork"]
        XCTAssertEqual(Set(actual.keys), Set(names))
        var rows: [[String: Any]] = []
        for name in names {
            let rendered = try XCTUnwrap(actual[name])
            let original = try XCTUnwrap(profile.images[name] ?? controls.common[name])
            let expected = try XCTUnwrap(Data(base64Encoded: original.base64))
            XCTAssertEqual(digest(expected), original.sha256)
            let a = try rgba(rendered), b = try rgba(expected)
            var maxima = [Int](repeating: 0, count: 4)
            var different = 0, minX = 480, minY = 640, maxX = -1, maxY = -1
            for pixel in 0..<(480 * 640) {
                var changed = false
                for channel in 0..<4 {
                    let delta = abs(Int(a[pixel * 4 + channel]) - Int(b[pixel * 4 + channel]))
                    maxima[channel] = max(maxima[channel], delta); changed = changed || delta > 2
                }
                if changed {
                    different += 1; let x = pixel % 480, y = pixel / 480
                    minX = min(minX, x); minY = min(minY, y); maxX = max(maxX, x); maxY = max(maxY, y)
                }
            }
            let maximum = maxima.max() ?? 0
            let limit = ["filtered-base", "sticker-artwork"].contains(name) ? 0 : 2
            rows.append(["name": name, "actualPNG_SHA256": digest(rendered), "originalPNG_SHA256": original.sha256,
                         "maximumChannelDifference": maximum, "allowedMaximum": limit,
                         "channelMaximumsRGBA": maxima, "pixelsAboveTwo": different,
                         "boundsAboveTwo": [minX, minY, maxX, maxY]])
            XCTAssertLessThanOrEqual(maximum, limit, "Current Mac output differs from immutable original UIKit 2x: \(name)")
        }
        let report: [String: Any] = ["schema": "Celluloid.MacOriginal2xProbe.1", "scope": "synthetic-pre-host-only",
            "controlFileSHA256": digest(packet), "controlSourceSHA": controls.sourceSHA,
            "controlProfile": "2x", "controlRuntime": controls.runtimeVersion, "controlBuild": controls.runtimeBuild,
            "archiveSHA256": digest(archive), "controlArchiveSHA256": controls.archiveSHA256,
            "sourcePNG_SHA256": digest(source), "actualPNG_SHA256": digest(full), "comparisons": rows,
            "layeredPhotosOutputQualified": false]
        let reportData = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        XCTAssertLessThanOrEqual(reportData.count, 16_384)
        print("MAC_ORIGINAL_2X_PROBE " + String(decoding: reportData, as: UTF8.self))
        let attachment = XCTAttachment(data: reportData, uniformTypeIdentifier: "public.json")
        attachment.name = "native-mac-original-2x-probe.json"; attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testWrongTypedUnknownNonfiniteAndOverBudgetArchivesFailClosed() throws {
        func archive(_ root: [String: Any]) throws -> Data { try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true) }
        XCTAssertThrowsError(try MacPhotoAdjustment.decode(archive(["filterType": "Original", "futureLayer": true])))
        XCTAssertThrowsError(try MacPhotoAdjustment.decode(archive(["filterType": "Original", "referenceCanvasSize": "480,640"])))
        XCTAssertThrowsError(try MacPhotoAdjustment.decode(Data(repeating: 0, count: MacPhotoAdjustment.maximumArchiveBytes + 1)))
        var adjustment = MacPhotoAdjustment(); adjustment.referenceCanvas = CGSize(width: 480, height: 640)
        var layer = MacPhotoLayer(kind: .bubble, asset: "say1", canvas: adjustment.referenceCanvas!)
        layer.transform.tx = .infinity; adjustment.bubbles = [layer]
        XCTAssertThrowsError(try adjustment.encode())
        layer.transform = .identity; layer.text = String(repeating: "a", count: 16_385); adjustment.bubbles = [layer]
        XCTAssertThrowsError(try adjustment.encode())
        layer.text = "ok"; adjustment.bubbles = Array(repeating: layer, count: 101)
        XCTAssertThrowsError(try adjustment.encode())
    }
    func testFilterOnlyHistoricalPayloadCanAcquireANewCanvasWithoutChangingExistingGeometry() throws {
        let root = ["filterType": "Chrome"]
        let bytes = try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true)
        let decoded = try MacPhotoAdjustment.decode(bytes)
        XCTAssertNil(decoded.referenceCanvas); XCTAssertTrue(decoded.layers.isEmpty)
        XCTAssertNoThrow(try decoded.requireEditableCanvas())
    }
    /// Independent public AppKit/TextKit control. This does not invoke the
    /// candidate's CoreText layout/raster or change its acceptance assertions.
    private func diagnoseNativeText(_ text: String, bounds: CGSize, archiveHash: String) throws {
        let font = NSFont.systemFont(ofSize: 10)
        let paragraph = NSMutableParagraphStyle(); paragraph.lineBreakMode = .byCharWrapping
        paragraph.alignment = .left // Natural line metrics, no forced min/max height.
        let storage = NSTextStorage(string: text, attributes: [.font: font, .foregroundColor: NSColor.black, .paragraphStyle: paragraph])
        let manager = TextKitGlyphObserver()
        let container = NSTextContainer(containerSize: CGSize(width: bounds.width, height: CGFloat.greatestFiniteMagnitude))
        container.lineFragmentPadding = 0; container.lineBreakMode = .byCharWrapping
        storage.addLayoutManager(manager); manager.addTextContainer(container); manager.ensureLayout(for: container)
        let glyphRange = manager.glyphRange(for: container), used = manager.usedRect(for: container)
        var lines: [[String: Any]] = []
        manager.enumerateLineFragments(forGlyphRange: glyphRange) { rect, usedRect, _, range, _ in
            let characters = manager.characterRange(forGlyphRange: range, actualGlyphRange: nil)
            let location = manager.location(forGlyphAt: range.location)
            lines.append(["glyphRange": [range.location, range.length], "utf16Range": [characters.location, characters.length],
                "text": (text as NSString).substring(with: characters), "lineRect": NSStringFromRect(rect),
                "usedRect": NSStringFromRect(usedRect), "baselineInContainer": rect.minY + location.y,
                "layoutManagerBoundingRect": NSStringFromRect(manager.boundingRect(forGlyphRange: range, in: container))])
        }
        for scale: CGFloat in [2, 3] {
            for padding: CGFloat in [0, 8] {
                let width = Int(ceil((bounds.width + 2 * padding) * scale))
                let height = Int(ceil((bounds.height + 2 * padding) * scale))
                let bitmap = try RasterCodec.bitmap(width: width, height: height)
                bitmap.translateBy(x: 0, y: CGFloat(height)); bitmap.scaleBy(x: scale, y: -scale)
                let origin = CGPoint(x: padding, y: padding + (bounds.height - used.height) / 2 - used.minY)
                manager.observedGlyphRuns = []
                NSGraphicsContext.saveGraphicsState()
                NSGraphicsContext.current = NSGraphicsContext(cgContext: bitmap, flipped: true)
                manager.drawGlyphs(forGlyphRange: glyphRange, at: origin)
                NSGraphicsContext.restoreGraphicsState()
                let png = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
                let hash = SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined()
                let record: [String: Any] = ["schema": "Celluloid.TextObservation.1", "kind": "independent-appkit-textkit",
                    "archiveSHA256": archiveHash, "text": text, "utf16": Array(text.utf16).map(Int.init),
                    "requestedFont": font.fontName, "requestedFontSize": font.pointSize,
                    "fontAscender": font.ascender, "fontDescender": font.descender, "fontLeading": font.leading,
                    "fontSelection": "Fixed 10pt system-font observation; does not prove the candidate's 16...2pt fitting search",
                    "lineHeightRule": "natural AppKit/TextKit; no forced line heights", "logicalBounds": NSStringFromSize(bounds),
                    "coordinateSpace": "TextKit top-left coordinates; bitmap CTM explicitly flipped once, NSGraphicsContext marked flipped",
                    "usedRect": NSStringFromRect(used), "drawOrigin": NSStringFromPoint(origin), "lines": lines,
                    "glyphRuns": manager.observedGlyphRuns, "scale": scale, "padding": padding,
                    "glyphHookScope": "Only calls observed through the public showCGGlyphs hook; absent runs are not inferred",
                    "width": width, "height": height, "pngSHA256": hash, "pngBase64": png.base64EncodedString(),
                    "scope": "Independent diagnostic raster, never original UIKit backing or acceptance output"]
                print("CELLULOID_TEXT_OBSERVATION " + String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
            }
        }
    }

}

/// Observe only the documented draw hook, then call the original implementation.
/// The supplied NSFont is the actual substitution font used for these glyphs.
private final class TextKitGlyphObserver: NSLayoutManager {
    var observedGlyphRuns: [[String: Any]] = []
    override func showCGGlyphs(_ glyphs: UnsafePointer<CGGlyph>, positions: UnsafePointer<CGPoint>,
        count glyphCount: Int, font: NSFont, textMatrix: CGAffineTransform,
        attributes: [NSAttributedString.Key: Any], in context: CGContext) {
        let observedGlyphs = Array(UnsafeBufferPointer(start: glyphs, count: glyphCount))
        let ctm = context.ctm
        observedGlyphRuns.append(["font": font.fontName, "size": font.pointSize,
            "ascender": font.ascender, "descender": font.descender, "leading": font.leading,
            "glyphs": observedGlyphs.map(Int.init),
            "fontGlyphBounds": observedGlyphs.map { NSStringFromRect(font.boundingRect(forCGGlyph: $0)) },
            "fontGlyphBoundsScope": "Public font metrics, not observed raster alpha bounds",
            "positions": Array(UnsafeBufferPointer(start: positions, count: glyphCount)).map { [$0.x, $0.y] },
            "textMatrix": [textMatrix.a, textMatrix.b, textMatrix.c, textMatrix.d, textMatrix.tx, textMatrix.ty],
            "contextCTM": [ctm.a, ctm.b, ctm.c, ctm.d, ctm.tx, ctm.ty]])
        super.showCGGlyphs(glyphs, positions: positions, count: glyphCount, font: font,
            textMatrix: textMatrix, attributes: attributes, in: context)
    }
}
