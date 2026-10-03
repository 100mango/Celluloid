import XCTest
@testable import CelluloidPhoneCompanion

final class CompanionDeliveryGateTests: XCTestCase {
    func testInactiveAndPreviousCounterpartCannotEnqueue() {
        let gate = CompanionDeliveryGate(); var calls = 0
        XCTAssertNil(gate.ticket { true })
        XCTAssertFalse(gate.enqueue(nil, isSessionActive: { true }) { calls += 1 })
        gate.activate(); let first = gate.ticket { true }
        XCTAssertNotNil(first)
        XCTAssertFalse(gate.enqueue(first, isSessionActive: { false }) { calls += 1 })
        gate.invalidate { }
        gate.activate(); let second = gate.ticket { true }
        XCTAssertNotEqual(first, second)
        XCTAssertFalse(gate.enqueue(first, isSessionActive: { true }) { calls += 1 })
        XCTAssertTrue(gate.enqueue(second, isSessionActive: { true }) { calls += 1 })
        XCTAssertEqual(calls, 1)
    }
    func testInvalidationCannotPassAnInFlightEnqueueAndCapturesOnlyOldTransfers() throws {
        let gate = CompanionDeliveryGate(); gate.activate(); let ticket = gate.ticket { true }
        let entered = expectation(description: "Enqueue holds gate")
        let attempting = expectation(description: "Inactive callback attempts gate")
        let senderDone = expectation(description: "Enqueue returns")
        let cancelled = expectation(description: "Inactive capture finishes")
        let release = DispatchSemaphore(value: 0), inactiveFinished = DispatchSemaphore(value: 0)
        let state = Handles()
        DispatchQueue.global().async {
            XCTAssertTrue(gate.enqueue(ticket, isSessionActive: { true }) {
                entered.fulfill()
                XCTAssertEqual(release.wait(timeout: .now() + 3), .success)
                state.queued.append("old-result")
            })
            senderDone.fulfill()
        }
        wait(for: [entered], timeout: 2)
        DispatchQueue.global().async {
            attempting.fulfill()
            let captured = gate.invalidate { state.queued }
            state.captured = captured; inactiveFinished.signal(); cancelled.fulfill()
        }
        wait(for: [attempting], timeout: 2)
        XCTAssertEqual(inactiveFinished.wait(timeout: .now() + 0.05), .timedOut)
        release.signal(); wait(for: [senderDone, cancelled], timeout: 3)
        XCTAssertEqual(state.captured, ["old-result"])
        gate.activate(); let next = gate.ticket { true }
        XCTAssertTrue(gate.enqueue(next, isSessionActive: { true }) { state.queued.append("new-result") })
        XCTAssertEqual(state.captured, ["old-result"], "Cancellation snapshot must not include the newly active counterpart's transfer")
        XCTAssertEqual(state.queued, ["old-result", "new-result"])
        XCTAssertFalse(gate.enqueue(ticket, isSessionActive: { true }) { XCTFail("Old render must stay local") })
    }
    private final class Handles: @unchecked Sendable {
        // queued is accessed only inside the delivery gate until both workers
        // finish. captured is published before the expectation completes.
        var queued: [String] = []
        var captured: [String] = []
    }
}
