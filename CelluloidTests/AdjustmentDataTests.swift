import XCTest
import UIKit
import CoreImage
import CryptoKit
@testable import CelluloidKit

final class AdjustmentDataTests: XCTestCase {
    // Deliberately independent of toJSON(): this is the dictionary and NSValue
    // shape emitted by JSONCodable 3 and the original version 1.0 app.
    private var legacyBubble: [String: Any] {
        return [
            "asset": "say1",
            "content": "Hello, 世界 🎬",
            "transform": NSValue(cgAffineTransform: CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4)),
            "bounds": NSValue(cgRect: CGRect(x: 0, y: 0, width: 180, height: 96)),
            "center": NSValue(cgPoint: CGPoint(x: 240, y: 320))
        ]
    }

    private var legacySticker: [String: Any] {
        return [
            "imageName": "32",
            "transform": NSValue(cgAffineTransform: CGAffineTransform(scaleX: 0.5, y: 0.75)),
            "bounds": NSValue(cgRect: CGRect(x: 2, y: 3, width: 72, height: 80)),
            "center": NSValue(cgPoint: CGPoint(x: 44, y: -12))
        ]
    }

    private var legacyObject: [String: Any] {
        return ["filterType": "Chrome", "bubbles": [legacyBubble], "stickers": [legacySticker]]
    }

    private func legacyArchive(_ object: Any) throws -> Data {
        // Equivalent to the old archivedData(withRootObject:) API: the archive
        // was not required to use secure coding, but its contents support it.
        return try NSKeyedArchiver.archivedData(withRootObject: object, requiringSecureCoding: false)
    }

    private func assertBudgetRejected(_ bytes: Data, file: StaticString = #filePath, line: UInt = #line) {
        let before = SHA256.hash(data: bytes)
        XCTAssertThrowsError(try AdjustmentData.decode(bytes), file: file, line: line) { error in
            guard case .some(.resourceLimit(_)) = error as? AdjustmentDataError else {
                XCTFail("Expected an explicit all-or-nothing resource rejection, got \(error)", file: file, line: line)
                return
            }
        }
        XCTAssertEqual(SHA256.hash(data: bytes), before, "Opaque bytes must remain unchanged", file: file, line: line)
    }

    func testEncodedByteBudgetRejectsBeforeUnarchiving() {
        assertBudgetRejected(Data(repeating: 0, count: AdjustmentData.maximumEncodedBytes + 1))
    }

    func testSmallSharedReferenceArchiveRejectsExcessiveLayers() throws {
        let shared = legacySticker as NSDictionary
        let object: NSDictionary = ["filterType": "Original",
            "stickers": NSArray(array: Array(repeating: shared, count: AdjustmentData.maximumDecorations + 1))]
        let bytes = try legacyArchive(object)
        XCTAssertLessThan(bytes.count, 64 * 1024, "A byte limit alone cannot prevent repeated-object expansion")
        assertBudgetRejected(bytes)
    }

    func testAggregateRepeatedTextBudgetRejectsWithoutTruncation() throws {
        var bubble = legacyBubble; bubble["content"] = String(repeating: "x", count: 4096)
        let shared = bubble as NSDictionary
        let object: NSDictionary = ["filterType": "Original",
            "bubbles": NSArray(array: Array(repeating: shared, count: 65))]
        let bytes = try legacyArchive(object)
        XCTAssertLessThan(bytes.count, 64 * 1024)
        assertBudgetRejected(bytes)
    }

    func testIndividualUnicodeTextBudgetRejectsWithoutTruncation() throws {
        var bubble = legacyBubble
        bubble["content"] = String(repeating: "界", count: AdjustmentData.maximumBubbleTextUTF16Units + 1)
        assertBudgetRejected(try legacyArchive(["filterType": "Original", "bubbles": [bubble]]))
    }

    func testResourceBoundariesPreserveEveryLegacyLayerAndTextUnit() throws {
        var bubble = legacyBubble
        let text = String(repeating: "界", count: AdjustmentData.maximumBubbleTextUTF16Units)
        bubble["content"] = text
        let bubbles = Array(repeating: bubble, count: 4)
        let stickers = Array(repeating: legacySticker, count: AdjustmentData.maximumDecorations - bubbles.count)
        let original: [String: Any] = ["filterType": "Chrome", "bubbles": bubbles, "stickers": stickers]
        let bytes = try legacyArchive(original)
        XCTAssertLessThanOrEqual(bytes.count, AdjustmentData.maximumEncodedBytes)
        let decoded = try AdjustmentData.decode(bytes)
        XCTAssertEqual(decoded.bubbles.count, 4)
        XCTAssertEqual(decoded.stickers.count, 1020)
        XCTAssertTrue(decoded.bubbles.allSatisfy { $0.content == text })
        XCTAssertNil(decoded.referenceCanvasSize)
        XCTAssertTrue(try XCTUnwrap(decoded.toJSON() as? NSDictionary).isEqual(to: original))
        let roundtrip = try AdjustmentData.decode(decoded.encode())
        XCTAssertTrue(try XCTUnwrap(roundtrip.toJSON() as? NSDictionary).isEqual(to: original))
    }

    func testEncodingRejectsUnreopenableStateInsteadOfDroppingLayers() {
        var state = AdjustmentData()
        state.stickers = Array(repeating: StickerModel.stickers[0], count: AdjustmentData.maximumDecorations + 1)
        XCTAssertThrowsError(try state.encode())
        XCTAssertEqual(state.stickers.count, AdjustmentData.maximumDecorations + 1)
        state.stickers = []
        var bubble = BubbleModel.bubbles[0]
        bubble.content = String(repeating: "x", count: AdjustmentData.maximumBubbleTextUTF16Units + 1)
        state.bubbles = [bubble]
        XCTAssertThrowsError(try state.encode())
        XCTAssertEqual(state.bubbles[0].content.utf16.count, AdjustmentData.maximumBubbleTextUTF16Units + 1)
    }

    func testLegacyArchiveRoundTripsWithoutChangingItsDictionary() throws {
        let decoded = try AdjustmentData.decode(legacyArchive(legacyObject))
        XCTAssertEqual(decoded.filterType, .Chrome)
        XCTAssertEqual(decoded.bubbles.count, 1)
        XCTAssertEqual(decoded.stickers.count, 1)
        XCTAssertEqual(decoded.bubbles[0].content, "Hello, 世界 🎬")
        XCTAssertEqual(decoded.bubbles[0].center, CGPoint(x: 240, y: 320))
        XCTAssertEqual(decoded.bubbles[0].bounds, CGRect(x: 0, y: 0, width: 180, height: 96))
        XCTAssertEqual(decoded.bubbles[0].transform, CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4))
        XCTAssertEqual(decoded.stickers[0].center, CGPoint(x: 44, y: -12))
        XCTAssertEqual(decoded.stickers[0].bounds, CGRect(x: 2, y: 3, width: 72, height: 80))
        XCTAssertEqual(decoded.stickers[0].transform, CGAffineTransform(scaleX: 0.5, y: 0.75))
        let restored = try AdjustmentData.decode(decoded.encode())
        let dictionary = try XCTUnwrap(restored.toJSON() as? NSDictionary)
        XCTAssertTrue(dictionary.isEqual(to: legacyObject))
        XCTAssertEqual(AdjustmentData.formatIdentifier, "Mango.CelluloidPhotoExtension")
        XCTAssertEqual(AdjustmentData.formatVersion, "1.0")
        XCTAssertTrue(AdjustmentData.supportIdentifier("Mango.CelluloidPhotoExtension", version: "1.0"))
        XCTAssertFalse(AdjustmentData.supportIdentifier("Mango.CelluloidPhotoExtension", version: "2.0"))
        XCTAssertFalse(AdjustmentData.supportIdentifier("Other", version: "1.0"))
    }

    func testExportSyntheticUIKitCompatibilityFixtures() throws {
        // Contemporary UIKit-produced reproductions of the shipping dictionary,
        // not recovered user archives. Bounded output supports independent AppKit
        // compatibility tests without guessing NSValue's serialized representation.
        for name in ["legacy-points", "reference-canvas"] {
            var object = legacyObject
            if name == "reference-canvas" { object["referenceCanvasSize"] = NSValue(cgSize: CGSize(width: 480, height: 640)) }
            let input = try legacyArchive(object)
            let decoded = try AdjustmentData.decode(input)
            let bytes: Data
            if name == "legacy-points" { bytes = input }
            else { bytes = try decoded.encode() }
            let verified = try AdjustmentData.decode(bytes)
            XCTAssertTrue(try XCTUnwrap(verified.toJSON() as? NSDictionary).isEqual(to: object))
            XCTAssertEqual(verified.referenceCanvasSize, name == "legacy-points" ? nil : CGSize(width: 480, height: 640))
            XCTAssertLessThanOrEqual(bytes.count, 8_000)
            let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            let metadata: [String: Any] = ["name": name, "sha256": digest, "bytes": bytes.count,
                "runtime": UIDevice.current.systemVersion, "formatIdentifier": AdjustmentData.formatIdentifier,
                "formatVersion": AdjustmentData.formatVersion, "filterType": "Chrome",
                "bubble": ["asset": "say1", "content": "Hello, 世界 🎬", "center": [240, 320], "bounds": [0, 0, 180, 96], "transform": [1.5, 0.25, -0.25, 1.5, 10, -4]],
                "sticker": ["imageName": "32", "center": [44, -12], "bounds": [2, 3, 72, 80], "transform": [0.5, 0, 0, 0.75, 0, 0]],
                "referenceCanvasSize": name == "legacy-points" ? [] : [480, 640]]
            print("UIKIT_ARCHIVE_FIXTURE_META " + String(decoding: try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]), as: UTF8.self))
            print("UIKIT_ARCHIVE_FIXTURE_BEGIN:" + name)
            // One small write stays atomic in the runner pipe, unlike a print
            // sequence that may interleave UIKit stderr into fixture bytes.
            FileHandle.standardOutput.write(Data((bytes.base64EncodedString() + "\n").utf8))
            print("UIKIT_ARCHIVE_FIXTURE_END:" + name)
        }
    }

    func testActualMacEncodedFixturesDecodeWithOriginalUIKitReader() throws {
        // Native macOS27/Xcode27 output from commit42270fac, run37117674534,
        // produced only after decoding the UIKit synthetic fixtures. This checks
        // the original shipping reader, not a new cross-platform substitute.
        let fixtures = [
            ("legacy-points", "1938b3dff02617600a4a56382869afadd2378ed9681df66472fb3dc00713ceca", "YnBsaXN0MDDUAQIDBAUGBwpYJHZlcnNpb25ZJGFyY2hpdmVyVCR0b3BYJG9iamVjdHMSAAGGoF8QD05TS2V5ZWRBcmNoaXZlctEICVRyb290gAGvECALDBkaGxwgLC0uLzAxPkRJSk9QU1ZXW2lqa25vcHh7fFUkbnVsbNMNDg8QFBhXTlMua2V5c1pOUy5vYmplY3RzViRjbGFzc6MREhOAAoADgASjFRYXgAWAFIAVgBJYc3RpY2tlcnNaZmlsdGVyVHlwZVdidWJibGVz0g4PHR+hHoAGgBPTDQ4PISYYpCIjJCWAB4AIgAmACqQnKCkqgAuADIAOgBCAEllpbWFnZU5hbWVZdHJhbnNmb3JtVmJvdW5kc1ZjZW50ZXJSMzLYMjMPNDU2Nzg5Ojs5PDk5PVtOUy5hdHZhbC50eVpOUy5zcGVjaWFsW05TLmF0dmFsLnR4Wk5TLmF0dmFsLmRaTlMuYXR2YWwuY1pOUy5hdHZhbC5iWk5TLmF0dmFsLmEjAAAAAAAAAAAQCoANIz/oAAAAAAAAIz/gAAAAAAAA0j9AQUJaJGNsYXNzbmFtZVgkY2xhc3Nlc1dOU1ZhbHVlokFDWE5TT2JqZWN000UPM0Y7SFpOUy5yZWN0dmFsgA+ADRADXxASe3syLCAzfSwgezcyLCA4MH1900sPM0w7TltOUy5wb2ludHZhbIARgA0QAVl7NDQsIC0xMn3SP0BRUlxOU0RpY3Rpb25hcnmiUUPSP0BUVVdOU0FycmF5olRDVkNocm9tZdIOD1gfoVmAFoAT0w0OD1xiGKUlXiMkYYAKgBeACIAJgBilY2RlZmeAGYAbgByAHYAfgBJXY29udGVudFVhc3NldNNLDzNsO06AGoANWnsyNDAsIDMyMH1sAEgAZQBsAGwAbwAsACBOFnVMACDYPN+s2DIzDzQ1Njc4cTo7c3R1dncjwBAAAAAAAACADSNAJAAAAAAAACM/+AAAAAAAACO/0AAAAAAAACM/0AAAAAAAACM/+AAAAAAAANNFDzN5O0iAHoANXxATe3swLCAwfSwgezE4MCwgOTZ9fVRzYXkxAAgAEQAaACQAKQAyADcASQBMAFEAUwB2AHwAgwCLAJYAnQChAKMApQCnAKsArQCvALEAswC8AMcAzwDUANYA2ADaAOEA5gDoAOoA7ADuAPMA9QD3APkA+wD9AQcBEQEYAR8BIgEzAT8BSgFWAWEBbAF3AYIBiwGNAY8BmAGhAaYBsQG6AcIBxQHOAdUB4AHiAeQB5gH7AgICDgIQAhICFAIeAiMCMAIzAjgCQAJDAkoCTwJRAlMCVQJcAmICZAJmAmgCagJsAnICdAJ2AngCegJ8An4ChgKMApMClQKXAqICuwLMAtUC1wLgAukC8gL7AwQDCwMNAw8DJQAAAAAAAAIBAAAAAAAAAH0AAAAAAAAAAAAAAAAAAAMq"),
            ("reference-canvas", "5562aaf3223fd7dd0e8ad2883484f7ab667f25ff9c9fe4bfb8e965d39c9806fc", "YnBsaXN0MDDUAQIDBAUGBwpYJHZlcnNpb25ZJGFyY2hpdmVyVCR0b3BYJG9iamVjdHMSAAGGoF8QD05TS2V5ZWRBcmNoaXZlctEICVRyb290gAGvECMLDBscHR4fICQyMzQ1Njc4OUlPVFVaW15hZmdrd3h5foGChVUkbnVsbNMNDg8QFRpXTlMua2V5c1pOUy5vYmplY3RzViRjbGFzc6QREhMUgAKAA4AEgAWkFhcYGYAGgAeAGIAagBZaZmlsdGVyVHlwZVdidWJibGVzXxATcmVmZXJlbmNlQ2FudmFzU2l6ZVhzdGlja2Vyc1ZDaHJvbWXSDg8hI6EigAiAF9MNDg8lKxqlJicoKSqACYAKgAuADIANpSwtLi8wgA6AD4AQgBKAFIAWVWFzc2V0V2NvbnRlbnRZdHJhbnNmb3JtVmJvdW5kc1ZjZW50ZXJUc2F5MWwASABlAGwAbABvACwAIE4WdUwAINg836zYOjsPPD0+P0BBQkNERUZHSFtOUy5hdHZhbC50eVpOUy5zcGVjaWFsW05TLmF0dmFsLnR4Wk5TLmF0dmFsLmRaTlMuYXR2YWwuY1pOUy5hdHZhbC5iWk5TLmF0dmFsLmEjwBAAAAAAAAAQCoARI0AkAAAAAAAAIz/4AAAAAAAAI7/QAAAAAAAAIz/QAAAAAAAAIz/4AAAAAAAA0kpLTE1aJGNsYXNzbmFtZVgkY2xhc3Nlc1dOU1ZhbHVlokxOWE5TT2JqZWN001APO1FDU1pOUy5yZWN0dmFsgBOAERADXxATe3swLCAwfSwgezE4MCwgOTZ9fdNWDztXQ1lbTlMucG9pbnR2YWyAFYAREAFaezI0MCwgMzIwfdJKS1xdXE5TRGljdGlvbmFyeaJcTtJKS19gV05TQXJyYXmiX07TYg87Y0NlWk5TLnNpemV2YWyAGYAREAJaezQ4MCwgNjQwfdIOD2gjoWmAG4AX0w0OD2xxGqRtKCkqgByAC4AMgA2kcnN0dYAdgB6AH4AhgBZZaW1hZ2VOYW1lUjMy2Do7Dzw9Pj9AekJDenx6en0jAAAAAAAAAACAESM/6AAAAAAAACM/4AAAAAAAANNQDzt/Q1OAIIARXxASe3syLCAzfSwgezcyLCA4MH1901YPO4NDWYAigBFZezQ0LCAtMTJ9AAgAEQAaACQAKQAyADcASQBMAFEAUwB5AH8AhgCOAJkAoAClAKcAqQCrAK0AsgC0ALYAuAC6ALwAxwDPAOUA7gD1APoA/AD+AQABBwENAQ8BEQETARUBFwEdAR8BIQEjASUBJwEpAS8BNwFBAUgBTwFUAW0BfgGKAZUBoQGsAbcBwgHNAdYB2AHaAeMB7AH1Af4CBwIMAhcCIAIoAisCNAI7AkYCSAJKAkwCYgJpAnUCdwJ5AnsChgKLApgCmwKgAqgCqwKyAr0CvwLBAsMCzgLTAtUC1wLZAuAC5QLnAukC6wLtAvIC9AL2AvgC+gL8AwYDCQMaAyMDJQMuAzcDPgNAA0IDVwNeA2ADYgAAAAAAAAIBAAAAAAAAAIYAAAAAAAAAAAAAAAAAAANs")
        ]
        for (name, expectedHash, base64) in fixtures {
            let bytes = try XCTUnwrap(Data(base64Encoded: base64))
            XCTAssertEqual(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(), expectedHash)
            let decoded = try AdjustmentData.decode(bytes)
            var expected = legacyObject
            if name == "reference-canvas" { expected["referenceCanvasSize"] = NSValue(cgSize: CGSize(width: 480, height: 640)) }
            XCTAssertTrue(try XCTUnwrap(decoded.toJSON() as? NSDictionary).isEqual(to: expected))
            XCTAssertEqual(decoded.referenceCanvasSize, name == "legacy-points" ? nil : CGSize(width: 480, height: 640))
            let redecoded = try AdjustmentData.decode(decoded.encode())
            XCTAssertTrue(try XCTUnwrap(redecoded.toJSON() as? NSDictionary).isEqual(to: expected))
            print("MAC_TO_UIKIT_ARCHIVE_PASS name=\(name) sha256=\(expectedHash)")
        }
    }

    func testProbe32BitGeometryArchiveRepresentation() throws {
        func floatValue(_ fields: [Float], _ encoding: String) -> NSValue {
            fields.withUnsafeBufferPointer { pointer in
                encoding.withCString { NSValue(bytes: UnsafeRawPointer(pointer.baseAddress!), objCType: $0) }
            }
        }
        var bubble = legacyBubble
        bubble["transform"] = floatValue([1.5, 0.25, -0.25, 1.5, 10, -4], "{CGAffineTransform=ffffff}")
        bubble["bounds"] = floatValue([0, 0, 180, 96], "{CGRect={CGPoint=ff}{CGSize=ff}}")
        bubble["center"] = floatValue([240, 320], "{CGPoint=ff}")
        var sticker = legacySticker
        sticker["transform"] = floatValue([0.5, 0, 0, 0.75, 0, 0], "{CGAffineTransform=ffffff}")
        sticker["bounds"] = floatValue([2, 3, 72, 80], "{CGRect={CGPoint=ff}{CGSize=ff}}")
        sticker["center"] = floatValue([44, -12], "{CGPoint=ff}")
        let object: [String: Any] = ["filterType": "Chrome", "bubbles": [bubble], "stickers": [sticker]]
        let inputTypes = ["transform", "bounds", "center"].map { String(cString: (bubble[$0] as! NSValue).objCType) }
        let bytes = try legacyArchive(object)
        XCTAssertLessThan(bytes.count, 8_000)
        let allowed: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
        let root = try XCTUnwrap(try NSKeyedUnarchiver.unarchivedObject(ofClasses: allowed, from: bytes) as? [String: Any])
        let values = try XCTUnwrap((root["bubbles"] as? [[String: Any]])?.first)
        let decodedTypes = try ["transform", "bounds", "center"].map { String(cString: try XCTUnwrap(values[$0] as? NSValue).objCType) }
        print("LEGACY_FLOAT_PROBE_TYPES before=\(inputTypes) after=\(decodedTypes)")
        // This is a classification probe, not a claim that an actual armv7 user
        // archive was recovered. Safe rejection identifies a conversion gap.
        do {
            let decoded = try AdjustmentData.decode(bytes)
            XCTAssertTrue(try XCTUnwrap(decoded.toJSON() as? NSDictionary).isEqual(to: legacyObject))
            print("LEGACY_FLOAT_PROBE_RESULT normalized_and_accepted")
        } catch {
            print("LEGACY_FLOAT_PROBE_RESULT safely_rejected error=\(error)")
        }
    }

    func testLegacyArchivesMayOmitEmptyArrays() throws {
        let data = try legacyArchive(["filterType": "Original"])
        let restored = try AdjustmentData.decode(data)
        XCTAssertTrue(restored.bubbles.isEmpty)
        XCTAssertTrue(restored.stickers.isEmpty)
        XCTAssertEqual(restored.filterType, .Original)
        let dictionary = try XCTUnwrap(restored.toJSON() as? [String: Any])
        XCTAssertNil(dictionary["bubbles"])
        XCTAssertNil(dictionary["stickers"])
        let empty = try AdjustmentData.decode(AdjustmentData().encode())
        XCTAssertEqual(empty.filterType, .Original)
    }

    func testExplicitEmptyArraysAreAlsoAccepted() throws {
        let restored = try AdjustmentData(object: ["filterType": "Original", "bubbles": [], "stickers": []])
        XCTAssertTrue(restored.bubbles.isEmpty)
        XCTAssertTrue(restored.stickers.isEmpty)
    }

    func testMalformedArchivesAndUnexpectedClassesAreRejected() throws {
        XCTAssertThrowsError(try AdjustmentData.decode(Data()))
        XCTAssertThrowsError(try AdjustmentData.decode(Data("not a keyed archive".utf8)))
        XCTAssertThrowsError(try AdjustmentData.decode(legacyArchive(["wrong", "root"])))
        XCTAssertThrowsError(try AdjustmentData.decode(legacyArchive(["filterType": Date()])))
        let valid = try legacyArchive(legacyObject)
        XCTAssertThrowsError(try AdjustmentData.decode(Data(valid.prefix(valid.count / 2))))
    }

    func testUnknownFilterAndInvalidCollectionsAreRejected() throws {
        for object: [String: Any] in [
            [:],
            ["filterType": "FutureFilter"],
            ["filterType": 1],
            ["filterType": "Original", "bubbles": "invalid"],
            ["filterType": "Original", "bubbles": [1]],
            ["filterType": "Original", "stickers": NSNull()]
        ] {
            XCTAssertThrowsError(try AdjustmentData(object: object))
        }
    }

    func testUnknownAssetsAreRejectedBeforeTheyReachImageRendering() throws {
        for name in ["unknown", "bubbleButton", "image_sticker_say"] {
            var bubble = legacyBubble
            bubble["asset"] = name
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        for name in ["unknown", "31", "55", "032", "32.png"] {
            var sticker = legacySticker
            sticker["imageName"] = name
            XCTAssertThrowsError(try StickerModel(object: sticker))
        }
    }

    func testMissingAndMistypedGeometryAreRejected() throws {
        for key in ["transform", "bounds", "center", "content", "asset"] {
            var bubble = legacyBubble
            bubble.removeValue(forKey: key)
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        let invalidGeometry: [String: Any] = [
            "transform": NSNumber(value: 1),
            "bounds": NSValue(cgPoint: .zero),
            "center": NSValue(range: NSRange(location: 0, length: 1))
        ]
        for (key, value) in invalidGeometry {
            var bubble = legacyBubble
            bubble[key] = value
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
    }

    func testNonfiniteAndNegativeGeometryAreRejected() throws {
        let invalidGeometry: [(String, NSValue)] = [
            ("transform", NSValue(cgAffineTransform: CGAffineTransform(a: .nan, b: 0, c: 0, d: 1, tx: 0, ty: 0))),
            ("bounds", NSValue(cgRect: CGRect(x: 0, y: 0, width: -1, height: 100))),
            ("bounds", NSValue(cgRect: CGRect(x: 0, y: 0, width: CGFloat.infinity, height: 100))),
            ("center", NSValue(cgPoint: CGPoint(x: CGFloat.infinity, y: 0)))
        ]
        for (key, value) in invalidGeometry {
            var bubble = legacyBubble
            bubble[key] = value
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        var state = AdjustmentData()
        var sticker = try StickerModel(object: legacySticker)
        sticker.center.x = .nan
        state.stickers = [sticker]
        XCTAssertThrowsError(try state.encode())
    }

    func testEveryShippingAssetAndFilterCanRoundTrip() throws {
        let filters: [FilterType] = [.Original, .Sepia, .Chrome, .Fade, .Invert, .Posterize, .Sketch, .Comic, .Crystal, .PixellateFace]
        for filter in filters {
            var state = AdjustmentData()
            state.filterType = filter
            state.bubbles = BubbleModel.bubbles
            state.stickers = StickerModel.stickers
            let restored = try AdjustmentData.decode(state.encode())
            XCTAssertEqual(restored.filterType, filter)
            XCTAssertEqual(restored.bubbles.count, 10)
            XCTAssertEqual(restored.stickers.count, 23)
        }
    }
}

final class FilterTests: XCTestCase {
    private let context = CIContext(options: [.workingColorSpace: NSNull(), .outputColorSpace: NSNull()])
    private let extent = CGRect(x: 0, y: 0, width: 16, height: 12)

    private var input: CIImage {
        return CIImage(color: CIColor(red: 0.25, green: 0.5, blue: 0.75)).cropped(to: extent)
    }

    private func pixels(_ image: CIImage) -> [UInt8] {
        let rowBytes = Int(extent.width) * 4
        var bytes = [UInt8](repeating: 0, count: rowBytes * Int(extent.height))
        bytes.withUnsafeMutableBytes { buffer in
            context.render(image, toBitmap: buffer.baseAddress!, rowBytes: rowBytes,
                           bounds: extent, format: .RGBA8, colorSpace: nil)
        }
        return bytes
    }

    func testOriginalReturnsTheSameImageAndPixels() {
        let original = input
        let result = Filters.filter(.Original)(original)
        XCTAssertTrue(result === original)
        XCTAssertEqual(pixels(result), pixels(original))
    }

    func testInvertActuallyInvertsPixels() {
        let result = pixels(Filters.filter(.Invert)(input))
        XCTAssertEqual(Double(result[0]), 191, accuracy: 1)
        XCTAssertEqual(Double(result[1]), 128, accuracy: 1)
        XCTAssertEqual(Double(result[2]), 64, accuracy: 1)
        XCTAssertEqual(result[3], 255)
    }

    func testPresetsMatchTheirShippingCoreImageFilters() throws {
        let names: [(FilterType, String)] = [
            (.Sepia, "CISepiaTone"), (.Chrome, "CIPhotoEffectChrome"),
            (.Fade, "CIPhotoEffectInstant"), (.Invert, "CIColorInvert"),
            (.Posterize, "CIColorPosterize"), (.Sketch, "CILineOverlay"),
            (.Comic, "CIComicEffect"), (.Crystal, "CICrystallize")
        ]
        for (type, name) in names {
            let expected = try XCTUnwrap(CIFilter(name: name, parameters: [kCIInputImageKey: input])?.outputImage)
            XCTAssertEqual(pixels(Filters.filter(type)(input)), pixels(expected), name)
        }
    }

    func testFacePixelationWithoutFacesIsANoOp() {
        let original = input
        let result = Filters.filter(.PixellateFace)(original)
        XCTAssertTrue(result === original)
    }

    func testInvalidBlurRadiusIsANoOp() {
        let original = input
        XCTAssertTrue(Filters.blur(.nan)(original) === original)
        XCTAssertTrue(Filters.blur(-1)(original) === original)
    }

    func testUIImageFilteringPreservesScaleAndDisplayOrientation() throws {
        let cgImage = try XCTUnwrap(context.createCGImage(input, from: extent))
        let image = UIImage(cgImage: cgImage, scale: 2, orientation: .right)
        let result = image.filteredImage(Filters.filter(.Original))
        XCTAssertEqual(result.scale, 2)
        XCTAssertEqual(result.imageOrientation, .right)
        XCTAssertEqual(result.size, image.size)
    }

    func testExifOrientationIsAppliedExactlyOnce() throws {
        let cgImage = try XCTUnwrap(context.createCGImage(input, from: extent))
        let image = UIImage(cgImage: cgImage, scale: 2, orientation: .right)
        let result = image.filteredImage(6, filter: Filters.filter(.Original))
        XCTAssertEqual(result.scale, 2)
        XCTAssertEqual(result.imageOrientation, .up)
        XCTAssertEqual(result.cgImage?.width, cgImage.height)
        XCTAssertEqual(result.cgImage?.height, cgImage.width)
    }

    func testImageWithoutBackingPixelsDoesNotCrash() {
        let image = UIImage()
        XCTAssertTrue(image.filteredImage(Filters.filter(.Sepia)) === image)
        XCTAssertTrue(image.filteredImage(6, filter: Filters.filter(.Sepia)) === image)
    }
}
