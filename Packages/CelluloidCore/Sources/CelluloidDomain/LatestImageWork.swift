import Foundation

// No image allocation or lazy graphics-context initialization occurs on submit.
// All instances share a serial executor to bound concurrent raster allocations.
private let imageWorkExecutor = DispatchQueue(label: "Mango.Celluloid.image-work", qos: .userInitiated)

/// Cooperative cancellation between decoder/filter/materialization stages.
/// An in-progress ImageIO/Core Image call cannot be forcibly interrupted.
public final class ImageWorkCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    private var discardOutput: (() -> Void)?
    public init() {}
    public var isCancelled: Bool {
        lock.lock(); defer { lock.unlock() }; return cancelled
    }
    public func cancel() {
        lock.lock(); cancelled = true
        let discard = discardOutput; discardOutput = nil
        lock.unlock()
        discard?()
    }
    public func checkCancellation() throws {
        if isCancelled { throw CancellationError() }
    }
    fileprivate func onOutputCancellation(_ discard: @escaping () -> Void) {
        lock.lock()
        let runNow = cancelled
        if !runNow { discardOutput = discard }
        lock.unlock()
        if runNow { discard() }
    }
    fileprivate func clearOutputCancellation() {
        lock.lock(); discardOutput = nil; lock.unlock()
    }
}

/// One running request and one replaceable pending request per editor/session.
/// Superseded pending inputs are released immediately; they never enter the
/// raster executor. Cancelled/stale results cannot publish even if cancellation
/// arrived after rendering and before delivery. Output should be immutable.
public final class LatestImageWork<Input, Output>: @unchecked Sendable {
    public struct Snapshot {
        public let running: Int
        public let pending: Int
        public let started: Int
        public let finished: Int
    }
    private struct Job {
        let input: Input
        let token: ImageWorkCancellation
        let completion: (Result<Output, Error>) -> Void
    }
    private let lock = NSLock()
    private let deliveryQueue: DispatchQueue
    private let operation: (Input, ImageWorkCancellation) throws -> Output
    private var active: ImageWorkCancellation?
    private var pending: Job?
    private var latest: ImageWorkCancellation?
    private var draining = false
    private var started = 0
    private var finished = 0

    public init(deliveryQueue: DispatchQueue = .main,
                operation: @escaping (Input, ImageWorkCancellation) throws -> Output) {
        self.deliveryQueue = deliveryQueue; self.operation = operation
    }

    @discardableResult
    public func submit(_ input: Input, completion: @escaping (Result<Output, Error>) -> Void) -> ImageWorkCancellation {
        let token = ImageWorkCancellation()
        let job = Job(input: input, token: token, completion: completion)
        lock.lock()
        latest?.cancel()
        let replaced = pending
        pending = job; latest = token
        let start = !draining
        draining = true
        lock.unlock()
        if let replaced { deliver(replaced, result: .failure(CancellationError())) }
        if start { imageWorkExecutor.async { self.drain() } }
        return token
    }

    /// Cancels both slots. Safe on disappearance, a new source, or a new session.
    public func cancel() {
        lock.lock()
        latest?.cancel(); active?.cancel()
        let cancelled = pending
        pending = nil
        lock.unlock()
        if let cancelled { deliver(cancelled, result: .failure(CancellationError())) }
    }

    /// SwiftUI callers may cancel their Task; both cancellation-before-submit
    /// and cancellation-after-submit are propagated to the cooperative token.
    public func value(for input: Input) async throws -> Output {
        let cancellation = TaskCancellationRelay()
        return try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            let value: Output = try await withCheckedThrowingContinuation { continuation in
                let token = submit(input) { continuation.resume(with: $0) }
                cancellation.install(token)
            }
            try Task.checkCancellation()
            return value
        }, onCancel: { cancellation.cancel() })
    }

    public var snapshot: Snapshot {
        lock.lock(); defer { lock.unlock() }
        return Snapshot(running: active == nil ? 0 : 1, pending: pending == nil ? 0 : 1,
                        started: started, finished: finished)
    }

    private func drain() {
        dispatchPrecondition(condition: .notOnQueue(.main))
        lock.lock()
        guard let job = pending else { draining = false; lock.unlock(); return }
        pending = nil; active = job.token
        started += 1
        lock.unlock()
        let result: Result<Output, Error> = Result {
            try job.token.checkCancellation()
            let value = try operation(job.input, job.token)
            try job.token.checkCancellation()
            return value
        }
        lock.lock()
        active = nil; finished += 1
        let more = pending != nil
        if !more { draining = false }
        lock.unlock()
        deliver(job, result: result)
        // Yield between jobs so one continuously edited window cannot starve
        // another session sharing this process-wide raster executor.
        if more { imageWorkExecutor.async { self.drain() } }
    }

    private func deliver(_ job: Job, result: Result<Output, Error>) {
        // Do not retain the input (often many MB of original bytes) in the UI
        // callback queue. The token remains cancellable until actual delivery.
        let completion = job.completion, token = job.token
        let output = ImageWorkDelivery(result)
        // A stalled UI queue must not retain a series of completed stale CGImages.
        // Replacing the request drops its output immediately, before UI delivery.
        token.onOutputCancellation { output.discard() }
        deliveryQueue.async {
            let result = output.take()
            token.clearOutputCancellation()
            completion(token.isCancelled ? .failure(CancellationError()) : result)
        }
    }
}

private final class ImageWorkDelivery<Output>: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<Output, Error>?
    init(_ result: Result<Output, Error>) { self.result = result }
    func discard() {
        lock.lock(); result = .failure(CancellationError()); lock.unlock()
    }
    func take() -> Result<Output, Error> {
        lock.lock(); defer { lock.unlock() }
        let value = result ?? .failure(CancellationError())
        result = nil
        return value
    }
}

private final class TaskCancellationRelay: @unchecked Sendable {
    private let lock = NSLock()
    private var token: ImageWorkCancellation?
    private var cancelled = false
    func install(_ token: ImageWorkCancellation) {
        lock.lock()
        self.token = token
        if cancelled { token.cancel() }
        lock.unlock()
    }
    func cancel() {
        lock.lock(); cancelled = true; token?.cancel(); lock.unlock()
    }
}
