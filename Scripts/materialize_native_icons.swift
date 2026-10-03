import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

// Build-derived packaging only: retains the existing published brand, never stretches it.
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let sourcePath = "Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png"
let sourceBytes = try Data(contentsOf: root.appendingPathComponent(sourcePath))
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
precondition(digest(sourceBytes) == "f4f7ca4326be0a7f017339545367ecfbe1fdae58da36cd3368305b056ce7c614")
let source = CGImageSourceCreateWithData(sourceBytes as CFData, nil)!
let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
precondition(image.width == 1024 && image.height == 1024)
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let corner = CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4, space: space,
                       bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)!
corner.draw(image, in: CGRect(x: 0, y: 0, width: 1024, height: 1024))
let rgba = corner.data!.assumingMemoryBound(to: UInt8.self)
let backdrop = CGColor(srgbRed: CGFloat(rgba[0])/255, green: CGFloat(rgba[1])/255, blue: CGFloat(rgba[2])/255, alpha: 1)
var files: [[String: Any]] = []
func record(_ relative: String, width: Int, height: Int, kind: String) throws {
    let bytes = try Data(contentsOf: root.appendingPathComponent(relative))
    files.append(["path": relative, "width": width, "height": height, "sha256": digest(bytes), "bytes": bytes.count, "derivation": kind])
}
func copy(_ relative: String) throws {
    try sourceBytes.write(to: root.appendingPathComponent(relative), options: .atomic)
    try record(relative,width:1024,height:1024,kind:"byte-identical original brand PNG")
}
func render(_ relative: String, width: Int, height: Int, artwork: Bool) throws {
    let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width*4, space: space,
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)!
    context.clear(CGRect(x:0,y:0,width:width,height:height))
    if artwork {
        context.setFillColor(backdrop);context.fill(CGRect(x:0,y:0,width:width,height:height))
        let side = min(width,height);context.interpolationQuality = .high
        context.draw(image,in:CGRect(x:CGFloat(width-side)/2,y:CGFloat(height-side)/2,width:CGFloat(side),height:CGFloat(side)))
    }
    let url = root.appendingPathComponent(relative)
    let destination = CGImageDestinationCreateWithURL(url as CFURL,UTType.png.identifier as CFString,1,nil)!
    CGImageDestinationAddImage(destination,context.makeImage()!,nil);precondition(CGImageDestinationFinalize(destination))
    try record(relative,width:width,height:height,kind:artwork ? "aspect-fit original over sampled original background; no stretching" : "transparent foreground; brand remains intact in back layer")
}
try copy("Platforms/watchOS/Assets.xcassets/AppIcon.appiconset/Generated-1024.png")
let vision = "Platforms/visionOS/Assets.xcassets/AppIcon.solidimagestack/"
try copy(vision+"Back.solidimagestacklayer/Content.imageset/Generated.png")
try render(vision+"Front.solidimagestacklayer/Content.imageset/Generated.png",width:1024,height:1024,artwork:false)
let tv = "Platforms/tvOS/Assets.xcassets/AppIcon.brandassets/"
for (name,width,height,scale) in [("Small",400,240,"1x"),("Small",800,480,"2x"),("Large",1280,768,"1x")] {
    for layer in ["Front","Back"] { try render(tv+"\(name).imagestack/\(layer).imagestacklayer/Content.imageset/Generated-\(scale).png",width:width,height:height,artwork:layer=="Back") }
}
for (name,width,height) in [("TopShelf",1920,720),("TopShelfWide",2320,720)] { try render(tv+"\(name).imageset/Generated.png",width:width,height:height,artwork:true) }
let report: [String: Any] = ["source_path": sourcePath,"source_sha256":digest(sourceBytes),"source_commit":ProcessInfo.processInfo.environment["GITHUB_SHA"] ?? "local", "files":files]
let output = URL(fileURLWithPath: ProcessInfo.processInfo.environment["RUNNER_TEMP"]!).appendingPathComponent("native-icon-provenance-runtime.json")
try JSONSerialization.data(withJSONObject: report,options:[.prettyPrinted,.sortedKeys]).write(to:output)
print("NATIVE_ICON_PACKAGING \(files.count) derived files; original source SHA256 \(digest(sourceBytes)); \(output.path)")
