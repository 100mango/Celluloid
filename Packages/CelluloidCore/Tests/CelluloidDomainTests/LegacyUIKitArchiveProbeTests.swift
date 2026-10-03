import XCTest
import Foundation
import CryptoKit

/// Compatibility probe only. No native document/editor imports or writes Photos 1.0 data.
/// Fixtures are synthetic, actually archived by UIKit on iOS27; provenance is bundled.
final class LegacyUIKitArchiveProbeTests: XCTestCase {
    func testActualUIKitArchivesDecodeAndRetainAbsoluteGeometryOnMac() throws {
        #if os(macOS)
        for name in ["legacy-points", "reference-canvas"] {
            let archiveURL = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "base64"))
            let archive = try XCTUnwrap(Data(base64Encoded: Data(contentsOf: archiveURL), options: .ignoreUnknownCharacters))
            let jsonURL = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "json"))
            let expected = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: jsonURL)) as? [String: Any])
            let hash = SHA256.hash(data: archive).map { String(format: "%02x", $0) }.joined()
            XCTAssertEqual(hash, expected["sha256"] as? String)
            let classes: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
            let root = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: classes, from: archive) as? [String: Any])
            XCTAssertEqual(root["filterType"] as? String, "Chrome")
            let bubble = try XCTUnwrap((root["bubbles"] as? [[String: Any]])?.first)
            let sticker = try XCTUnwrap((root["stickers"] as? [[String: Any]])?.first)
            XCTAssertEqual(bubble["asset"] as? String, "say1")
            XCTAssertEqual(bubble["content"] as? String, "Hello, 世界 🎬")
            XCTAssertEqual(sticker["imageName"] as? String, "32")
            try assertGeometry(bubble, expected: XCTUnwrap(expected["bubble"] as? [String: Any]))
            try assertGeometry(sticker, expected: XCTUnwrap(expected["sticker"] as? [String: Any]))
            let reference = expected["referenceCanvasSize"] as? [Double] ?? []
            if reference.isEmpty { XCTAssertNil(root["referenceCanvasSize"]) }
            else { XCTAssertEqual(try components(root["referenceCanvasSize"], count: 2), reference) }
            // This output is ONLY a roundtrip candidate for UIKit to verify. Successful
            // Mac re-encoding alone is explicitly not proof of UIKit compatibility.
            let candidate = try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true)
            let candidateHash = SHA256.hash(data: candidate).map { String(format: "%02x", $0) }.joined()
            print("MAC_LEGACY_CANDIDATE name=\(name) bytes=\(candidate.count) sha256=\(candidateHash)")
            let base64 = candidate.base64EncodedString()
            for (index, start) in stride(from: 0, to: base64.count, by: 160).enumerated() {
                let a = base64.index(base64.startIndex, offsetBy: start)
                let b = base64.index(a, offsetBy: min(160, base64.count - start))
                print("MAC_LEGACY_BYTES name=\(name) chunk=\(index) data=\(base64[a..<b])")
            }
        }
        #else
        throw XCTSkip("This gate requires native macOS decoding of UIKit-produced archive bytes")
        #endif
    }
    private func assertGeometry(_ object: [String: Any], expected: [String: Any]) throws {
        for (key, count) in [("center",2),("bounds",4),("transform",6)] {
            XCTAssertEqual(try components(object[key], count: count), expected[key] as? [Double])
        }
    }
    private func components(_ object: Any?, count: Int) throws -> [Double] {
        let value = try XCTUnwrap(object as? NSValue)
        let encoding = String(cString: value.objCType)
        let expectedTypes: [Int: Set<String>] = [
            2: ["{CGPoint=dd}","{_NSPoint=dd}","{CGSize=dd}","{_NSSize=dd}"],
            4: ["{CGRect={CGPoint=dd}{CGSize=dd}}","{_NSRect={_NSPoint=dd}{_NSSize=dd}}"],
            6: ["{CGAffineTransform=dddddd}"]
        ]
        guard expectedTypes[count]?.contains(encoding) == true else {
            XCTFail("Unexpected archive geometry encoding: \(encoding)")
            throw CocoaError(.coderReadCorrupt)
        }
        var result = [Double](repeating: 0, count: count)
        result.withUnsafeMutableBytes { value.getValue($0.baseAddress!, size: $0.count) }
        XCTAssertTrue(result.allSatisfy(\.isFinite))
        return result
    }
}
