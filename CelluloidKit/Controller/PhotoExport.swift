import Foundation
import UIKit

public struct PhotoExport {
    public let image: UIImage
    public let jpegData: Data
    public let adjustmentData: Data
}

public enum PhotoExportError: Error { case cancelled, missingImage, invalidState, encodingFailed, adjustmentTooComplex }

/// One cancellable snapshot. Cancellation never turns a prior request into a new
/// editing session's output; each request completes once, on the main queue.
public final class PhotoExportTask {
    private let lock = NSLock()
    private var cancelled = false
    public func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
    #if DEBUG
    private var storage = PhotoExportStorageStatistics()
    private var consumedRasterObserver: (() -> Void)?
    var consumedRasterObserverForTesting: (() -> Void)? {
        get { lock.lock(); defer { lock.unlock() }; return consumedRasterObserver }
        set { lock.lock(); consumedRasterObserver = newValue; lock.unlock() }
    }
    var storageStatistics: PhotoExportStorageStatistics { lock.lock(); defer { lock.unlock() }; return storage }
    func recordCompositionStorage(_ bytes: Int) { lock.lock(); storage.compositionBytes = bytes; lock.unlock() }
    func beginRasterStorage(_ bytes: Int, width: Int, height: Int) {
        lock.lock(); defer { lock.unlock() }
        storage.currentRasterCount += 1; storage.currentRasterBytes += bytes; storage.rasterizedCount += 1
        storage.maximumRasterCount = max(storage.maximumRasterCount, storage.currentRasterCount)
        storage.maximumRasterBytes = max(storage.maximumRasterBytes, storage.currentRasterBytes)
        storage.maximumRasterWidth = max(storage.maximumRasterWidth, width)
        storage.maximumRasterHeight = max(storage.maximumRasterHeight, height)
    }
    func recordConsumedRaster() {
        lock.lock()
        storage.consumedRasterCount += 1
        let observer = consumedRasterObserver
        consumedRasterObserver = nil
        lock.unlock()
        // Test-only synchronization runs outside the statistics lock. Release
        // builds contain neither the observer nor these storage diagnostics.
        observer?()
    }
    func recordCompletedOverlay() { lock.lock(); storage.completedOverlayCount += 1; lock.unlock() }
    func endRasterStorage(_ bytes: Int) {
        lock.lock(); defer { lock.unlock() }
        storage.currentRasterCount -= 1; storage.currentRasterBytes -= bytes
    }
    #endif
}

#if DEBUG
struct PhotoExportStorageStatistics {
    var compositionBytes = 0
    var currentRasterCount = 0
    var currentRasterBytes = 0
    var maximumRasterCount = 0
    var maximumRasterBytes = 0
    var rasterizedCount = 0
    var consumedRasterCount = 0
    var completedOverlayCount = 0
    var maximumRasterWidth = 0
    var maximumRasterHeight = 0
}

import Darwin

/// Opt-in synthetic CI diagnostics. No pixels, paths or account data are logged.
enum PhotoExportDiagnostics {
    nonisolated static func trace(_ stage: String, source: CGImage? = nil, context: CGContext? = nil,
                                  format: UIGraphicsImageRendererFormat? = nil) {
        guard getenv("CELLULOID_EXPORT_METRICS") != nil else { return }
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
        let code = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        var fields: [String: Any] = ["stage": stage, "main_thread": Thread.isMainThread,
            "footprint_bytes": code == KERN_SUCCESS ? info.phys_footprint : 0]
        if let source = source {
            fields["source_width"] = source.width; fields["source_height"] = source.height
            fields["source_bits_per_component"] = source.bitsPerComponent
            fields["source_bits_per_pixel"] = source.bitsPerPixel
            fields["source_row_bytes"] = source.bytesPerRow
            fields["source_color_space"] = String(describing: source.colorSpace?.name)
            fields["source_alpha_info"] = source.alphaInfo.rawValue
        }
        if let context = context {
            fields["context_bits_per_component"] = context.bitsPerComponent
            fields["context_bits_per_pixel"] = context.bitsPerPixel
            fields["context_row_bytes"] = context.bytesPerRow
            fields["context_color_space"] = String(describing: context.colorSpace?.name)
            fields["context_alpha_info"] = context.alphaInfo.rawValue
        }
        if let format = format { fields["renderer_preferred_range"] = format.preferredRange.rawValue; fields["renderer_opaque"] = format.opaque }
        if let data = try? JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) { print("EXPORT_BITMAP_STAGE " + text) }
    }
}
#endif
