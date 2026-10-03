import XCTest
import CryptoKit
import CelluloidDomain
@testable import CelluloidMac

final class LegacyFilterAdjustmentTests: XCTestCase {
    func testNewlyAuthoredFilterOnlyArchivesAndOpaqueFallbackPreservation() throws {
        for filter in FilterPreset.allCases {
            let bytes = try LegacyFilterAdjustment.encode(filter)
            XCTAssertEqual(try LegacyFilterAdjustment.decode(bytes), filter)
            let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            print("MAC_FILTER_ONLY_FIXTURE filter=\(filter.rawValue) sha256=\(hash) base64=\(bytes.base64EncodedString())")
        }
        let opaque = Data([0,1,2,3,4,255])
        let archive = try LegacyFilterAdjustment.encode(.fade, preserving: .init(identifier: "legacy-fixture", version: "1.0", data: opaque))
        XCTAssertNil(try LegacyFilterAdjustment.decode(archive), "Baked prior edits must not be advertised as restored layers")
        let root = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: [NSDictionary.self,NSString.self], from: archive) as? [String: Any])
        let preserved = try XCTUnwrap(root["celluloidPreservedAdjustment"] as? [String: String])
        XCTAssertEqual(Data(base64Encoded: try XCTUnwrap(preserved["base64"])), opaque)
        let layered = try NSKeyedArchiver.archivedData(withRootObject: ["filterType":"Chrome","bubbles":[["content":"Synthetic layer"]]], requiringSecureCoding: true)
        XCTAssertNil(try LegacyFilterAdjustment.decode(layered))
    }
}
