import XCTest
@testable import CelluloidDomain

final class CompanionJobTests: XCTestCase {
    private var request: CompanionRequest { CompanionRequest(sourceID: UUID(), sourceSHA256: String(repeating: "a", count: 64), sourceBytes: 120, filter: .fade) }
    func testExplicitPendingAndMatchingIdempotentCompletion() throws {
        let request = request
        var job = CompanionJob(request: request)
        XCTAssertEqual(job.phase, .pending)
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: String(repeating: "b", count: 64), pixelWidth: 512, pixelHeight: 340, failure: nil)
        job.markProcessing(); XCTAssertEqual(job.phase, .processing)
        try job.accept(response); XCTAssertEqual(job.phase, .completed)
        let before = job; try job.accept(response); XCTAssertEqual(job, before)
        XCTAssertEqual(try CompanionRequest.decode(request.encoded()), request)
        XCTAssertEqual(try CompanionResult.decode(response.encoded()), response)
        XCTAssertEqual(try JSONDecoder().decode(CompanionJob.self, from: JSONEncoder().encode(job)), job)
    }
    func testCancellationAndStaleRepliesCannotOverwriteCurrentState() throws {
        var job = CompanionJob(request: request); job.cancel()
        let response = CompanionResult(requestID: job.request.id, sourceSHA256: job.request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Not available")
        try job.accept(response); XCTAssertEqual(job.phase, .cancelled); XCTAssertNil(job.result)
        var active = CompanionJob(request: request)
        XCTAssertThrowsError(try active.accept(response)); XCTAssertEqual(active.phase, .pending)
    }
    func testRejectOversizeMalformedAndAmbiguousResponses() throws {
        XCTAssertThrowsError(try CompanionRequest(sourceID: UUID(), sourceSHA256: "bad", sourceBytes: 1, filter: .original).validate())
        XCTAssertThrowsError(try CompanionRequest(sourceID: UUID(), sourceSHA256: String(repeating: "0", count: 64), sourceBytes: 8 * 1024 * 1024 + 1, filter: .original).validate())
        XCTAssertThrowsError(try CompanionResult(requestID: UUID(), sourceSHA256: String(repeating: "0", count: 64), previewSHA256: String(repeating: "0", count: 64), pixelWidth: 513, pixelHeight: 1, failure: nil).validate())
        XCTAssertThrowsError(try CompanionResult.decode(Data(repeating: 0, count: 4097)))
        var job = CompanionJob(request: request)
        try job.accept(CompanionResult(requestID: job.request.id, sourceSHA256: job.request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Phone processing failed"))
        XCTAssertEqual(job.phase, .failed)
    }
    func testFailedResponseDeliveryCanRecoverAndLateFailureCannotDowngradeCompletion() throws {
        var job = CompanionJob(request: request)
        let failure = CompanionResult(requestID: job.request.id, sourceSHA256: job.request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Preview transfer failed")
        try job.accept(failure); XCTAssertEqual(job.phase, .failed)
        let delivered = CompanionResult(requestID: job.request.id, sourceSHA256: job.request.sourceSHA256, previewSHA256: String(repeating: "b", count: 64), pixelWidth: 512, pixelHeight: 340, failure: nil)
        try job.accept(delivered); XCTAssertEqual(job.phase, .completed)
        try job.accept(failure); XCTAssertEqual(job.phase, .completed); XCTAssertEqual(job.result, delivered)
        try job.validate()
        let altered = CompanionResult(requestID: job.request.id, sourceSHA256: job.request.sourceSHA256, previewSHA256: String(repeating: "c", count: 64), pixelWidth: 512, pixelHeight: 340, failure: nil)
        XCTAssertThrowsError(try job.accept(altered))
    }

}
