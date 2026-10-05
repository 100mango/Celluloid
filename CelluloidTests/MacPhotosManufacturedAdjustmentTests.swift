import XCTest
import UIKit
import CryptoKit
@testable import CelluloidKit

/// Consumes actual native-macOS-produced bytes, never a UIKit substitute archive.
/// Fixture delivery is a separately admitted, source/hash-bound test-only step.
@MainActor final class MacPhotosManufacturedAdjustmentTests: XCTestCase {
    private struct Fixture: Decodable {
        let name: String, identifier: String, version: String, sha256: String, base64: String
        let sourceSHA256: String, sourceBase64: String, renderedSHA256: String, renderedBase64: String
        let components: [Component]?
    }
    private struct Component: Decodable { let name: String, sha256: String, base64: String }
    func testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor() throws {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("mac-layer-fixture.json")
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw XCTSkip("Requires the exact source-bound MAC_LAYER_ADJUSTMENT_FIXTURE from an admitted Mac run; interoperability and text pixel parity are not yet proved")
        }
        print("MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=\(UIScreen.main.scale)")
        let contents = try Data(contentsOf: url)
        XCTAssertLessThanOrEqual(contents.count, 500_000)
        let fixture = try JSONDecoder().decode(Fixture.self, from: contents)
        let controlURL = url.deletingLastPathComponent().appendingPathComponent("mac-platform-controls.json")
        let controlData = try Data(contentsOf: controlURL)
        XCTAssertLessThanOrEqual(controlData.count, 200_000)
        XCTAssertEqual(digest(controlData), Self.controlFileHash, "Immutable original UIKit control packet")
        let controls = try JSONDecoder().decode(PlatformControls.self, from: controlData)
        XCTAssertEqual(controls.schema, "Celluloid.PlatformControls.1")
        XCTAssertEqual(controls.sourceSHA, "52bf7a9c04e2d91880ca4e8fd3418cd94d32bb7e")
        XCTAssertEqual(controls.uikitProductionFingerprint, "5b648707e5f204c18007cd1158ccea7622387cbb277c8fe09b42b7587283cc35")
        XCTAssertEqual(UIDevice.current.systemVersion, controls.runtimeVersion)
        let profile = UIScreen.main.scale == 2 ? "2x" : UIScreen.main.scale == 3 ? "3x" : "unsupported"
        let ownControl = try XCTUnwrap(controls.profiles[profile])
        XCTAssertEqual(UIScreen.main.scale, CGFloat(ownControl.scale))
        XCTAssertEqual(fixture.sha256, controls.archiveSHA256); XCTAssertEqual(fixture.sourceSHA256, controls.sourcePNG_SHA256)
        var sameRuntime: [String: Int] = [:], exactComponents: [String: Int] = [:]
        var artwork: [String: [String: Int]] = [:]
        var rejectedArtworkMutations = 0
        XCTAssertEqual(fixture.name, "manufactured-affine")
        XCTAssertEqual(fixture.identifier, "Mango.CelluloidPhotoExtension"); XCTAssertEqual(fixture.version, "1.0")
        func data(_ base64: String, _ hash: String) throws -> Data {
            let data = try XCTUnwrap(Data(base64Encoded: base64))
            XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), hash)
            return data
        }
        let archive = try data(fixture.base64, fixture.sha256)
        let decoded = try AdjustmentData.decode(archive)
        XCTAssertEqual(decoded.filterType, .Fade); XCTAssertEqual(decoded.referenceCanvasSize, CGSize(width: 480, height: 640))
        XCTAssertEqual(decoded.bubbles.count, 1); XCTAssertEqual(decoded.stickers.count, 1)
        let bubble = try XCTUnwrap(decoded.bubbles.first), sticker = try XCTUnwrap(decoded.stickers.first)
        XCTAssertEqual(bubble.content, "Hello, 世界 🎬")
        XCTAssertEqual(bubble.center, CGPoint(x: 240, y: 320)); XCTAssertEqual(bubble.bounds, CGRect(x: 0, y: 0, width: 180, height: 96))
        XCTAssertEqual(bubble.transform, CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4))
        XCTAssertEqual(sticker.center, CGPoint(x: 44, y: -12)); XCTAssertEqual(sticker.bounds, CGRect(x: 2, y: 3, width: 72, height: 80))
        XCTAssertEqual(sticker.transform, CGAffineTransform(a: 0.5, b: 0, c: 0, d: 0.75, tx: 0, ty: 0))
        let reencoded = try AdjustmentData.decode(decoded.encode())
        XCTAssertEqual(reencoded.bubbles[0].transform, bubble.transform)
        XCTAssertEqual(reencoded.stickers[0].bounds, sticker.bounds)
        let source = try XCTUnwrap(UIImage(data: data(fixture.sourceBase64, fixture.sourceSHA256)))
        let native = try XCTUnwrap(UIImage(data: data(fixture.renderedBase64, fixture.renderedSHA256)))
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 480, height: 850)
        editor.sourceImage = source; editor.view.layoutIfNeeded(); editor.restoreFromData(decoded)
        let expected = try XCTUnwrap(editor.outputImage)
        XCTAssertEqual(expected.cgImage?.width, 480); XCTAssertEqual(expected.cgImage?.height, 640)
        XCTAssertEqual(native.cgImage?.width, 480); XCTAssertEqual(native.cgImage?.height, 640)
        let actual = try pixels(native), oracle = try pixels(expected)
        XCTAssertEqual(actual.count, oracle.count)
        let maximum = zip(actual, oracle).map { abs(Int($0) - Int($1)) }.max() ?? 0
        print("MAC_LAYER_UIKIT_COMPOSITOR archiveSHA256=\(fixture.sha256) sourceSHA256=\(fixture.sourceSHA256) nativeSHA256=\(fixture.renderedSHA256) maximumChannelDifference=\(maximum)")
        // Retain the historical universal comparison verbatim as a diagnostic.
        // The frozen 2x/3x references differ by172, so no raster can satisfy both.
        // The replacement gates below are strict within each qualified runtime.
        sameRuntime["full"] = maximumDifference(oracle, try frozenPixels(XCTUnwrap(ownControl.images["full"])))
        XCTAssertLessThanOrEqual(try XCTUnwrap(sameRuntime["full"]), 2, "Original UIKit must match its own immutable runtime control")
        diagnose(name: "full", actual: actual, oracle: oracle, expected: expected)
        let view = BubbleView(bubbleModel: bubble); view.layoutIfNeeded()
        let label = view.bubbleLabel, image = try XCTUnwrap(view.imageView.image)
        print("MAC_LAYER_UIKIT_COMPOSITOR_UIKIT_LAYOUT asset=\(image.cgImage?.width ?? 0)x\(image.cgImage?.height ?? 0) imageScale=\(image.scale) textRect=\(label.frame) font=\(label.font.fontName) fontSize=\(label.font.pointSize) lineHeight=\(label.font.lineHeight) ascender=\(label.font.ascender) descender=\(label.font.descender) leading=\(label.font.leading) textRectForBounds=\(label.textRect(forBounds: label.bounds, limitedToNumberOfLines: 0)) sizeThatFits=\(label.sizeThatFits(CGSize(width: label.bounds.width, height: CGFloat.greatestFiniteMagnitude))) contentsScale=\(label.layer.contentsScale) referenceCanvas=\(editor.adjustmentData.referenceCanvasSize.debugDescription)")
        try diagnoseUIKitText(label, archiveHash: fixture.sha256)
        if let components = fixture.components {
            XCTAssertEqual(components.count, 4)
            XCTAssertEqual(Set(components.map(\.name)), ["filtered-base", "bubble-artwork", "sticker-artwork", "all-artwork"])
            for component in components {
                var adjustment = decoded
                adjustment.bubbles = adjustment.bubbles.map { var model = $0; model.content = ""; return model }
                if component.name == "filtered-base" || component.name == "sticker-artwork" { adjustment.bubbles = [] }
                if component.name == "filtered-base" || component.name == "bubble-artwork" { adjustment.stickers = [] }
                let componentNative = try XCTUnwrap(UIImage(data: data(component.base64, component.sha256)))
                // Always call the original UIKit controller/compositor. Do not
                // replace it with the Mac renderer or reconstructed CG paths.
                let controller = BaseEditPhotoController(); controller.loadViewIfNeeded()
                controller.view.frame = CGRect(x: 0, y: 0, width: 480, height: 850)
                controller.sourceImage = source; controller.view.layoutIfNeeded(); controller.restoreFromData(adjustment)
                let componentExpected = try XCTUnwrap(controller.outputImage)
                XCTAssertEqual(componentNative.cgImage?.width, 480); XCTAssertEqual(componentNative.cgImage?.height, 640)
                let a = try pixels(componentNative), b = try pixels(componentExpected)
                XCTAssertEqual(a.count, b.count)
                let difference = zip(a, b).map { abs(Int($0) - Int($1)) }.max() ?? 0
                print("MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT name=\(component.name) nativeSHA256=\(component.sha256) maximumChannelDifference=\(difference)")
                if ["filtered-base", "sticker-artwork"].contains(component.name) {
                    let frozen = try frozenPixels(XCTUnwrap(controls.common[component.name]))
                    let exact = max(difference, max(maximumDifference(a, frozen), maximumDifference(b, frozen)))
                    exactComponents[component.name] = exact
                    XCTAssertEqual(exact, 0, "Previously exact base/sticker pixels must remain identical")
                } else {
                    let two = try frozenPixels(XCTUnwrap(controls.profiles["2x"]?.images[component.name]))
                    let three = try frozenPixels(XCTUnwrap(controls.profiles["3x"]?.images[component.name]))
                    sameRuntime[component.name] = maximumDifference(b, profile == "2x" ? two : three)
                    XCTAssertLessThanOrEqual(try XCTUnwrap(sameRuntime[component.name]), 2, "Original UIKit artwork must match its own frozen runtime")
                    let metrics = artworkMetrics(a, two, three); artwork[component.name] = metrics
                    XCTAssertTrue(artworkPasses(metrics), "Independent fixed artwork edge/interior contract: \(component.name) \(metrics)")
                    // Real image mutations exercise this pixel oracle. They do
                    // not alter controls, metadata, or any production source.
                    var recolored = two; recolored[0] = two[0] == 0 ? 255 : 0
                    var translucent = two; translucent[3] = 0
                    let removed = try frozenPixels(XCTUnwrap(controls.common["filtered-base"]))
                    for mutation in [recolored, translucent, removed] {
                        let rejected = !artworkPasses(artworkMetrics(mutation, two, three))
                        XCTAssertTrue(rejected, "An altered image must fail the independent artwork oracle")
                        if rejected { rejectedArtworkMutations += 1 }
                    }
                }
                diagnose(name: component.name, actual: a, oracle: b, expected: componentExpected)
                if component.name == "all-artwork", a.count == actual.count, b.count == oracle.count {
                    let textDifference = actual.indices.map { abs((Int(actual[$0]) - Int(a[$0])) - (Int(oracle[$0]) - Int(b[$0]))) }.max() ?? 0
                    print("MAC_LAYER_UIKIT_COMPOSITOR_TEXT_CONTRIBUTION maximumChannelDifference=\(textDifference)")
                }
            }
        } else {
            XCTFail("Required versioned component proof is absent")
        }
        XCTAssertEqual(Set(sameRuntime.keys), Set(["full", "bubble-artwork", "all-artwork"]))
        XCTAssertEqual(Set(exactComponents.keys), Set(["filtered-base", "sticker-artwork"]))
        XCTAssertEqual(Set(artwork.keys), Set(["bubble-artwork", "all-artwork"]))
        XCTAssertEqual(rejectedArtworkMutations, 6)
        let contract: [String: Any] = ["schema": "Celluloid.PlatformRendering.1", "profile": profile,
            "runtimeVersion": UIDevice.current.systemVersion, "scale": Double(UIScreen.main.scale),
            "controlFileSHA256": Self.controlFileHash, "controlSourceSHA": controls.sourceSHA,
            "archiveSHA256": fixture.sha256, "sourceSHA256": fixture.sourceSHA256, "nativeSHA256": fixture.renderedSHA256,
            "historicalFullMaximum": maximum, "sameRuntimeMaximums": sameRuntime,
            "exactComponentMaximums": exactComponents, "artworkMetrics": artwork,
            "rejectedArtworkMutations": rejectedArtworkMutations]
        print("MAC_PLATFORM_RENDERING_CONTRACT " + String(decoding: try JSONSerialization.data(withJSONObject: contract, options: [.sortedKeys]), as: UTF8.self))
    }
    private struct PlatformImage: Decodable { let sha256: String, base64: String }
    private struct PlatformProfile: Decodable { let scale: Int, originatingModel: String, images: [String: PlatformImage] }
    private struct PlatformControls: Decodable {
        let schema: String, sourceSHA: String, runtimeVersion: String, runtimeBuild: String
        let archiveSHA256: String, sourcePNG_SHA256: String, uikitProductionFingerprint: String
        let profiles: [String: PlatformProfile], common: [String: PlatformImage]
    }
    private static let controlFileHash = "7b03cc5efba3a4bfdf40f1be5e33ff67d94eb6166d9659f2f8acc114540cb7b1"
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func frozenPixels(_ blob: PlatformImage) throws -> [UInt8] {
        let data = try XCTUnwrap(Data(base64Encoded: blob.base64))
        XCTAssertEqual(digest(data), blob.sha256)
        let image = try XCTUnwrap(UIImage(data: data))
        XCTAssertEqual(image.cgImage?.width, 480); XCTAssertEqual(image.cgImage?.height, 640)
        return try pixels(image)
    }
    private func maximumDifference(_ a: [UInt8], _ b: [UInt8]) -> Int {
        guard a.count == b.count else { return 256 }
        return zip(a, b).map { abs(Int($0) - Int($1)) }.max() ?? 0
    }
    private func gradientEdges(_ bytes: [UInt8]) -> [Bool] {
        var edges = [Bool](repeating: false, count: 480 * 640)
        guard bytes.count == edges.count * 4 else { return edges }
        for y in 0..<640 { for x in 0..<480 {
            let p = y * 480 + x
            for q in [x + 1 < 480 ? p + 1 : -1, y + 1 < 640 ? p + 480 : -1] where q >= 0 {
                if (0..<4).contains(where: { abs(Int(bytes[p * 4 + $0]) - Int(bytes[q * 4 + $0])) > 2 }) {
                    edges[p] = true; edges[q] = true
                }
            }
        } }
        return edges
    }
    private func expandedEdges(_ edges: [Bool]) -> [Bool] {
        var result = edges
        for y in 0..<640 { for x in 0..<480 where edges[y * 480 + x] {
            for yy in max(0, y - 1)...min(639, y + 1) { for xx in max(0, x - 1)...min(479, x + 1) {
                result[yy * 480 + xx] = true
            } }
        } }
        return result
    }
    /// The permitted edge band and color envelope come only from immutable
    /// original UIKit controls. Candidate output never defines its own mask.
    private func artworkMetrics(_ candidate: [UInt8], _ two: [UInt8], _ three: [UInt8]) -> [String: Int] {
        guard candidate.count == 480 * 640 * 4, two.count == candidate.count, three.count == candidate.count else {
            return ["outsideMaximum": 256, "edgeViolations": 1, "envelopeViolations": 1, "opacityViolations": 1, "controlBandPixels": 0]
        }
        let twoEdges = gradientEdges(two), threeEdges = gradientEdges(three)
        let referenceEdges = zip(twoEdges, threeEdges).map { $0 || $1 }
        let band = expandedEdges(referenceEdges), actualEdges = gradientEdges(candidate), actualBand = expandedEdges(actualEdges)
        var outside = 0, violations = 0, edgeViolations = 0, opacity = 0
        for y in 0..<640 { for x in 0..<480 {
            let p = y * 480 + x
            if candidate[p * 4 + 3] != 255 { opacity += 1 }
            if (actualEdges[p] && !band[p]) || (referenceEdges[p] && !actualBand[p]) { edgeViolations += 1 }
            if !band[p] {
                for c in 0..<4 { outside = max(outside, max(abs(Int(candidate[p * 4 + c]) - Int(two[p * 4 + c])), abs(Int(candidate[p * 4 + c]) - Int(three[p * 4 + c])))) }
            } else {
                var pixelViolation = false
                for c in 0..<4 {
                    var low = 255, high = 0
                    for yy in max(0, y - 1)...min(639, y + 1) { for xx in max(0, x - 1)...min(479, x + 1) {
                        let q = (yy * 480 + xx) * 4 + c
                        low = min(low, min(Int(two[q]), Int(three[q]))); high = max(high, max(Int(two[q]), Int(three[q])))
                    } }
                    let value = Int(candidate[p * 4 + c])
                    if value < low - 2 || value > high + 2 { pixelViolation = true }
                }
                if pixelViolation { violations += 1 }
            }
        } }
        return ["outsideMaximum": outside, "edgeViolations": edgeViolations, "envelopeViolations": violations,
                "opacityViolations": opacity, "controlBandPixels": band.filter { $0 }.count]
    }
    private func artworkPasses(_ metrics: [String: Int]) -> Bool {
        ["outsideMaximum", "edgeViolations", "envelopeViolations", "opacityViolations"].allSatisfy { metrics[$0] == 0 }
    }
    private func diagnose(name: String, actual: [UInt8], oracle: [UInt8], expected: UIImage) {
        guard actual.count == oracle.count, let cg = expected.cgImage else { return }
        var count = 0, minX = cg.width, minY = cg.height, maxX = -1, maxY = -1
        for offset in stride(from: 0, to: actual.count, by: 4) {
            if (0..<4).contains(where: { abs(Int(actual[offset + $0]) - Int(oracle[offset + $0])) > 2 }) {
                count += 1
                let x = (offset / 4) % cg.width, y = (offset / 4) / cg.width
                minX = min(minX, x); minY = min(minY, y); maxX = max(maxX, x); maxY = max(maxY, y)
            }
        }
        let png = expected.pngData() ?? Data()
        let hash = SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined()
        print("MAC_LAYER_UIKIT_COMPOSITOR_DIAGNOSTIC name=\(name) oraclePNG_SHA256=\(hash) differingPixels=\(count) bitmapBounds=\(minX),\(minY),\(maxX),\(maxY)")
        if count > 0 {
            // Native PNGs are already in the hash-bound fixture. Retain at most
            // five small independent UIKit images, within the existing 8-image
            // attachment selector and unchanged aggregate evidence byte budget.
            let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
            attachment.name = "native-mac-layer-\(name)-uikit"; attachment.lifetime = .keepAlways
            add(attachment)
        }
    }
    private func pixels(_ image: UIImage) throws -> [UInt8] {
        let cg = try XCTUnwrap(image.cgImage), space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: cg.width, height: cg.height, bitsPerComponent: 8,
            bytesPerRow: cg.width * 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        bitmap.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        return Array(UnsafeBufferPointer(start: bitmap.data!.assumingMemoryBound(to: UInt8.self), count: bitmap.bytesPerRow * bitmap.height))
    }
    /// This separate BubbleLabel has the same public configuration, but is not
    /// the already-discarded temporary label inside the shipping compositor.
    /// No private KVC, layer internals or inferred backing dimensions are used.
    private func diagnoseUIKitText(_ label: UILabel, archiveHash: String) throws {
        func backing(_ phase: String) throws -> [String: Any] {
            var row: [String: Any] = ["phase": phase, "contentsScale": label.layer.contentsScale,
                "contentsRect": NSCoder.string(for: label.layer.contentsRect),
                "contentsGravity": label.layer.contentsGravity.rawValue,
                "bounds": NSCoder.string(for: label.bounds), "position": NSCoder.string(for: label.layer.position),
                "scope": "Public CALayer.contents of separate diagnostic BubbleLabel only"]
            row["availableCGImage"] = false
            row["reason"] = "Public contents does not expose a CGImage; dimensions unavailable"
            if let contents = label.layer.contents,
               CFGetTypeID(contents as CFTypeRef) == CGImage.typeID {
                // Core Foundation downcasts require a type-ID check; an `as?`
                // cast alone is not a reliable check for a CF-backed object.
                let image = contents as! CGImage
                if let png = UIImage(cgImage: image).pngData() {
                    row["availableCGImage"] = true; row.removeValue(forKey: "reason")
                    row["width"] = image.width; row["height"] = image.height
                    row["pngSHA256"] = SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined()
                    row["pngBase64"] = png.base64EncodedString()
                } else { row["reason"] = "Public CGImage exists but PNG encoding was unavailable" }
            }
            return row
        }
        let initialBacking = try backing("before any explicit diagnostic rendering")
        let first = UILayoutGuide(), last = UILayoutGuide()
        label.addLayoutGuide(first); label.addLayoutGuide(last)
        let constraints = [first.topAnchor.constraint(equalTo: label.firstBaselineAnchor),
            last.topAnchor.constraint(equalTo: label.lastBaselineAnchor),
            first.leadingAnchor.constraint(equalTo: label.leadingAnchor), last.leadingAnchor.constraint(equalTo: label.leadingAnchor),
            first.widthAnchor.constraint(equalToConstant: 0), first.heightAnchor.constraint(equalToConstant: 0),
            last.widthAnchor.constraint(equalToConstant: 0), last.heightAnchor.constraint(equalToConstant: 0)]
        NSLayoutConstraint.activate(constraints); label.layoutIfNeeded()
        let baselines: [String: Any] = ["first": first.layoutFrame.minY, "last": last.layoutFrame.minY,
            "space": "Diagnostic UILabel logical bounds; public Auto Layout baseline anchors",
            "observedPositiveOrderedAnchors": first.layoutFrame.minY > 0 && last.layoutFrame.minY > first.layoutFrame.minY,
            "availabilityNote": "Zero or unordered anchors are inconclusive; never substitute font-derived baseline estimates",
            "internalLineSpans": "unavailable from public UILabel API; not inferred from raster"]
        NSLayoutConstraint.deactivate(constraints); label.removeLayoutGuide(first); label.removeLayoutGuide(last)
        for padding: CGFloat in [0, 8] {
            let format = UIGraphicsImageRendererFormat(); format.scale = UIScreen.main.scale
            format.opaque = false; format.preferredRange = .standard
            let size = CGSize(width: label.bounds.width + 2 * padding, height: label.bounds.height + 2 * padding)
            let image = UIGraphicsImageRenderer(size: size, format: format).image { output in
                output.cgContext.translateBy(x: padding, y: padding)
                if padding == 0 { label.layer.render(in: output.cgContext) }
                else { label.drawText(in: label.bounds) }
            }
            let png = try XCTUnwrap(image.pngData()), cg = try XCTUnwrap(image.cgImage)
            let record: [String: Any] = ["schema": "Celluloid.TextObservation.1", "kind": "separate-uikit-label-diagnostic",
                "archiveSHA256": archiveHash, "text": label.text ?? "", "utf16": Array((label.text ?? "").utf16).map(Int.init),
                "font": label.font.fontName, "fontSize": label.font.pointSize, "lineHeight": label.font.lineHeight,
                "bounds": NSCoder.string(for: label.bounds), "textRect": NSCoder.string(for: label.textRect(forBounds: label.bounds, limitedToNumberOfLines: 0)),
                "baselines": baselines, "initialPublicBacking": initialBacking,
                "afterDiagnosticPublicBacking": try backing("after explicitly labeled diagnostic rendering"),
                "drawingMethod": padding == 0 ? "CALayer.render" : "UILabel.drawText with padded destination; not a clipping proof by itself",
                "clippingLimit": "The padded and unpadded observations use different public drawing methods; their difference alone cannot prove clipping",
                "scale": format.scale, "padding": padding, "width": cg.width, "height": cg.height,
                "pngSHA256": SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined(), "pngBase64": png.base64EncodedString(),
                "scope": "New diagnostic raster; shipping compositor unchanged, historical cross-platform deltas retained separately from versioned runtime controls"]
            print("CELLULOID_TEXT_OBSERVATION " + String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
        }
    }

}
