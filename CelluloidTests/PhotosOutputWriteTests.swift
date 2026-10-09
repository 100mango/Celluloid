import XCTest
import Foundation
import Darwin

@MainActor
final class PhotosOutputWriteTests: XCTestCase {
    private var directory: URL!
    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("Celluloid-output-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws {
        drainWrites()
        try FileManager.default.removeItem(at: directory)
    }
    private func drainWrites() {
        let drained = expectation(description: "Owned output queue drained")
        PhotosOutputWrite.afterPendingWorkForTesting { drained.fulfill() }
        wait(for: [drained], timeout: 5)
    }
    private func url(_ name: String = "output.jpg") -> URL { directory.appendingPathComponent(name) }
    // The production writer runs at User-initiated QoS. Give its test-only
    // semaphore signal the same explicit QoS instead of inheriting XCTest's
    // potentially Utility test-thread priority. Cancellation/replacement still
    // happens on the test thread before this asynchronous release is submitted.
    private func releasePrewriteBarrier(_ release: DispatchSemaphore) {
        DispatchQueue.global(qos: .userInitiated).async(qos: .userInitiated, flags: .enforceQoS) {
            release.signal()
        }
    }
    private func assertEmpty(_ destination: URL, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path), file: file, line: line)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: directory.path), [], file: file, line: line)
    }
    func testCanceledBeforeStartNeverWritesAndCompletesOnce() {
        let operation = PhotosOutputWrite(destination: url())
        operation.cancel()
        let done = expectation(description: "Canceled write completion"); done.assertForOverFulfill = true
        operation.start(jpeg: Data("old".utf8)) { writer, result in
            if case .failure(.cancelled) = result {} else { XCTFail("Canceled write proceeded") }
            XCTAssertFalse(writer.claimForDelivery())
            done.fulfill()
        }
        wait(for: [done], timeout: 5); drainWrites(); assertEmpty(operation.destination)
    }
    func testCancellationAtObservedPrewriteBarrierPreventsAbandonedDestination() {
        let operation = PhotosOutputWrite(destination: url())
        let entered = expectation(description: "Actually reached pre-write boundary")
        let release = DispatchSemaphore(value: 0)
        operation.beforeWriteForTesting = {
            entered.fulfill()
            XCTAssertEqual(release.wait(timeout: .now() + 5), .success, "Pre-write test barrier timed out")
        }
        let done = expectation(description: "Canceled queued write completion"); done.assertForOverFulfill = true
        operation.start(jpeg: Data("old".utf8)) { _, result in
            if case .failure(.cancelled) = result {} else { XCTFail("Canceled queued write reached destination") }
            done.fulfill()
        }
        wait(for: [entered], timeout: 5)
        operation.cancel(); releasePrewriteBarrier(release)
        wait(for: [done], timeout: 5); drainWrites(); assertEmpty(operation.destination)
    }
    func testNewWriteSucceedsAfterSupersedingPausedOldWrite() throws {
        let old = PhotosOutputWrite(destination: url())
        let newer = PhotosOutputWrite(destination: url())
        let entered = expectation(description: "Old queued operation entered")
        let release = DispatchSemaphore(value: 0)
        old.beforeWriteForTesting = {
            entered.fulfill()
            XCTAssertEqual(release.wait(timeout: .now() + 5), .success, "Pre-write test barrier timed out")
        }
        let oldDone = expectation(description: "Old write canceled"); oldDone.assertForOverFulfill = true
        old.start(jpeg: Data("old".utf8)) { _, result in
            if case .failure(.cancelled) = result {} else { XCTFail("Old result was committed") }; oldDone.fulfill()
        }
        wait(for: [entered], timeout: 5)
        old.cancel()
        let newDone = expectation(description: "Replacement succeeds"); newDone.assertForOverFulfill = true
        newer.start(jpeg: Data("new".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Replacement failed: \(result)") }
            XCTAssertTrue(writer.claimForDelivery()); newDone.fulfill(); writer.completeDelivery()
        }
        releasePrewriteBarrier(release)
        wait(for: [oldDone, newDone], timeout: 5)
        old.cancel(); drainWrites()
        XCTAssertEqual(try Data(contentsOf: newer.destination), Data("new".utf8))
    }
    func testCancelAfterCommitBeforeDeliveryRemovesOnlyOwnedOutput() {
        let operation = PhotosOutputWrite(destination: url())
        let done = expectation(description: "Committed but not delivered")
        operation.start(jpeg: Data("private-output".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Write failed") }
            XCTAssertTrue(FileManager.default.fileExists(atPath: writer.destination.path))
            writer.cancel()
            XCTAssertFalse(writer.claimForDelivery())
            done.fulfill()
        }
        wait(for: [done], timeout: 5); drainWrites(); assertEmpty(operation.destination)
    }
    func testCancelAfterDeliveryDoesNotRemovePhotosOwnedOutput() throws {
        let operation = PhotosOutputWrite(destination: url())
        let done = expectation(description: "Host received output")
        operation.start(jpeg: Data("delivered".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Write failed") }
            XCTAssertTrue(writer.claimForDelivery())
            XCTAssertFalse(writer.claimForDelivery(), "Host delivery can only be claimed once")
            writer.cancel(); done.fulfill(); writer.completeDelivery()
        }
        wait(for: [done], timeout: 5); drainWrites()
        XCTAssertEqual(try Data(contentsOf: operation.destination), Data("delivered".utf8))
    }
    func testUnexpectedDestinationReuseCannotOverwriteOrDeleteAnotherOwner() throws {
        let old = PhotosOutputWrite(destination: url())
        let occupied = expectation(description: "First owned destination committed")
        old.start(jpeg: Data("first".utf8)) { _, result in
            if case .success = result {} else { XCTFail("Initial write failed") }; occupied.fulfill()
        }
        wait(for: [occupied], timeout: 5)
        let rejected = PhotosOutputWrite(destination: directory.appendingPathComponent("unused/../output.jpg"))
        XCTAssertEqual(rejected.destination, old.destination, "Canonical path aliases share one ownership identity")
        let rejectedDone = expectation(description: "Occupied destination safely rejected")
        rejected.start(jpeg: Data("second".utf8)) { writer, result in
            if case .failure(.writeFailed(_)) = result {} else { XCTFail("Existing destination was overwritten") }
            writer.cancel(); rejectedDone.fulfill()
        }
        wait(for: [rejectedDone], timeout: 5); drainWrites()
        XCTAssertEqual(try Data(contentsOf: old.destination), Data("first".utf8))
        old.cancel(); drainWrites(); assertEmpty(old.destination)
        let replacement = PhotosOutputWrite(destination: url())
        let replacementDone = expectation(description: "New owner after old cleanup")
        replacement.start(jpeg: Data("replacement".utf8)) { _, result in
            if case .success = result {} else { XCTFail("Replacement failed") }; replacementDone.fulfill()
        }
        wait(for: [replacementDone], timeout: 5)
        old.cancel(); rejected.cancel(); drainWrites()
        XCTAssertEqual(try Data(contentsOf: replacement.destination), Data("replacement".utf8), "Late cleanup does not own the replacement")
        XCTAssertTrue(replacement.claimForDelivery())
        replacement.completeDelivery()
    }
    func testClaimRetainsDestinationReservationUntilHostCompletionReturns() throws {
        let operation = PhotosOutputWrite(destination: url())
        let claimed = expectation(description: "Photos handoff began")
        operation.start(jpeg: Data("handed-off".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Initial write failed") }
            XCTAssertTrue(writer.claimForDelivery()); claimed.fulfill()
        }
        wait(for: [claimed], timeout: 5)
        // Model a consumer moving its file during the callback. The reservation,
        // not just file existence, must still protect that in-progress handoff.
        try FileManager.default.removeItem(at: operation.destination)
        let collision = PhotosOutputWrite(destination: url())
        let blocked = expectation(description: "In-progress host destination remains reserved")
        collision.start(jpeg: Data("too-early".utf8)) { writer, result in
            if case .failure(.writeFailed(_)) = result {} else { XCTFail("Claimed handoff reservation was released too early") }
            writer.cancel(); blocked.fulfill()
        }
        wait(for: [blocked], timeout: 5); drainWrites()
        XCTAssertFalse(FileManager.default.fileExists(atPath: operation.destination.path))
        operation.completeDelivery(); drainWrites()
        let later = PhotosOutputWrite(destination: url())
        let done = expectation(description: "Destination available after actual handoff return")
        later.start(jpeg: Data("after-return".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Post-handoff operation failed") }
            XCTAssertTrue(writer.claimForDelivery()); writer.completeDelivery(); done.fulfill()
        }
        wait(for: [done], timeout: 5); drainWrites()
        XCTAssertEqual(try Data(contentsOf: later.destination), Data("after-return".utf8))
    }

    func testNonMissingStagingCleanupFailureIsReportedWithoutClaimingDeletion() throws {
        let existing = url(); try Data("existing-unowned-destination".utf8).write(to: existing)
        let operation = PhotosOutputWrite(destination: existing)
        var staging: URL?
        var failures: [(String, Int)] = []
        operation.removeStagingForTesting = { path in
            staging = path
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(EACCES))
        }
        operation.stagingCleanupFailureForTesting = { failures.append(($0, $1)) }
        let done = expectation(description: "Occupied output plus simulated staging removal failure")
        done.assertForOverFulfill = true
        operation.start(jpeg: Data("retained-stage".utf8)) { writer, result in
            if case .failure(.writeFailed(_)) = result {} else { XCTFail("Occupied destination was replaced") }
            XCTAssertFalse(writer.claimForDelivery()); writer.cancel(); done.fulfill()
        }
        wait(for: [done], timeout: 5); drainWrites()
        XCTAssertEqual(failures.count, 1)
        XCTAssertEqual(failures.first?.0, NSPOSIXErrorDomain)
        XCTAssertEqual(failures.first?.1, Int(EACCES))
        let retained = try XCTUnwrap(staging)
        XCTAssertEqual(retained.deletingLastPathComponent(), directory.standardizedFileURL.resolvingSymlinksInPath())
        XCTAssertTrue(retained.lastPathComponent.hasPrefix(".Celluloid-"))
        XCTAssertEqual(try Data(contentsOf: retained), Data("retained-stage".utf8), "Failed deletion remains a real retained file, not a claimed cleanup success")
        XCTAssertEqual(try Data(contentsOf: existing), Data("existing-unowned-destination".utf8))

        let success = PhotosOutputWrite(destination: url("successful.jpg"))
        var unexpectedAbsenceFailures = 0
        success.stagingCleanupFailureForTesting = { _, _ in unexpectedAbsenceFailures += 1 }
        let moved = expectation(description: "Normal move leaves expected absent staging")
        success.start(jpeg: Data("normal".utf8)) { writer, result in
            if case .success = result {} else { XCTFail("Normal commit failed") }
            XCTAssertTrue(writer.claimForDelivery()); writer.completeDelivery(); moved.fulfill()
        }
        wait(for: [moved], timeout: 5); drainWrites()
        XCTAssertEqual(unexpectedAbsenceFailures, 0)
        // tearDown removes only this test's private temporary directory. No
        // filesystem permissions were changed to manufacture the error branch.
    }

    func testFileWriteFailureCompletesOnceWithoutAReplacement() {
        let destination = url("missing-parent").appendingPathComponent("output.jpg")
        let operation = PhotosOutputWrite(destination: destination)
        let done = expectation(description: "Write error once"); done.assertForOverFulfill = true
        operation.start(jpeg: Data("bytes".utf8)) { writer, result in
            if case .failure(.writeFailed(_)) = result {} else { XCTFail("Missing parent did not fail") }
            XCTAssertFalse(writer.claimForDelivery()); writer.cancel(); done.fulfill()
        }
        wait(for: [done], timeout: 5); drainWrites(); assertEmpty(destination)
    }
}
