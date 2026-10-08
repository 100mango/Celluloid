import Foundation
import CoreImage
import CoreGraphics
import ImageIO
import CryptoKit

// Independently evaluate the documented historical effects on the known fixture.
// No app renderer, recipe decoder, production proof helper or output-as-input.
func require(_ condition: @autoclosure () -> Bool, _ detail: String) throws {
    if !condition() { throw NSError(domain: "TVFilterOracle", code: 1, userInfo: [NSLocalizedDescriptionKey: detail]) }
}
func decoded(_ bytes: Data) throws -> CGImage {
    guard let source = CGImageSourceCreateWithData(bytes as CFData, nil), let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "TVFilterOracle", code: 2)
    }
    return image
}
func rgba(_ image: CGImage) throws -> [UInt8] {
    guard let space = CGColorSpace(name: CGColorSpace.sRGB), let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: image.width * 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { throw NSError(domain: "TVFilterOracle", code: 3) }
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return Array(UnsafeBufferPointer(start: context.data!.assumingMemoryBound(to: UInt8.self), count: image.width * image.height * 4))
}
let fixture = URL(fileURLWithPath: CommandLine.arguments[1]), folder = URL(fileURLWithPath: CommandLine.arguments[2])
let inputBytes = try Data(contentsOf: fixture), source = try decoded(inputBytes), sourcePixels = try rgba(source)
let input = CIImage(cgImage: source), context = CIContext(), colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
var ids = Set<String>(), previous: [UInt8]?
for (index, effect) in ["CIPhotoEffectInstant", "CIPhotoEffectChrome"].enumerated() {
    let number = index + 1, imageURL = folder.appendingPathComponent("\(number).png"), metaURL = folder.appendingPathComponent("\(number).json")
    let fileSize = try imageURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
    try require(fileSize <= 5_000_000, "Oversized proof image")
    let metaSize = try metaURL.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
    try require(metaSize <= 16_384, "Oversized proof metadata")
    let actualBytes = try Data(contentsOf: imageURL)
    try require(actualBytes.count <= 5_000_000, "Readback grew beyond proof bound")
    let metadata = try JSONSerialization.jsonObject(with: Data(contentsOf: metaURL)) as! [String: Any]
    let hash = SHA256.hash(data: actualBytes).map { String(format: "%02x", $0) }.joined()
    try require(metadata["sha256"] as? String == hash, "Readback proof hash mismatch")
    let id = metadata["photosAssetIdentifier"] as? String ?? ""
    try require(!id.isEmpty && ids.insert(id).inserted, "Two distinct Photos saves required")
    let actual = try decoded(actualBytes)
    try require(actual.width == 1200 && actual.height == 800, "Actual Photos output dimensions changed")
    let graph = input.applyingFilter(effect).cropped(to: input.extent)
    guard let expected = context.createCGImage(graph, from: input.extent, format: .RGBA8, colorSpace: colorSpace) else { throw NSError(domain: "TVFilterOracle", code: 4) }
    let actualPixels = try rgba(actual), expectedPixels = try rgba(expected)
    let maximumDifference = zip(actualPixels, expectedPixels).map { abs(Int($0) - Int($1)) }.max() ?? 255
    let changedFromOriginal = zip(actualPixels, sourcePixels).filter { $0 != $1 }.count
    try require(maximumDifference <= 2, "Requested effect does not match real Photos pixels: \(effect), maximum difference \(maximumDifference)")
    try require(changedFromOriginal > actualPixels.count / 10, "Requested non-default effect left source unchanged")
    if let previous { try require(previous != actualPixels, "Second changed effect returned stale first output") }
    previous = actualPixels
    print("TV_NATIVE_FILTER_ORACLE effect=\(effect) fullPixels=960000 maximumChannelDifference=\(maximumDifference) changedBytes=\(changedFromOriginal) distinctPhotosAsset=true readbackSHA256=\(hash)")
}
