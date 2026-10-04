import XCTest
import CryptoKit
import CoreGraphics
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
        let record: [String: String] = ["identifier": MacPhotoAdjustment.identifier, "version": MacPhotoAdjustment.version,
            "name": "manufactured-affine", "sha256": digest(bytes), "base64": bytes.base64EncodedString(),
            "sourceSHA256": digest(sourceBytes), "sourceBase64": sourceBytes.base64EncodedString(),
            "renderedSHA256": digest(rendered), "renderedBase64": rendered.base64EncodedString()]
        print("MAC_LAYER_ADJUSTMENT_FIXTURE " + String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
        let decoded = try MacPhotoAdjustment.decode(bytes)
        XCTAssertEqual(decoded.bubbles[0].transform, bubble.transform); XCTAssertEqual(decoded.stickers[0].bounds, sticker.bounds)
        // This is NOT itself UIKit interoperability proof. The matching phone
        // test consumes these actual emitted bytes through its original reader.
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
}
