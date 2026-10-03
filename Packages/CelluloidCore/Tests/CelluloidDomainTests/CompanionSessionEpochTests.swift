import XCTest
@testable import CelluloidDomain
final class CompanionSessionEpochTests: XCTestCase {
    func testDeactivationDuringRenderAndCounterpartSwitchRejectOldDelivery() throws {
        var session = CompanionSessionEpoch()
        XCTAssertNil(session.ticket); XCTAssertFalse(session.canDeliver(nil))
        session.activate(); let original = try XCTUnwrap(session.ticket)
        XCTAssertTrue(session.canDeliver(original))
        session.invalidate(); XCTAssertFalse(session.canDeliver(original)); XCTAssertNil(session.ticket)
        session.activate(); let switched = try XCTUnwrap(session.ticket)
        XCTAssertNotEqual(original, switched); XCTAssertFalse(session.canDeliver(original)); XCTAssertTrue(session.canDeliver(switched))
        for _ in 0..<100 { XCTAssertFalse(session.canDeliver(original)) }
    }
}
