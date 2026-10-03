import Foundation
import UIKit

public struct PhotoExport {
    public let image: UIImage
    public let jpegData: Data
    public let adjustmentData: Data
}

public enum PhotoExportError: Error { case cancelled, missingImage, invalidState, encodingFailed }

/// One cancellable snapshot. Cancellation never turns a prior request into a new
/// editing session's output; each request completes once, on the main queue.
public final class PhotoExportTask {
    private let lock = NSLock()
    private var cancelled = false
    public func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
}
