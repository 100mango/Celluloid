import XCTest
import AppKit
import CryptoKit
import CelluloidDomain
import CelluloidRendering

@MainActor final class MacPhotoSessionTests: XCTestCase {
    private func image() throws -> Data {
        let context = try RasterCodec.bitmap(width: 120, height: 80)
        context.setFillColor(CGColor(srgbRed: 0.2, green: 0.6, blue: 0.8, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
    }
    func testUnsupportedAndMalformedDataKeepExactCurrentPlaceholderAndOpaqueBytesReadOnly() throws {
        for payload in [MacPhotoAdjustmentPayload(identifier: "future-editor", version: "99", bytes: Data([1,2,3])),
                        MacPhotoAdjustmentPayload(identifier: MacPhotoAdjustment.identifier, version: "1.0", bytes: Data([9,8,7]))] {
            var reads = 0
            let session = MacPhotoSession(load: { _ in reads += 1; return Data() })
            let current = NSImage(size: NSSize(width: 120, height: 80))
            session.begin(url: URL(fileURLWithPath: "/not-read"), orientation: 1, previous: payload, placeholder: current)
            XCTAssertTrue(session.readOnly); XCTAssertTrue(session.placeholder === current)
            XCTAssertEqual(session.originalAdjustment?.bytes, payload.bytes); XCTAssertNil(session.snapshot)
            session.change { $0.filter = .invert }; session.add(kind: .sticker, asset: "32")
            XCTAssertFalse(session.changed); XCTAssertEqual(reads, 0)
            session.cancel(); XCTAssertNil(session.originalAdjustment); XCTAssertNil(session.placeholder)
        }
    }
    func testActualLegacyPointsFixtureUsesReadOnlyCurrentAppearance() throws {
        let bundle = Bundle(for: Self.self)
        let data = try XCTUnwrap(Data(base64Encoded: Data(contentsOf: XCTUnwrap(bundle.url(forResource: "legacy-points", withExtension: "base64"))), options: .ignoreUnknownCharacters))
        let session = MacPhotoSession(load: { _ in XCTFail("Ambiguous geometry must not load/render the earlier input"); return Data() })
        session.begin(url: nil, orientation: 1, previous: .init(identifier: MacPhotoAdjustment.identifier, version: "1.0", bytes: data), placeholder: NSImage())
        XCTAssertTrue(session.readOnly); XCTAssertEqual(session.originalAdjustment?.bytes, data); XCTAssertNil(session.snapshot)
    }
    func testReferenceCanvasLayersPreserveExactCurrentAppearanceUntilUIKitPixelGatePasses() throws {
        let bundle = Bundle(for: Self.self)
        let data = try XCTUnwrap(Data(base64Encoded: Data(contentsOf: XCTUnwrap(bundle.url(forResource: "reference-canvas", withExtension: "base64"))), options: .ignoreUnknownCharacters))
        var reads = 0, previews = 0
        let session = MacPhotoSession(load: { _ in reads += 1; return Data() }, preview: { _, _, _ in
            previews += 1; throw RenderError.renderFailed
        })
        let current = NSImage(size: NSSize(width: 480, height: 640))
        session.begin(url: URL(fileURLWithPath: "/must-not-render-original"), orientation: 1,
                      previous: .init(identifier: MacPhotoAdjustment.identifier, version: "1.0", bytes: data), placeholder: current)
        XCTAssertTrue(session.readOnly); XCTAssertTrue(session.placeholder === current)
        XCTAssertEqual(session.originalAdjustment?.bytes, data); XCTAssertNil(session.snapshot)
        session.change { $0.filter = .invert }; session.remove(session.adjustment.bubbles[0].id)
        XCTAssertFalse(session.changed); XCTAssertEqual(session.adjustment.filter, .chrome)
        XCTAssertEqual(session.adjustment.bubbles.count, 1); XCTAssertEqual(session.adjustment.stickers.count, 1)
        switch session.prepareHostFinish() {
        case .noChange: break
        default: XCTFail("An unqualified layered edit must never reach Photos output preparation")
        }
        XCTAssertEqual(reads, 0); XCTAssertEqual(previews, 0)
        XCTAssertTrue(session.placeholder === current); XCTAssertEqual(session.originalAdjustment?.bytes, data)
    }
    func testCancellationAndReplacementSuppressLateSourceAndPreviewWithoutMutatingInput() async throws {
        let original = try image()
        let entered = expectation(description: "Old source loading entered")
        let returned = expectation(description: "Canceled source operation returned")
        var resume: CheckedContinuation<Data, Never>?
        let session = MacPhotoSession(load: { _ in
            let data = await withCheckedContinuation { resume = $0; entered.fulfill() }
            returned.fulfill(); return data
        })
        session.begin(url: URL(fileURLWithPath: "/old"), orientation: 1, previous: nil, placeholder: NSImage())
        await fulfillment(of: [entered], timeout: 2)
        let opaque = Data([4,5,6]); let current = NSImage()
        session.begin(url: nil, orientation: 1, previous: .init(identifier: "unknown", version: "1", bytes: opaque), placeholder: current)
        resume?.resume(returning: original)
        await fulfillment(of: [returned], timeout: 2); await Task.yield()
        XCTAssertTrue(session.readOnly); XCTAssertTrue(session.placeholder === current); XCTAssertNil(session.preview)
        XCTAssertEqual(session.originalAdjustment?.bytes, opaque); XCTAssertNil(session.snapshot)
    }
    func testImmediateHostDoneDuringObservedLoadingIsNoChangeAndStartsNoRenderOrWritePreparation() async throws {
        let original = try image()
        let entered = expectation(description: "Actually entered paused source loader")
        let returned = expectation(description: "Canceled loader returned")
        var resume: CheckedContinuation<Data, Never>?
        var previews = 0, renderPreparations = 0
        let session = MacPhotoSession(load: { _ in
            let bytes = await withCheckedContinuation { resume = $0; entered.fulfill() }
            returned.fulfill(); return bytes
        }, preview: { _, _, _ in
            previews += 1; return try RasterCodec.bitmap(width: 1, height: 1).makeImage()!
        })
        session.begin(url: URL(fileURLWithPath: "/paused"), orientation: 1, previous: nil, placeholder: NSImage())
        await fulfillment(of: [entered], timeout: 2)
        XCTAssertTrue(session.loading); XCTAssertFalse(session.editable); XCTAssertFalse(session.changed)
        switch session.prepareHostFinish() { // The exact controller dispatch decision.
        case .noChange: break
        case .render: renderPreparations += 1; XCTFail("Unchanged input must not reach output/writer preparation")
        case .unavailable: XCTFail("Immediate Done must not return a failed/nil output")
        }
        XCTAssertNil(session.snapshot)
        resume?.resume(returning: original)
        await fulfillment(of: [returned], timeout: 2); await Task.yield()
        XCTAssertEqual(previews, 0); XCTAssertEqual(renderPreparations, 0)
        XCTAssertNil(session.snapshot); XCTAssertFalse(session.changed)
        session.cancel()
    }
    func testNewEditsFreezeForFinishAndKeepOriginalBytes() async throws {
        let original = try image(), loaded = expectation(description: "Preview rendered")
        let session = MacPhotoSession(load: { _ in original }, preview: { _, _, _ in
            let image = try RasterCodec.bitmap(width: 120, height: 80).makeImage()!
            loaded.fulfill(); return image
        })
        session.begin(url: URL(fileURLWithPath: "/source"), orientation: 1, previous: nil, placeholder: NSImage())
        await fulfillment(of: [loaded], timeout: 2); await Task.yield()
        XCTAssertTrue(session.editable); XCTAssertFalse(session.changed)
        session.change { $0.filter = .fade }
        for (kind, asset) in [(MacPhotoLayer.Kind.bubble, "say1"), (.sticker, "32")] {
            session.add(kind: kind, asset: asset)
            XCTAssertTrue(session.adjustment.layers.isEmpty)
            XCTAssertNil(session.selection); XCTAssertNotNil(session.error)
        }
        session.prepareToFinish(); session.finishing = true
        let snapshot = try XCTUnwrap(session.snapshot)
        session.change { $0.filter = .invert }
        XCTAssertEqual(session.adjustment.filter, .fade)
        XCTAssertEqual(snapshot.adjustment.filter, .fade); XCTAssertTrue(snapshot.adjustment.layers.isEmpty)
        XCTAssertEqual(snapshot.bytes, original); XCTAssertEqual(session.snapshot?.bytes, original)
        XCTAssertTrue(session.changed)
        session.cancel(); XCTAssertFalse(session.changed); XCTAssertNil(session.snapshot)
    }
    func testOrientationMismatchNeverUsesUnverifiedOriginalAsCurrentAppearance() async throws {
        let original = try image(), loaded = expectation(description: "Source read")
        let session = MacPhotoSession(load: { _ in loaded.fulfill(); return original })
        let current = NSImage()
        session.begin(url: URL(fileURLWithPath: "/source"), orientation: 6, previous: nil, placeholder: current)
        await fulfillment(of: [loaded], timeout: 2); await Task.yield()
        XCTAssertTrue(session.readOnly); XCTAssertTrue(session.placeholder === current); XCTAssertNil(session.snapshot)
    }
}
