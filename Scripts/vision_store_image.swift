// Host-only ImageIO validation and optional same-pixel-size JPEG encoding.
// No crop, scale, drawing, compositor, UI synthesis, or product modification.
import Foundation
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers

func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw NSError(domain: "CelluloidStoreImage", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
func decode(_ path: String) throws -> CGImage {
    let url = URL(fileURLWithPath: path)
    let source = try { () throws -> CGImageSource in
        guard let value = CGImageSourceCreateWithURL(url as CFURL, nil) else { throw NSError(domain: "JPEGDecode", code: 1) }
        return value
    }()
    try require(CGImageSourceGetType(source) as String? == UTType.jpeg.identifier, "Expected original JPEG")
    try require(CGImageSourceGetCount(source) == 1, "Expected one image")
    guard let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] else { throw NSError(domain: "JPEGProperties", code: 1) }
    try require(props[kCGImagePropertyPixelWidth] as? Int == 3840 && props[kCGImagePropertyPixelHeight] as? Int == 2160, "Expected native 3840 x 2160; no resize allowed")
    try require((props[kCGImagePropertyOrientation] as? Int ?? 1) == 1, "Unexpected orientation")
    guard let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary) else { throw NSError(domain: "JPEGDecode", code: 2) }
    try require(image.width == 3840 && image.height == 2160 && image.bitsPerComponent == 8 && image.colorSpace?.model == .rgb, "Expected decoded eight-bit RGB")
    try require([CGImageAlphaInfo.none, .noneSkipFirst, .noneSkipLast].contains(image.alphaInfo), "Alpha is forbidden")
    return image
}
do {
    let args = Array(CommandLine.arguments.dropFirst())
    try require(args.count == 2 || args.count == 4, "Usage: --inspect input | --encode input output quality")
    try require(args[0] == "--inspect" && args.count == 2 || args[0] == "--encode" && args.count == 4, "Invalid mode")
    let image = try decode(args[1])
    var output: [String: Any] = ["format": "JPEG", "width": image.width, "height": image.height, "mode": "RGB", "alpha": false, "decoded": true]
    if args[0] == "--encode" {
        let quality = Int(args[3]) ?? -1
        try require([65, 45, 30].contains(quality), "Only fixed quality ladder is allowed")
        try require(!FileManager.default.fileExists(atPath: args[2]), "Do not overwrite output")
        guard let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[2]) as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { throw NSError(domain: "JPEGDestination", code: 1) }
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: Double(quality) / 100] as CFDictionary)
        try require(CGImageDestinationFinalize(destination), "JPEG encoding failed")
        _ = try decode(args[2])
        output["quality"] = quality
        output["provenance"] = "Same-size lossy derivative; original JPEG bytes preserved separately"
    }
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    fputs("Celluloid Store image failure: \(error)\n", stderr)
    exit(1)
}
