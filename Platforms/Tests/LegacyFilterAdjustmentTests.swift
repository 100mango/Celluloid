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
        let previous = LegacyFilterAdjustment.Preserved(identifier: "legacy-fixture", version: "1.0", data: opaque)
        XCTAssertEqual(LegacyFilterAdjustment.outputVersion(isBakedBase: false), "1.0")
        XCTAssertEqual(LegacyFilterAdjustment.outputVersion(isBakedBase: true), "2.0-baked-base")
        let archive = try LegacyFilterAdjustment.encode(.fade, preserving: previous)
        let fallback = ["identifier": LegacyFilterAdjustment.identifier,
                        "version": LegacyFilterAdjustment.outputVersion(isBakedBase: true),
                        "sha256": SHA256.hash(data: archive).map { String(format: "%02x", $0) }.joined(),
                        "base64": archive.base64EncodedString()]
        print("MAC_BAKED_BASE_FIXTURE " + String(decoding: try JSONSerialization.data(withJSONObject: fallback, options: [.sortedKeys]), as: UTF8.self))
        XCTAssertNil(try LegacyFilterAdjustment.decode(archive), "Baked prior edits must not be advertised as restored layers")
        let root = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: [NSDictionary.self,NSString.self,NSNumber.self], from: archive) as? [String: Any])
        let preserved = try XCTUnwrap(root["celluloidPreservedAdjustment"] as? [String: String])
        XCTAssertEqual(Data(base64Encoded: try XCTUnwrap(preserved["base64"])), opaque)
        let layered = try NSKeyedArchiver.archivedData(withRootObject: ["filterType":"Chrome","bubbles":[["content":"Synthetic layer"]]], requiringSecureCoding: true)
        XCTAssertNil(try LegacyFilterAdjustment.decode(layered))
    }
    func testReaderAcceptanceIsPureAndRepeatedFallbackIsBounded() throws {
        let valid = try LegacyFilterAdjustment.encode(.chrome)
        XCTAssertTrue(LegacyFilterAdjustment.accepts(identifier: LegacyFilterAdjustment.identifier, version: "1.0", data: valid))
        XCTAssertFalse(LegacyFilterAdjustment.accepts(identifier: "unrelated", version: "1.0", data: valid))
        XCTAssertFalse(LegacyFilterAdjustment.accepts(identifier: LegacyFilterAdjustment.identifier, version: "2.0-baked-base", data: valid))
        XCTAssertTrue(LegacyFilterAdjustment.accepts(identifier: LegacyFilterAdjustment.identifier, version: "1.0", data: valid), "An unrelated probe must not change acceptance or retain unrelated data")
        let withoutPriorBytes = try LegacyFilterAdjustment.encode(.original, isBakedBase: true)
        XCTAssertNil(try LegacyFilterAdjustment.decode(withoutPriorBytes))
        let root = try XCTUnwrap(NSKeyedUnarchiver.unarchivedObject(ofClasses: [NSDictionary.self,NSString.self,NSNumber.self], from: withoutPriorBytes) as? [String: Any])
        XCTAssertNil(root["celluloidPreservedAdjustment"], "Absent input metadata must never be invented or borrowed from a previous probe")
        var prior = Data([1,2,3]), boundedFailure = false
        for _ in 0..<64 {
            do {
                prior = try autoreleasepool {
                    try LegacyFilterAdjustment.encode(.fade, preserving: .init(identifier: LegacyFilterAdjustment.identifier, version: "2.0-baked-base", data: prior), isBakedBase: true)
                }
                XCTAssertLessThanOrEqual(prior.count, 4 * 1024 * 1024)
            } catch RecipeError.resourceLimit { boundedFailure = true; break }
        }
        XCTAssertTrue(boundedFailure, "Repeated fallback edits must fail explicitly at the bound instead of dropping prior bytes")
    }

}
