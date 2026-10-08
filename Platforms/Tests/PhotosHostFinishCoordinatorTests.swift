import XCTest
@testable import CelluloidMac

final class PhotosHostFinishCoordinatorTests: XCTestCase {
    @MainActor func testCancelSuppressesLateOutputAndUnlocksEditingWithoutHostCallback() async {
        let coordinator = PhotosHostFinishCoordinator<Int>()
        let started = expectation(description: "Output preparation started")
        let returned = expectation(description: "Independent operation resolved")
        var resume: CheckedContinuation<Int, Never>?
        var states: [Bool] = [], callbacks = 0, failures = 0
        coordinator.finish(preparing: { states.append($0) }, failed: { _ in failures += 1 }, operation: {
            let value = await withCheckedContinuation { continuation in resume = continuation; started.fulfill() }
            returned.fulfill(); return value
        }, completion: { _ in callbacks += 1 })
        await fulfillment(of: [started], timeout: 2)
        XCTAssertEqual(states, [true])
        coordinator.cancel(); XCTAssertEqual(states, [true, false])
        resume?.resume(returning: 42)
        await fulfillment(of: [returned], timeout: 2)
        await Task.yield()
        XCTAssertEqual(callbacks, 0); XCTAssertEqual(failures, 0)
    }
    @MainActor func testSupersededHostFinishCannotCompleteNewSessionOrReenableIt() async {
        let coordinator = PhotosHostFinishCoordinator<Int>()
        let oldStarted = expectation(description: "Old request started")
        let oldReturned = expectation(description: "Old request resolved")
        let newStarted = expectation(description: "New request rendering remains pending")
        let newFinished = expectation(description: "New request finished")
        var oldResume: CheckedContinuation<Int, Never>?
        var newResume: CheckedContinuation<Int, Never>?
        var outputs: [Int] = [], oldStates: [Bool] = [], newStates: [Bool] = []
        coordinator.finish(preparing: { oldStates.append($0) }, failed: { _ in XCTFail() }, operation: {
            let value = await withCheckedContinuation { oldResume = $0; oldStarted.fulfill() }
            oldReturned.fulfill(); return value
        }, completion: { _ in XCTFail("Superseded completion must not reach Photos") })
        await fulfillment(of: [oldStarted], timeout: 2)
        coordinator.finish(preparing: { newStates.append($0) }, failed: { _ in XCTFail() }, operation: {
            await withCheckedContinuation { newResume = $0; newStarted.fulfill() }
        }, completion: {
            if let value = $0 { outputs.append(value) }; newFinished.fulfill()
        })
        await fulfillment(of: [newStarted], timeout: 2)
        oldResume?.resume(returning: 1)
        await fulfillment(of: [oldReturned], timeout: 2); await Task.yield()
        XCTAssertEqual(oldStates, [true, false])
        XCTAssertEqual(newStates, [true], "A superseded operation must not unlock the newer render's controls")
        XCTAssertTrue(outputs.isEmpty)
        newResume?.resume(returning: 2)
        await fulfillment(of: [newFinished], timeout: 2)
        XCTAssertEqual(newStates, [true, false]); XCTAssertEqual(outputs, [2])
    }
    @MainActor func testSynchronousCancellationFromPreparingStartsNoOperation() async {
        let coordinator = PhotosHostFinishCoordinator<Int>()
        var operations = 0, completions = 0
        coordinator.finish(preparing: { if $0 { coordinator.cancel() } }, failed: { _ in XCTFail() }, operation: {
            operations += 1; return 1
        }, completion: { _ in completions += 1 })
        await Task.yield()
        XCTAssertEqual(operations, 0); XCTAssertEqual(completions, 0)
    }
    @MainActor func testFailureObserverCancellationStillSuppressesPhotosCallback() async {
        let coordinator = PhotosHostFinishCoordinator<Int>()
        let observed = expectation(description: "Failure observed")
        var completions = 0
        coordinator.finish(preparing: { _ in }, failed: { _ in coordinator.cancel(); observed.fulfill() }, operation: {
            throw CocoaError(.fileReadCorruptFile)
        }, completion: { _ in completions += 1 })
        await fulfillment(of: [observed], timeout: 2); await Task.yield()
        XCTAssertEqual(completions, 0)
    }
    @MainActor func testCurrentFailureCompletesNilExactlyOnceAndReenablesEditing() async {
        let coordinator = PhotosHostFinishCoordinator<Int>()
        let finished = expectation(description: "Active error reaches Photos")
        var states: [Bool] = [], callbacks = 0, failures = 0
        coordinator.finish(preparing: { states.append($0) }, failed: { _ in failures += 1 }, operation: {
            throw CocoaError(.fileReadCorruptFile)
        }, completion: { value in XCTAssertNil(value); callbacks += 1; finished.fulfill() })
        await fulfillment(of: [finished], timeout: 2)
        coordinator.cancel()
        XCTAssertEqual(states, [true, false]); XCTAssertEqual(callbacks, 1); XCTAssertEqual(failures, 1)
    }
}
