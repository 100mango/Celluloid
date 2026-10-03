import XCTest
import UIKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidVision

final class NativeVisionTests: XCTestCase {
    func testNativeVisionDocumentImportRenderSaveReopenAndExport() throws {
        let bitmap = try RasterCodec.bitmap(width: 320, height: 240)
        bitmap.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [0.15,0.5,0.85,1])))
        bitmap.fill(CGRect(x: 0, y: 0, width: 320, height: 240))
        let data = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        var document = NativeDocument(); try document.replaceSources([("Synthetic.png", data)])
        document.recipe.filter = .fade
        document.recipe.overlays = [Overlay(bubble: .say1, text: "Vision 世界")]
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".celluloid")
        defer { try? FileManager.default.removeItem(at: folder) }
        try document.archive().write(to: folder, options: .atomic, originalContentsURL: nil)
        let restored = try NativeDocument(wrapper: FileWrapper(url: folder, options: .immediate))
        XCTAssertEqual(restored, document)
        let output = try RecipeRenderer().render(restored.recipe, sources: restored.originals)
        let exported = try RasterCodec.encode(output, as: .png)
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".png")
        defer { try? FileManager.default.removeItem(at: file) }
        try exported.write(to: file, options: .atomic)
        XCTAssertEqual(try Data(contentsOf: file), exported)
        XCTAssertEqual(try RasterCodec.metadata(exported).pixelWidth, 320)
        print("VISION_NATIVE_DOCUMENT_PIPELINE verified import/render/package-reopen/export-readback; programmatic hosted integration, not system-picker traversal")
    }
    @MainActor func testNativeVisionExecutableAndSceneAreLive() throws {
        XCTAssertEqual(Bundle.main.bundleIdentifier, "Mango.Celluloid")
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "xrsimulator")
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        XCTAssertFalse(scenes.isEmpty)
        print("VISION_NATIVE_RUNTIME bundle=\(Bundle.main.bundleURL.path) scenes=\(scenes.count) platform=\(Bundle.main.infoDictionary?["DTPlatformName"] ?? "")")
    }
}
