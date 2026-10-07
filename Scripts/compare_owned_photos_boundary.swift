// Independent post-host diagnostic. No Photos import, UI, production renderer,
// process discovery, private library access, acceptance override or extra retry.
import Foundation
import CoreGraphics
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import CryptoKit
import Dispatch
import Darwin

struct Invalid: Error { let message: String }
func require(_ ok: Bool, _ message: String) throws { if !ok { throw Invalid(message: message) } }
func unwrap<T>(_ value: T?) throws -> T { guard let value else { throw Invalid(message: "missing native value") }; return value }
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
let started = DispatchTime.now().uptimeNanoseconds
func check() throws { try require(DispatchTime.now().uptimeNanoseconds - started <= 10_000_000_000, "checked comparison budget") }
let size = CGRect(x: 0, y: 0, width: 1200, height: 800)
let srgb = try unwrap(CGColorSpace(name: CGColorSpace.sRGB))
func bitmap() throws -> CGContext {
    try unwrap(CGContext(data: nil, width: 1200, height: 800, bitsPerComponent: 8, bytesPerRow: 1200 * 4,
        space: srgb, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue))
}
func read(_ folder: Int32, _ name: String, _ cap: Int) throws -> Data {
    try check()
    let fd = openat(folder, name, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW)
    try require(fd >= 0, "owned input open"); defer { close(fd) }
    var before = stat()
    try require(fstat(fd, &before) == 0 && before.st_nlink == 1 && before.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG)
        && before.st_size > 0 && before.st_size <= off_t(cap), "owned input type/size")
    var data = Data(count: Int(before.st_size))
    let expected = data.count
    let count = data.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress!, expected) }
    var after = stat(), entry = stat(), extra: UInt8 = 0
    try require(count == expected && Darwin.read(fd, &extra, 1) == 0 && fstat(fd, &after) == 0
        && fstatat(folder, name, &entry, AT_SYMLINK_NOFOLLOW) == 0, "owned input read")
    func same(_ a: stat, _ b: stat) -> Bool {
        a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size && a.st_mode == b.st_mode
            && a.st_nlink == b.st_nlink && a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec
            && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec && a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec
            && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
    }
    try require(same(before, after) && same(before, entry), "changed input")
    try check(); return data
}
func write(_ folder: Int32, _ name: String, _ bytes: Data, _ cap: Int) throws {
    try check(); try require(!bytes.isEmpty && bytes.count <= cap, "comparison output cap")
    let fd = openat(folder, name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0o600)
    try require(fd >= 0, "exclusive comparison output"); defer { close(fd) }
    try require(bytes.withUnsafeBytes { Darwin.write(fd, $0.baseAddress!, bytes.count) } == bytes.count, "comparison output write")
}
struct Raster { let raw: Data; let image: CGImage; let rgba: Data; let metadata: [String: Any] }
func decode(_ data: Data) throws -> Raster {
    try check()
    let source = try unwrap(CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary))
    let kind = try unwrap(CGImageSourceGetType(source)) as String
    let props = try unwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
    try require(CGImageSourceGetCount(source) == 1 && [UTType.png.identifier, UTType.jpeg.identifier].contains(kind)
        && props[kCGImagePropertyPixelWidth] as? Int == 1200 && props[kCGImagePropertyPixelHeight] as? Int == 800
        && (props[kCGImagePropertyOrientation] as? Int ?? 1) == 1 && props[kCGImagePropertyDepth] as? Int == 8,
        "unsupported actual boundary format/geometry")
    let image = try unwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
    try require(image.width == 1200 && image.height == 800 && image.bitsPerComponent == 8 && image.colorSpace?.model == .rgb,
        "unsupported actual boundary RGB image")
    let context = try bitmap(); context.interpolationQuality = .none; context.draw(image, in: size)
    let rgba = Data(bytes: try unwrap(context.data), count: 1200 * 800 * 4)
    try require(stride(from: 3, to: rgba.count, by: 4).allSatisfy { rgba[$0] == 255 }, "nonopaque boundary image")
    let icc: Data? = image.colorSpace.flatMap { $0.copyICCData() }.map { $0 as Data }
    let metadata: [String: Any] = ["bytes": data.count, "sha256": digest(data), "rgba_sha256": digest(rgba),
        "format": kind, "width": 1200, "height": 800, "orientation": 1, "depth": 8,
        "profile_name": props[kCGImagePropertyProfileName] as? String ?? "unspecified",
        "icc_sha256": icc.map { digest($0) } ?? "unavailable", "canonical_decode": "ImageIO to opaque sRGB RGBA8; no resampling"]
    return Raster(raw: data, image: image, rgba: rgba, metadata: metadata)
}
func png(_ image: CGImage) throws -> Data {
    let bytes = NSMutableData()
    let encoder = try unwrap(CGImageDestinationCreateWithData(bytes, UTType.png.identifier as CFString, 1, nil))
    CGImageDestinationAddImage(encoder, image, [kCGImagePropertyPNGDictionary: [kCGImagePropertyPNGInterlaceType: 0]] as CFDictionary)
    try require(CGImageDestinationFinalize(encoder), "PNG encode"); return bytes as Data
}
// Same independent a940 Fade graph and quality as the unchanged historical
// gate. The input here is captured I.raw, never the retained fixture F.
func expectedFade(_ original: Raster) throws -> (Raster, String) {
    try check()
    let source = try unwrap(CGImageSourceCreateWithData(original.raw as CFData,
        [kCGImageSourceShouldCache: false, kCGImageSourceShouldCacheImmediately: false] as CFDictionary))
    let cg = try unwrap(CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary))
    let input = CIImage(cgImage: cg)
    let filter = try unwrap(CIFilter(name: "CIPhotoEffectInstant", parameters: [kCIInputImageKey: input]))
    let filtered = try unwrap(filter.outputImage).cropped(to: size)
    let ci = CIContext(options: [.outputColorSpace: srgb, .cacheIntermediates: false]); defer { ci.clearCaches() }
    let output = try unwrap(ci.createCGImage(filtered, from: filtered.extent, format: .RGBA8, colorSpace: srgb))
    let composition = try bitmap(); composition.interpolationQuality = .high; composition.draw(output, in: size)
    let flattened = try bitmap(); flattened.interpolationQuality = .high
    flattened.setFillColor(CGColor(gray: 1, alpha: 1)); flattened.fill(size)
    flattened.draw(try unwrap(composition.makeImage()), in: size)
    let jpeg = NSMutableData()
    let encoder = try unwrap(CGImageDestinationCreateWithData(jpeg, UTType.jpeg.identifier as CFString, 1, nil))
    CGImageDestinationAddImage(encoder, try unwrap(flattened.makeImage()), [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
    try require(CGImageDestinationFinalize(encoder) && jpeg.length > 0 && jpeg.length <= 65_536, "independent JPEG cap")
    let decoded = try decode(jpeg as Data)
    return (try decode(png(decoded.image)), digest(jpeg as Data))
}
func metrics(_ a: Raster, _ b: Raster) throws -> [String: Any] {
    try check(); var maximum = 0, changed = 0, above = 0; var squared: Double = 0
    for pixel in 0..<(1200 * 800) {
        var pixelMax = 0
        for channel in 0..<4 {
            let index = pixel * 4 + channel, delta = abs(Int(a.rgba[index]) - Int(b.rgba[index]))
            pixelMax = max(pixelMax, delta); if channel < 3 { squared += Double(delta * delta) }
        }
        maximum = max(maximum, pixelMax); if pixelMax > 0 { changed += 1 }; if pixelMax > 2 { above += 1 }
    }
    try check()
    return ["max_channel_delta": maximum, "changed_pixels": changed, "pixels_above_two": above,
        "rgb_rmse": sqrt(squared / Double(1200 * 800 * 3)), "allowed_max_channel_delta": 2]
}
try require(CommandLine.arguments.count == 2, "one admitted owned comparison folder required")
let folder = open(CommandLine.arguments[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
try require(folder >= 0, "comparison folder"); defer { close(folder) }
let input = try decode(read(folder, "input.bytes", 65_536))
let intended = try decode(read(folder, "intended.jpg", 65_536))
try require(intended.metadata["format"] as? String == UTType.jpeg.identifier, "intended JPEG format")
let fixture = try decode(read(folder, "lifecycle-source.png", 131_072))
try require(digest(fixture.raw) == "6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772", "fixture hash")
let historical = try decode(read(folder, "lifecycle-expected-save.png", 131_072))
let saved = try decode(read(folder, "lifecycle-saved.png", 131_072))
let (reference, referenceJPEG) = try expectedFade(input)
let report: [String: Any] = ["schema": "Celluloid.OwnedPhotosBoundaryComparison.1", "acceptance": false,
    "input": input.metadata, "intended": intended.metadata, "saved": saved.metadata,
    "fixture": fixture.metadata, "historical_reference": historical.metadata, "input_reference": reference.metadata,
    "input_raw_equals_fixture": input.raw == fixture.raw,
    "input_vs_fixture": try metrics(input, fixture), "intended_vs_input_reference": try metrics(intended, reference),
    "saved_vs_intended": try metrics(saved, intended), "saved_vs_historical_fixture_reference": try metrics(saved, historical),
    "input_reference_jpeg_sha256": referenceJPEG, "intended_jpeg_sha256": digest(intended.raw),
    "complete_host_e2e": false, "photos_internal_storage_observed": false, "performance_acceptance": false]
try write(folder, "intended-decoded.png", png(intended.image), 32_768)
try write(folder, "input-reference.png", reference.raw, 32_768)
try write(folder, "boundary-comparison.json", JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]), 8192)
