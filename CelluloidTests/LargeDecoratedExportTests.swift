import XCTest
import UIKit
import ImageIO
import UniformTypeIdentifiers
import Darwin
@testable import CelluloidKit

/// A simulator measurement, not a physical Photos-extension memory budget.
@MainActor
final class LargeDecoratedExportTests: XCTestCase {
    func testFortyEightMegapixelDecoratedExportAndInFlightCancellation() throws {
        setenv("CELLULOID_EXPORT_METRICS", "1", 1)
        defer { unsetenv("CELLULOID_EXPORT_METRICS") }
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".png")
        defer { try? FileManager.default.removeItem(at: path) }
        // Keep fixture creation outside export metrics and release its bitmap.
        try autoreleasepool {
            let context = try XCTUnwrap(CGContext(data: nil, width: 8000, height: 6000, bitsPerComponent: 8,
                bytesPerRow: 8000 * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            context.setFillColor(UIColor.red.cgColor); context.fill(CGRect(x: 0, y: 0, width: 4000, height: 6000))
            context.setFillColor(UIColor.blue.cgColor); context.fill(CGRect(x: 4000, y: 0, width: 4000, height: 6000))
            let image = try XCTUnwrap(context.makeImage())
            let destination = try XCTUnwrap(CGImageDestinationCreateWithURL(path as CFURL, UTType.png.identifier as CFString, 1, nil))
            CGImageDestinationAddImage(destination, image, nil)
            XCTAssertTrue(CGImageDestinationFinalize(destination))
        }
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = try XCTUnwrap(UIImage(contentsOfFile: path.path))
        editor.view.layoutIfNeeded()
        var state = editor.adjustmentData
        let canvas = try XCTUnwrap(state.referenceCanvasSize)
        var sticker = StickerModel.stickers[0]
        sticker.center = CGPoint(x: canvas.width * 0.75, y: canvas.height * 0.5)
        var bubble = BubbleModel.bubbles[4]
        bubble.content = "Full resolution 世界"
        bubble.center = CGPoint(x: canvas.width * 0.25, y: canvas.height * 0.5)
        state.stickers = [sticker]; state.bubbles = [bubble]
        editor.restoreFromData(state)
        editor.overlayView.subviews.compactMap { $0 as? AttachView }.forEach { $0.hideButtonEnable = false }
        let finished = expectation(description: "48MP decorated export")
        var completions = 0
        let probe = ExportLoadProbe()
        probe.start()
        print("EXPORT_48MP_BEGIN phase=success dimensions=8000x6000 decorations=bubble_and_sticker")
        editor.exportPhoto { result in
            completions += 1
            let metrics = probe.stop()
            print("EXPORT_48MP_METRICS phase=success " + metrics)
            XCTAssertTrue(probe.hasValidSamples, "Memory/heartbeat measurements must actually be obtained")
            switch result {
            case .failure(let error): XCTFail("48MP export failed: \(error)")
            case .success(let output):
                XCTAssertEqual(output.image.cgImage?.width, 8000)
                XCTAssertEqual(output.image.cgImage?.height, 6000)
                let jpeg = CGImageSourceCreateWithData(output.jpegData as CFData, nil)!
                let properties = CGImageSourceCopyPropertiesAtIndex(jpeg, 0, nil)! as NSDictionary
                XCTAssertEqual(properties[kCGImagePropertyPixelWidth] as? Int, 8000)
                XCTAssertEqual(properties[kCGImagePropertyPixelHeight] as? Int, 6000)
                XCTAssertGreaterThan(self.pixel(output.image, x: 100, y: 100)[0], 240)
                XCTAssertGreaterThan(self.pixel(output.image, x: 7900, y: 5900)[2], 240)
                // White artwork on otherwise pure red/blue proves the intended
                // two distinct decorated regions survived the full-size render.
                for centerX in [2000, 6000] {
                    var white = 0
                    for y in stride(from: 2500, through: 3500, by: 100) {
                        for x in stride(from: centerX - 500, through: centerX + 500, by: 100) {
                            let p = self.pixel(output.image, x: x, y: y)
                            if p[0] > 220 && p[1] > 220 && p[2] > 220 { white += 1 }
                        }
                    }
                    XCTAssertGreaterThan(white, 0, "Missing decoration at intended canvas location \(centerX)")
                }
                XCTAssertEqual(try? AdjustmentData.decode(output.adjustmentData).stickers.count, 1)
                XCTAssertEqual(try? AdjustmentData.decode(output.adjustmentData).bubbles.first?.content, bubble.content)
                print("EXPORT_48MP_PIXELS_PASS jpeg_bytes=\(output.jpegData.count) output_bits_per_pixel=\(output.image.cgImage?.bitsPerPixel ?? 0)")
            }
            finished.fulfill()
        }
        wait(for: [finished], timeout: 120)
        XCTAssertEqual(completions, 1)

        let cancelled = expectation(description: "In-flight48MP cancellation completes exactly once")
        var cancelledCompletions = 0
        let cancelProbe = ExportLoadProbe()
        cancelProbe.start()
        let task = editor.exportPhoto { result in
            cancelledCompletions += 1
            print("EXPORT_48MP_METRICS phase=cancel " + cancelProbe.stop())
            if case .failure(.cancelled) = result {} else { XCTFail("In-flight cancellation returned stale success") }
            cancelled.fulfill()
        }
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 0.05) {
            print("EXPORT_48MP_CANCEL_REQUEST uptime=\(ProcessInfo.processInfo.systemUptime)")
            task.cancel()
        }
        wait(for: [cancelled], timeout: 120)
        XCTAssertEqual(cancelledCompletions, 1)
        editor.sourceImage = nil
    }

    private func pixel(_ image: UIImage, x: Int, y: Int) -> [UInt8] {
        let part = image.cgImage!.cropping(to: CGRect(x: x, y: y, width: 1, height: 1))!
        var bytes = [UInt8](repeating: 0, count: 4)
        let context = CGContext(data: &bytes, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.draw(part, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        return bytes
    }
}

/// Samples the app process from an independent queue while UIKit may be busy.
/// Main-queue latency is measured separately from export completion duration.
private final class ExportLoadProbe: @unchecked Sendable {
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "Celluloid.test.export-load", qos: .userInitiated)
    private var timer: DispatchSourceTimer?
    private var started: TimeInterval = 0
    private var baseline: UInt64 = 0
    private var peak: UInt64 = 0
    private var samples = 0
    private var heartbeats = 0
    private var pendingHeartbeat = false
    private var stopped = false
    private var maxMainLatency: TimeInterval = 0

    private func footprint() -> UInt64 {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
        let code = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return code == KERN_SUCCESS ? info.phys_footprint : 0
    }
    var hasValidSamples: Bool {
        lock.lock(); defer { lock.unlock() }
        return baseline > 0 && peak >= baseline && samples > 0 && heartbeats > 0 && maxMainLatency.isFinite
    }
    func start() {
        started = ProcessInfo.processInfo.systemUptime
        baseline = footprint(); peak = baseline
        let source = DispatchSource.makeTimerSource(queue: queue)
        source.schedule(deadline: .now(), repeating: .milliseconds(25))
        source.setEventHandler { [weak self] in self?.tick() }
        timer = source
        source.resume()
    }
    private func tick() {
        let value = footprint()
        lock.lock()
        guard !stopped else { lock.unlock(); return }
        peak = max(peak, value); samples += 1
        let sendHeartbeat = !pendingHeartbeat
        if sendHeartbeat { pendingHeartbeat = true }
        lock.unlock()
        if sendHeartbeat {
            let sent = ProcessInfo.processInfo.systemUptime
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                self.lock.lock()
                self.maxMainLatency = max(self.maxMainLatency, ProcessInfo.processInfo.systemUptime - sent)
                self.heartbeats += 1
                self.pendingHeartbeat = false
                self.lock.unlock()
            }
        }
    }
    func stop() -> String {
        timer?.cancel(); timer = nil
        let final = footprint()
        lock.lock(); defer { lock.unlock() }
        stopped = true
        let metrics: [String: Any] = ["elapsed_seconds": ProcessInfo.processInfo.systemUptime - started,
            "baseline_footprint_bytes": baseline, "sampled_peak_footprint_bytes": max(peak, final),
            "final_footprint_bytes": final, "samples": samples, "main_heartbeats": heartbeats,
            "max_main_queue_latency_seconds": maxMainLatency, "sampling_interval_ms": 25,
            "scope": "simulator_fallback_sourceImage_not_URL_backed_Photos_extension"]
        return String(data: try! JSONSerialization.data(withJSONObject: metrics, options: [.sortedKeys]), encoding: .utf8)!
    }
}
