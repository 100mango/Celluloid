import XCTest
import AppKit
import CoreImage
import CryptoKit
import ImageIO
import UniformTypeIdentifiers
import zlib
import CelluloidDomain
import CelluloidRendering

/// Isolated pre-host control. This does not observe PHContentEditingInput,
/// the JPEG submitted by Photos, or Save/Cancel/Revert in the Photos host.
final class MacPhotoNativeCodecControlTests: XCTestCase {
    private let sourceSHA256 = "6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772"
    private var lifecycleICC: [String: Any]?
    private var retained: [String: [String: Any]] = [:]
    private var retainedBytes = 0
    private var referenceJPEG: Data?
    private struct LifecycleRaster {
        let bytes: Data
        let rgba: Data
        let metadata: [String: Any]
    }

    func testRetainedSourceFadeExportAfterOriginalAndFadePreviews() async throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "lifecycle-source", withExtension: "png"))
        let bytes = try Data(contentsOf: url)
        guard digest(bytes) == sourceSHA256 else { throw block("Retained synthetic source SHA-256 changed") }
        let original = try lifecycleRaster(bytes, expectedFormat: UTType.png.identifier)
        let source = try RasterCodec.metadata(bytes)
        let queue = MacPhotoRenderQueue()
        var adjustment = MacPhotoAdjustment()
        // One queue owns one renderer/context throughout this exact sequence.
        let originalPreview = try await queue.preview(adjustment, source: source, bytes: bytes)
        XCTAssertEqual(originalPreview.width, 1200); XCTAssertEqual(originalPreview.height, 800)
        adjustment.filter = .fade
        let fadePreview = try await queue.preview(adjustment, source: source, bytes: bytes)
        XCTAssertEqual(fadePreview.width, 1200); XCTAssertEqual(fadePreview.height, 800)
        let actualJPEG = try await queue.export(adjustment, source: source, bytes: bytes)
        try retain(actualJPEG, named: "codec-actual.jpg")
        let actual = try decodedJPEG(actualJPEG)
        try retain(actual.bytes, named: "codec-actual-decoded.png")
        let reference = try expectedFade(original)
        _ = try checkedJPEG(XCTUnwrap(referenceJPEG))
        try retain(reference.raster.bytes, named: "codec-reference-decoded.png")
        let delta = try maximumDelta(actual.rgba, reference.raster.rgba)
        let actualChannels = [UInt8](actual.rgba), expectedChannels = [UInt8](reference.raster.rgba)
        var changed = 0, aboveTwo = 0, squareError: Double = 0
        var channelCounts = [Int](repeating: 0, count: 4)
        for pixel in 0..<(1200 * 800) {
            var pixelChanged = false, pixelAboveTwo = false
            for channel in 0..<4 {
                let index = pixel * 4 + channel
                let difference = abs(Int(actualChannels[index]) - Int(expectedChannels[index]))
                pixelChanged = pixelChanged || difference > 0
                pixelAboveTwo = pixelAboveTwo || difference > 2
                if difference > 2 { channelCounts[channel] += 1 }
                if channel < 3 { squareError += Double(difference * difference) }
            }
            if pixelChanged { changed += 1 }
            if pixelAboveTwo { aboveTwo += 1 }
        }
        let report: [String: Any] = [
            "schema": "Celluloid.NativeCodecControl.1", "scope": "synthetic-pre-host-only",
            "public_parent": "a940bcdf8a92811210bcfacf84141dceb6c3fcd3",
            "operating_system": ProcessInfo.processInfo.operatingSystemVersionString,
            "source_sha256": sourceSHA256, "source": original.metadata,
            "sequence": ["Original preview", "Fade preview", "Fade export"],
            "actual": actual.metadata, "reference": reference.raster.metadata,
            "actual_jpeg_sha256": digest(actualJPEG), "reference_jpeg_sha256": reference.jpegSHA256,
            "max_channel_delta": delta, "allowed_max_channel_delta": 2,
            "changed_pixels": changed, "pixels_above_two": aboveTwo,
            "channels_above_two_rgba": channelCounts,
            "rgb_rmse": sqrt(squareError / Double(1200 * 800 * 3)),
            "pixel_contract_passed": delta <= 2,
            "photos_input_observed": false, "photos_submitted_jpeg_observed": false,
            "actual_export_prejpeg_observed": false,
            "srgb_icc_reference": lifecycleICC as Any? ?? NSNull(),
            "artifacts": retained]
        try retain(JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]), named: "codec-control.json")
        XCTAssertGreaterThan(try maximumDelta(reference.raster.rgba, original.rgba), 2,
            "The independent Fade reference must change the source")
        XCTAssertLessThanOrEqual(delta, 2, "Same-run independent Fade JPEG pixels differ; Photos host is not involved")
    }

    private func retain(_ data: Data, named name: String) throws {
        let limits: [String: Int] = ["codec-actual.jpg": 128 * 1024, "codec-reference.jpg": 128 * 1024,
            "codec-actual-decoded.png": 128 * 1024, "codec-reference-decoded.png": 128 * 1024,
            "codec-reference-prejpeg.png": 128 * 1024, "codec-control.json": 16 * 1024]
        guard let limit = limits[name], retained[name] == nil, !data.isEmpty, data.count <= limit,
              retainedBytes + data.count <= 512 * 1024 else { throw block("Fixed-name attachment size/count limit") }
        retainedBytes += data.count
        retained[name] = ["bytes": data.count, "sha256": digest(data)]
        let type = name.hasSuffix(".jpg") ? UTType.jpeg.identifier : name.hasSuffix(".png") ? UTType.png.identifier : UTType.json.identifier
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: type)
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func png(_ image: CGImage) throws -> Data {
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image,
            [kCGImagePropertyPNGDictionary: [kCGImagePropertyPNGInterlaceType: 0]] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw block("Control PNG encode failed") }
        return data as Data
    }

    private func decodedJPEG(_ bytes: Data) throws -> LifecycleRaster {
        try lifecycleRaster(png(checkedJPEG(bytes)), expectedFormat: UTType.png.identifier)
    }

    private func checkedJPEG(_ bytes: Data) throws -> CGImage {
        guard !bytes.isEmpty, bytes.count <= 128 * 1024 else { throw block("Control JPEG size bound failed") }
        let source = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let profile = try XCTUnwrap(image.colorSpace?.copyICCData()) as Data
        let expectedProfile = try XCTUnwrap(srgb.copyICCData()) as Data
        guard CGImageSourceGetCount(source) == 1, CGImageSourceGetType(source) as String? == UTType.jpeg.identifier,
              properties[kCGImagePropertyPixelWidth] as? Int == 1200,
              properties[kCGImagePropertyPixelHeight] as? Int == 800,
              (properties[kCGImagePropertyOrientation] as? Int ?? 1) == 1,
              properties[kCGImagePropertyDepth] as? Int == 8,
              properties[kCGImagePropertyProfileName] as? String != nil,
              image.width == 1200, image.height == 800, image.bitsPerComponent == 8,
              image.colorSpace?.model == .rgb, profile == expectedProfile else {
            throw block("Control JPEG format/dimensions/orientation/depth/sRGB mismatch")
        }
        return image
    }

    private func block(_ reason: String, operation: [String: Any]? = nil) -> NSError {
        NSError(domain: "Celluloid.NativeCodecControl", code: 1,
            userInfo: [NSLocalizedDescriptionKey: reason, "operation": operation ?? [:]])
    }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    // The following independent host helpers are copied literally from a940.
    // Only host-deadline checks are removed. expectedFade additionally retains
    // its own JPEG and pre-JPEG raster using marked, test-only captures.
    private func pngHeader(_ data: Data) throws -> (colorType: Int, profileEncoding: String) {
        let bytes = [UInt8](data)
        guard bytes.count >= 45, bytes.count <= 128 * 1024,
              Array(bytes.prefix(8)) == [137, 80, 78, 71, 13, 10, 26, 10] else { throw block("Required PNG signature/128 KiB bound failed") }
        func u32(_ offset: Int) -> Int {
            Int(bytes[offset]) << 24 | Int(bytes[offset + 1]) << 16 | Int(bytes[offset + 2]) << 8 | Int(bytes[offset + 3])
        }
        guard u32(8) == 13, String(bytes: bytes[12..<16], encoding: .ascii) == "IHDR",
              u32(16) == 1200, u32(20) == 800, bytes[24] == 8, [2, 6].contains(bytes[25]),
              bytes[26] == 0, bytes[27] == 0, bytes[28] == 0 else {
            throw block("Required PNG dimensions/depth/color type/interlace failed", operation: ["sha256": digest(data), "bytes": data.count])
        }
        var offset = 8, chunks = 0, srgb = 0, icc = 0, textChunks = 0
        while offset < bytes.count {
            guard offset <= bytes.count - 12, chunks < 64 else { throw block("PNG chunk framing limit") }
            let count = u32(offset)
            guard count <= bytes.count - offset - 12 else { throw block("Truncated PNG chunk") }
            let tag = String(bytes: bytes[(offset + 4)..<(offset + 8)], encoding: .ascii) ?? ""
            let protected = Array(bytes[(offset + 4)..<(offset + 8 + count)])
            let actualCRC = protected.withUnsafeBufferPointer { crc32(0, $0.baseAddress, uInt($0.count)) }
            guard actualCRC == uLong(u32(offset + 8 + count)) else { throw block("PNG chunk CRC mismatch before decode") }
            if tag == "iTXt" {
                textChunks += 1
                guard textChunks == 1 else { throw block("Duplicate iTXt before decode") }
                try admitInternationalText(Array(bytes[(offset + 8)..<(offset + 8 + count)]))
            }
            if tag == "sRGB" {
                guard count == 1, bytes[offset + 8] == 0 else { throw block("PNG sRGB rendering intent mismatch") }
                srgb += 1
            }
            if tag == "iCCP" {
                icc += 1
                guard icc == 1 else { throw block("Duplicate ICC profile before decode") }
                try admitICC(Array(bytes[(offset + 8)..<(offset + 8 + count)]), pngSHA256: digest(data))
            }
            guard ["IHDR", "sRGB", "iCCP", "gAMA", "cHRM", "pHYs", "eXIf", "iTXt", "IDAT", "IEND"].contains(tag) else {
                throw block("Unsupported PNG chunk before decode", operation: ["chunk": tag, "sha256": digest(data)])
            }
            guard !["acTL", "fcTL", "fdAT", "tRNS"].contains(tag) else { throw block("Animated/transparency PNG is outside the fixture contract") }
            offset += count + 12; chunks += 1
        }
        guard offset == bytes.count, (srgb == 1 && icc == 0) || (srgb == 0 && icc == 1) else {
            throw block("PNG profile missing/ambiguous; pixel conversion is not a fallback", operation: ["sha256": digest(data), "sRGB_chunks": srgb, "iCCP_chunks": icc])
        }
        return (Int(bytes[25]), srgb == 1 ? "srgb-chunk" : "icc-reference")
    }

    private func admitInternationalText(_ payload: [UInt8]) throws {
        do { try Self.validateInternationalText(payload) }
        catch { throw block("Malformed or oversized PNG iTXt structure before decode") }
    }

    private static func validateInternationalText(_ payload: [UInt8]) throws {
        // W3C PNG 11.3.3.4: inspect only the bounded envelope and UTF-8.
        // Text is never interpreted as XML/XMP, orientation or color authority.
        guard payload.count <= 16_384, let separator = payload.firstIndex(of: 0), (1...79).contains(separator),
              separator + 5 <= payload.count else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed/oversized PNG iTXt envelope"]) }
        let keyword = Array(payload[..<separator])
        guard keyword.allSatisfy({ (32...126).contains($0) || (161...255).contains($0) }),
              keyword.first != 32, keyword.last != 32,
              !zip(keyword, keyword.dropFirst()).contains(where: { pair in pair.0 == 32 && pair.1 == 32 }) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt keyword"]) }
        let flag = payload[separator + 1], method = payload[separator + 2]
        guard [0, 1].contains(flag), flag == 0 || method == 0,
              let languageEnd = payload[(separator + 3)...].firstIndex(of: 0),
              languageEnd + 1 < payload.count,
              let translatedEnd = payload[(languageEnd + 1)...].firstIndex(of: 0) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt compression/separators"]) }
        let language = payload[(separator + 3)..<languageEnd]
        guard language.allSatisfy({ $0 == 45 || (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) }),
              String(bytes: payload[(languageEnd + 1)..<translatedEnd], encoding: .utf8) != nil else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt language/translated bytes"]) }
        var text = Array(payload[(translatedEnd + 1)...])
        if flag == 1 {
            let compressed = text
            var output = [UInt8](repeating: 0, count: 16_385)
            var outputCount = uLongf(output.count), inputCount = uLong(compressed.count)
            let status = output.withUnsafeMutableBufferPointer { destination in
                compressed.withUnsafeBufferPointer { source in
                    uncompress2(destination.baseAddress, &outputCount, source.baseAddress, &inputCount)
                }
            }
            guard status == Z_OK, outputCount <= 16_384, inputCount == uLong(compressed.count) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "PNG iTXt bounded decompression failed"]) }
            text = Array(output.prefix(Int(outputCount)))
        }
        guard text.count <= 16_384, !text.contains(0), String(bytes: text, encoding: .utf8) != nil else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed/oversized PNG iTXt UTF-8"]) }
    }

    private func admitICC(_ payload: [UInt8], pngSHA256: String) throws {
        guard let separator = payload.firstIndex(of: 0), (1...79).contains(separator),
              separator + 2 < payload.count, payload[separator + 1] == 0 else {
            throw block("Malformed PNG ICC profile envelope before decode", operation: ["sha256": pngSHA256])
        }
        let compressed = Array(payload[(separator + 2)...])
        // Apple's public system zlib module links libz. uncompress2 admits
        // caller-sized storage and reports consumed input, so neither an ICC
        // bomb nor a trailing/concatenated stream reaches ImageIO.
        var output = [UInt8](repeating: 0, count: 4097)
        var outputCount = uLongf(output.count)
        var inputCount = uLong(compressed.count)
        let status = output.withUnsafeMutableBufferPointer { destination in
            compressed.withUnsafeBufferPointer { source in
                uncompress2(destination.baseAddress, &outputCount, source.baseAddress, &inputCount)
            }
        }
        guard status == Z_OK, outputCount > 0, outputCount <= 4096, inputCount == uLong(compressed.count) else {
            throw block("PNG ICC bounded decompression/profile admission failed before decode",
                operation: ["sha256": pngSHA256, "zlib_status": status, "decoded_bytes": Int(outputCount), "consumed_bytes": Int(inputCount)])
        }
        let actual = Data(output.prefix(Int(outputCount)))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let reference = try XCTUnwrap(srgb.copyICCData()) as Data
        guard !reference.isEmpty, reference.count <= 4096, actual == reference else {
            throw block("PNG ICC bytes differ from independent sRGB reference; pixels were not compared",
                operation: ["sha256": pngSHA256, "icc_sha256": digest(actual)])
        }
        lifecycleICC = ["bytes": reference.count, "sha256": digest(reference)]
    }

    private func bitmap() throws -> CGContext {
        try XCTUnwrap(CGContext(data: nil, width: 1200, height: 800, bitsPerComponent: 8, bytesPerRow: 1200 * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue))
    }

    private func lifecycleRaster(_ data: Data, expectedFormat: String) throws -> LifecycleRaster {
        let header = try pngHeader(data)
        let imageSource = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary))
        guard CGImageSourceGetCount(imageSource) == 1,
              CGImageSourceGetType(imageSource) as String? == expectedFormat,
              let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any],
              properties[kCGImagePropertyPixelWidth] as? Int == 1200,
              properties[kCGImagePropertyPixelHeight] as? Int == 800,
              (properties[kCGImagePropertyOrientation] as? Int ?? 1) == 1,
              properties[kCGImagePropertyDepth] as? Int == 8,
              let image = CGImageSourceCreateImageAtIndex(imageSource, 0, nil), image.width == 1200, image.height == 800,
              image.bitsPerComponent == 8, image.colorSpace?.model == .rgb else {
            throw block("Export format/dimensions/orientation/depth mismatch", operation: ["sha256": digest(data), "bytes": data.count])
        }
        let context = try bitmap()
        context.interpolationQuality = .none
        context.draw(image, in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let rgba = Data(bytes: try XCTUnwrap(context.data), count: 1200 * 800 * 4)
        guard stride(from: 3, to: rgba.count, by: 4).allSatisfy({ rgba[$0] == 255 }) else { throw block("Export alpha mismatch; opaque source required") }
        let metadata: [String: Any] = ["bytes": data.count, "sha256": digest(data), "rgba_sha256": digest(rgba),
            "format": expectedFormat, "width": 1200, "height": 800, "bit_depth": 8,
            "color_type": header.colorType, "interlace": 0, "orientation": 1, "profile": "sRGB",
            "profile_encoding": header.profileEncoding, "alpha": "opaque"]
        return LifecycleRaster(bytes: data, rgba: rgba, metadata: metadata)
    }

    private func expectedFade(_ original: LifecycleRaster) throws -> (raster: LifecycleRaster, jpegSHA256: String) {
        // Deliberately independent from production filter maps, renderer and codec.
        // Match only their published sRGB/opaque/ImageIO JPEG-quality contract.
        let source = try XCTUnwrap(CGImageSourceCreateWithData(original.bytes as CFData,
            [kCGImageSourceShouldCache: false, kCGImageSourceShouldCacheImmediately: false] as CFDictionary))
        let cg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary))
        let input = CIImage(cgImage: cg)
        let filter = try XCTUnwrap(CIFilter(name: "CIPhotoEffectInstant", parameters: [kCIInputImageKey: input]))
        let filtered = try XCTUnwrap(filter.outputImage).cropped(to: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let ci = CIContext(options: [.outputColorSpace: srgb, .cacheIntermediates: false])
        defer { ci.clearCaches() }
        let output = try XCTUnwrap(ci.createCGImage(filtered, from: filtered.extent, format: .RGBA8, colorSpace: srgb))
        let composition = try bitmap()
        composition.interpolationQuality = .high
        composition.draw(output, in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let flattened = try bitmap()
        flattened.interpolationQuality = .high
        flattened.setFillColor(CGColor(gray: 1, alpha: 1))
        flattened.fill(CGRect(x: 0, y: 0, width: 1200, height: 800))
        flattened.draw(try XCTUnwrap(composition.makeImage()), in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let jpeg = NSMutableData()
        let encoder = try XCTUnwrap(CGImageDestinationCreateWithData(jpeg, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(encoder, try XCTUnwrap(flattened.makeImage()), [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
        guard CGImageDestinationFinalize(encoder), jpeg.length > 0, jpeg.length <= 16 * 1024 * 1024 else { throw block("Independent JPEG reference encode failed") }
        try retain(jpeg as Data, named: "codec-reference.jpg") // CONTROL_CAPTURE
        referenceJPEG = jpeg as Data // CONTROL_CAPTURE
        try retain(self.png(try XCTUnwrap(flattened.makeImage())), named: "codec-reference-prejpeg.png") // CONTROL_CAPTURE
        let decoded = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let decodedImage = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoded, 0, nil))
        guard decodedImage.width == 1200, decodedImage.height == 800 else { throw block("Independent JPEG reference dimensions changed") }
        let png = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(png, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, decodedImage,
            [kCGImagePropertyPNGDictionary: [kCGImagePropertyPNGInterlaceType: 0]] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw block("Independent PNG reference encode failed") }
        return (try lifecycleRaster(png as Data, expectedFormat: UTType.png.identifier), digest(jpeg as Data))
    }

    private func maximumDelta(_ lhs: Data, _ rhs: Data) throws -> Int {
        guard lhs.count == 1200 * 800 * 4, lhs.count == rhs.count else { throw block("Pixel comparison size mismatch") }
        var maximum = 0
        for index in lhs.indices { maximum = max(maximum, abs(Int(lhs[index]) - Int(rhs[index]))) }
        return maximum
    }
}
