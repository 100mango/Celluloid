import Foundation
import CoreGraphics
import CoreImage
import ImageIO
import CryptoKit

// Host-side independent oracle for the actually refetched Photos PNG. It does
// not import the app renderer, processor or persisted recipe decoder.
func require(_ value: @autoclosure () -> Bool, _ detail: String) throws {
    if !value() { throw NSError(domain: "PhoneOutputOracle", code: 1, userInfo: [NSLocalizedDescriptionKey: detail]) }
}
func bounded(_ url: URL, maximum: Int) throws -> Data {
    let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
    try require(size <= maximum, "Proof size preflight")
    let data = try Data(contentsOf: url); try require(data.count <= maximum, "Proof grew beyond bound")
    return data
}
func decode(_ data: Data) throws -> CGImage {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil), image.width * image.height <= 2_000_000 else {
        throw NSError(domain: "PhoneOutputOracle", code: 2)
    }
    return image
}
func pixels(_ image: CGImage) throws -> [UInt8] {
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8,
                                  bytesPerRow: image.width * 4, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { throw NSError(domain: "PhoneOutputOracle", code: 3) }
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return Array(UnsafeBufferPointer(start: context.data!.assumingMemoryBound(to: UInt8.self), count: image.width * image.height * 4))
}
let fixture = URL(fileURLWithPath: CommandLine.arguments[1]), container = URL(fileURLWithPath: CommandLine.arguments[2])
let source = try bounded(fixture, maximum: 5_000_000), inputCG = try decode(source)
let proof = container.appendingPathComponent("Library/Caches/PhoneOutputProof")
let data = try bounded(proof.appendingPathComponent("photos-output.png"), maximum: 5_000_000)
let info = try JSONSerialization.jsonObject(with: bounded(proof.appendingPathComponent("photos-output.json"), maximum: 16_384)) as! [String: Any]
let hash: (Data) -> String = { SHA256.hash(data: $0).map { String(format: "%02x", $0) }.joined() }
try require(info["requestID"] as? String == "58B78AAA-30B8-44DB-BD4F-10762900A001", "Wrong request association")
try require(info["filter"] as? String == "Fade" && info["sourceSHA256"] as? String == hash(source), "Wrong request filter/source")
try require(info["sha256"] as? String == hash(data) && !(info["photosAssetIdentifier"] as? String ?? "").isEmpty, "Actual Photos readback hash/identity")
let output = try decode(data)
try require(output.width == 1200 && output.height == 800, "Actual output dimensions")
let input = CIImage(cgImage: inputCG), graph = input.applyingFilter("CIPhotoEffectInstant").cropped(to: input.extent)
guard let expected = CIContext().createCGImage(graph, from: input.extent, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!) else { throw NSError(domain: "PhoneOutputOracle", code: 4) }
let actual = try pixels(output), wanted = try pixels(expected), original = try pixels(inputCG)
let maximum = zip(actual, wanted).map { abs(Int($0) - Int($1)) }.max() ?? 255
let changed = zip(actual, original).filter { $0 != $1 }.count
try require(maximum <= 2 && changed > actual.count / 10, "Independent requested Fade output failed: \(maximum)")
let store = container.appendingPathComponent("Library/Application Support/WatchProcessingResults")
let records = try JSONSerialization.jsonObject(with: bounded(store.appendingPathComponent("index.json"), maximum: 128 * 1024)) as! [[String: Any]]
let pending = try FileManager.default.contentsOfDirectory(atPath: store.appendingPathComponent("Pending").path)
try require(records.isEmpty && pending.isEmpty, "Explicit UI deletion did not persist after relaunch")
try require(!FileManager.default.fileExists(atPath: store.appendingPathComponent("58B78AAA-30B8-44DB-BD4F-10762900A001.png").path), "Local completed image was not removed")
print("PHONE_COMPANION_OUTPUT_ORACLE fullPixels=960000 maximumChannelDifference=\(maximum) changedBytes=\(changed) readbackSHA256=\(hash(data)) localDeletionVerified=true physicalTransport=false")
