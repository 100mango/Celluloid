import Foundation
import Darwin

/// Owns one prepared Photos output file until the host receives it. The queue
/// serializes file commits/cleanup; the lock only protects state and the short
/// same-directory rename boundary, never JPEG encoding or bulk writes.
final class PhotosOutputWrite {
    enum Failure: Error { case cancelled, writeFailed(Error) }
    private static let queue = DispatchQueue(label: "Mango.Celluloid.Photos-output-files", qos: .userInitiated)
    // Accessed only on queue. Another operation can never have its committed
    // output deleted by a late cleanup from this operation.
    private static var destinationOwners: [URL: UUID] = [:]
    private let lock = NSLock()
    private let identity = UUID()
    private var cancelled = false
    private var delivered = false
    private var committed = false
    private var started = false
    let destination: URL
    private let staging: URL

    #if DEBUG
    // Executes off-main before any file write, outside lock. Tests acknowledge
    // cancellation/replacement deterministically rather than racing a delay.
    var beforeWriteForTesting: (() -> Void)?
    var removeStagingForTesting: ((URL) throws -> Void)?
    var stagingCleanupFailureForTesting: ((String, Int) -> Void)?
    static func afterPendingWorkForTesting(_ completion: @escaping () -> Void) {
        queue.async { DispatchQueue.main.async(execute: completion) }
    }
    #endif

    init(destination: URL) {
        let canonical = destination.standardizedFileURL.resolvingSymlinksInPath()
        self.destination = canonical
        staging = canonical.deletingLastPathComponent().appendingPathComponent(".Celluloid-\(UUID().uuidString).jpg")
    }

    func cancel() {
        lock.lock(); cancelled = true; lock.unlock()
        Self.queue.async { self.removeAbandonedOutput() }
    }

    /// Call on main after all adapter generation checks, immediately before the
    /// Photos callback. No later cancellation may delete a delivered host file.
    func claimForDelivery() -> Bool {
        lock.lock()
        guard !cancelled, committed, !delivered else { lock.unlock(); return false }
        delivered = true
        lock.unlock()
        return true
    }

    /// Relinquish the destination reservation only after the Photos completion
    /// returns. Claiming first protects against reentrant cancellation, while the
    /// reservation prevents a same-path replacement throughout the handoff.
    func completeDelivery() {
        lock.lock(); let wasDelivered = delivered; lock.unlock()
        guard wasDelivered else { return }
        Self.queue.async {
            if Self.destinationOwners[self.destination] == self.identity {
                Self.destinationOwners.removeValue(forKey: self.destination)
            }
        }
    }

    func start(jpeg: Data, completion: @escaping (PhotosOutputWrite, Result<Void, Failure>) -> Void) {
        lock.lock()
        precondition(!started, "Each output write is started once")
        started = true
        lock.unlock()
        Self.queue.async {
            #if DEBUG
            self.beforeWriteForTesting?()
            #endif
            let result = autoreleasepool { self.writeAndCommit(jpeg) }
            DispatchQueue.main.async { completion(self, result) }
        }
    }

    private func writeAndCommit(_ data: Data) -> Result<Void, Failure> {
        lock.lock(); let shouldStop = cancelled; lock.unlock()
        guard !shouldStop else { return .failure(.cancelled) }
        // This is our unique sibling staging path, never an input/original URL.
        // Keeping it beside the destination makes commit a same-volume rename.
        defer { removeOwnedStaging() }
        do { try data.write(to: staging, options: .atomic) }
        catch { return .failure(.writeFailed(error)) }

        lock.lock()
        guard !cancelled else { lock.unlock(); return .failure(.cancelled) }
        guard Self.destinationOwners[destination] == nil else {
            lock.unlock()
            return .failure(.writeFailed(CocoaError(.fileWriteFileExists)))
        }
        do {
            // No overwrite: if Photos unexpectedly supplied an occupied output,
            // fail without touching it. All owned commits/cleanup use this queue.
            try FileManager.default.moveItem(at: staging, to: destination)
            committed = true
            Self.destinationOwners[destination] = identity
            lock.unlock()
            return .success(())
        } catch {
            lock.unlock()
            return .failure(.writeFailed(error))
        }
    }

    private func removeOwnedStaging() {
        do {
            #if DEBUG
            if let remove = removeStagingForTesting { try remove(staging) }
            else { try FileManager.default.removeItem(at: staging) }
            #else
            try FileManager.default.removeItem(at: staging)
            #endif
        } catch {
            let error = error as NSError
            // Successful commit moved this exact staging file away. That absence
            // is expected; every other removal failure must remain observable.
            let absent = (error.domain == NSPOSIXErrorDomain && error.code == Int(ENOENT)) ||
                (error.domain == NSCocoaErrorDomain && error.code == CocoaError.Code.fileNoSuchFile.rawValue)
            guard !absent else { return }
            print("PHOTOS_OUTPUT_OWNED_STAGING_CLEANUP_FAILED domain=\(error.domain) code=\(error.code)")
            #if DEBUG
            stagingCleanupFailureForTesting?(error.domain, error.code)
            #endif
        }
    }

    private func removeAbandonedOutput() {
        lock.lock()
        let shouldRemove = cancelled && committed && !delivered
        lock.unlock()
        guard shouldRemove, Self.destinationOwners[destination] == identity else { return }
        // Queue confinement prevents a newer owned commit between this ownership
        // check and removal. A delivered file was relinquished and is not ours.
        do {
            try FileManager.default.removeItem(at: destination)
            Self.destinationOwners.removeValue(forKey: destination)
        } catch {
            // Surface cleanup failure rather than silently claiming abandonment
            // was cleaned. No broad deletion, retry or parent-directory removal.
            print("PHOTOS_OUTPUT_OWNED_CLEANUP_FAILED domain=\((error as NSError).domain) code=\((error as NSError).code)")
        }
    }
}
