import XCTest
@testable import CelluloidDomain

final class LatestImageWorkTests: XCTestCase {
    func testBurstRetainsOnlyOnePendingInputAndNeverRunsSupersededInputs() {
        let entered = expectation(description: "first worker entered")
        let callbacks = expectation(description: "all callers finish exactly once")
        callbacks.expectedFulfillmentCount = 201
        let release = DispatchSemaphore(value: 0)
        let ledger = Ledger()
        let work = LatestImageWork<Int, Int> { input, token in
            XCTAssertFalse(Thread.isMainThread)
            ledger.append(input)
            if input == 0 {
                entered.fulfill()
                XCTAssertEqual(release.wait(timeout: .now() + 10), .success)
            }
            try token.checkCancellation()
            return input
        }
        work.submit(0) { result in
            if case .success = result { XCTFail("Superseded active result published") }
            callbacks.fulfill()
        }
        wait(for: [entered], timeout: 10)
        for index in 1...200 {
            work.submit(index) { result in
                XCTAssertTrue(Thread.isMainThread)
                switch result {
                case .success(let output): XCTAssertEqual(output, 200)
                case .failure(let error): XCTAssertTrue(error is CancellationError); XCTAssertNotEqual(index, 200)
                }
                callbacks.fulfill()
            }
            XCTAssertEqual(work.snapshot.running, 1)
            XCTAssertEqual(work.snapshot.pending, 1)
        }
        release.signal()
        wait(for: [callbacks], timeout: 10)
        XCTAssertEqual(ledger.values, [0, 200])
        XCTAssertEqual(work.snapshot.started, 2)
        XCTAssertEqual(work.snapshot.finished, 2)
    }

    func testSupersessionAfterRenderBeforeDeliveryStillRejectsOldImage() {
        let rendered = DispatchSemaphore(value: 0)
        let delivery = DispatchQueue(label: "test.delayed-image-delivery")
        delivery.suspend()
        let done = expectation(description: "deliveries"); done.expectedFulfillmentCount = 2
        let work = LatestImageWork<Int, Int>(deliveryQueue: delivery) { input, _ in
            rendered.signal(); return input
        }
        work.submit(1) { result in
            if case .failure(let error) = result { XCTAssertTrue(error is CancellationError) }
            else { XCTFail("Old image escaped after newer input") }
            done.fulfill()
        }
        XCTAssertEqual(rendered.wait(timeout: .now() + 10), .success)
        work.submit(2) { result in
            XCTAssertEqual(try? result.get(), 2); done.fulfill()
        }
        delivery.resume()
        wait(for: [done], timeout: 10)
    }

    func testCancellationBeforeOperationAndAfterAwait() async throws {
        let work = LatestImageWork<Int, Int>(deliveryQueue: .global()) { input, token in
            try token.checkCancellation(); return input
        }
        let task = Task {
            while !Task.isCancelled { await Task.yield() }
            return try await work.value(for: 1)
        }
        task.cancel()
        do { _ = try await task.value; XCTFail("Cancelled task succeeded") }
        catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(work.snapshot.started, 0)
        let value = try await work.value(for: 2)
        XCTAssertEqual(value, 2)
    }

    func testCancelClearsPendingWithoutDroppingCompletion() {
        let entered = expectation(description: "entered")
        let done = expectation(description: "cancelled callers"); done.expectedFulfillmentCount = 2
        let release = DispatchSemaphore(value: 0)
        let ledger = Ledger()
        let work = LatestImageWork<Int, Int> { input, token in
            ledger.append(input); entered.fulfill()
            _ = release.wait(timeout: .now() + 10)
            try token.checkCancellation(); return input
        }
        let completion: (Result<Int, Error>) -> Void = { result in
            if case .failure(let error) = result { XCTAssertTrue(error is CancellationError) }
            else { XCTFail("Cancelled input published") }
            done.fulfill()
        }
        work.submit(1, completion: completion)
        wait(for: [entered], timeout: 10)
        work.submit(2, completion: completion)
        work.cancel()
        XCTAssertEqual(work.snapshot.pending, 0)
        release.signal()
        wait(for: [done], timeout: 10)
        XCTAssertEqual(ledger.values, [1])
    }

    func testTaskCancellationDuringOperationPropagatesToWorker() async {
        let entered = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        let work = LatestImageWork<Int, Int>(deliveryQueue: .global()) { input, token in
            entered.signal()
            _ = release.wait(timeout: .now() + 10)
            try token.checkCancellation()
            return input
        }
        let task = Task { try await work.value(for: 1) }
        let began = await Task.detached { entered.wait(timeout: .now() + 10) }.value
        XCTAssertEqual(began, .success)
        task.cancel(); release.signal()
        do { _ = try await task.value; XCTFail("Cancelled active task published") }
        catch { XCTAssertTrue(error is CancellationError) }
    }

    func testSupersededRasterIsReleasedWhileDeliveryQueueIsStalled() {
        let delivery = DispatchQueue(label: "test.stalled-delivery")
        delivery.suspend()
        let rendered = DispatchSemaphore(value: 0), released = DispatchSemaphore(value: 0)
        let callbacks = expectation(description: "callbacks"); callbacks.expectedFulfillmentCount = 2
        let work = LatestImageWork<Int, Payload>(deliveryQueue: delivery) { index, _ in
            let output = Payload { if index == 1 { released.signal() } }
            rendered.signal()
            return output
        }
        work.submit(1) { result in
            if case .success = result { XCTFail("Superseded raster published") }
            callbacks.fulfill()
        }
        XCTAssertEqual(rendered.wait(timeout: .now() + 10), .success)
        work.submit(2) { result in
            if case .failure = result { XCTFail("Current raster discarded") }
            callbacks.fulfill()
        }
        XCTAssertEqual(rendered.wait(timeout: .now() + 10), .success)
        XCTAssertEqual(released.wait(timeout: .now() + 10), .success,
                       "A stalled UI queue retained a completed stale raster")
        delivery.resume()
        wait(for: [callbacks], timeout: 10)
    }

    private final class Payload {
        let onDeinit: () -> Void
        init(onDeinit: @escaping () -> Void) { self.onDeinit = onDeinit }
        deinit { onDeinit() }
    }

    private final class Ledger: @unchecked Sendable {
        private let lock = NSLock()
        private var stored: [Int] = []
        func append(_ value: Int) { lock.lock(); stored.append(value); lock.unlock() }
        var values: [Int] { lock.lock(); defer { lock.unlock() }; return stored }
    }
}
