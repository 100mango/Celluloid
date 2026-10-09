import XCTest
@testable import Celluloid

final class PhotoSelectionIdentityTests: XCTestCase {
    func testOneToFourOrderedOriginalIdentities() throws {
        for count in 1...4 {
            let selected = (0..<count).map { "selected-\($0)" }
            let identity = try PhotoSelectionIdentity(identifiers: selected, maximumSelection: 4)
            XCTAssertEqual(identity.orderedIdentifiers, selected)
            XCTAssertEqual(try identity.ordered(Array(selected.reversed()), identifier: { $0 }), selected,
                           "PhotoKit fetch order is not the user's selection order")
        }
    }

    func testMissingOrUnavailableAssetNeverReturnsPartialSelection() throws {
        XCTAssertThrowsError(try PhotoSelectionIdentity(identifiers: [nil], maximumSelection: 1)) {
            XCTAssertEqual($0 as? PhotoSelectionError, .originalIdentityMissing)
        }
        XCTAssertThrowsError(try PhotoSelectionIdentity(identifiers: [""], maximumSelection: 1))
        let selection = try PhotoSelectionIdentity(identifiers: ["allowed", "outside-limited-set"], maximumSelection: 4)
        XCTAssertThrowsError(try selection.ordered(["allowed"], identifier: { $0 })) {
            XCTAssertEqual($0 as? PhotoSelectionError, .originalUnavailable)
        }
    }

    func testSelectionLimitAndDuplicatesAreRejectedWithoutTruncation() {
        let invalid: [[String?]] = [[], ["one", "two"], ["one", "one"]]
        for identifiers in invalid {
            XCTAssertThrowsError(try PhotoSelectionIdentity(identifiers: identifiers, maximumSelection: 1))
        }
        XCTAssertThrowsError(try PhotoSelectionIdentity(identifiers: ["1", "2", "3", "4", "5"], maximumSelection: 4))
        XCTAssertThrowsError(try PhotoSelectionIdentity(identifiers: ["1"], maximumSelection: 0))
    }

    func testUnselectedResultsCannotLeakIntoTheEditor() throws {
        let selection = try PhotoSelectionIdentity(identifiers: ["second", "first"], maximumSelection: 4)
        XCTAssertEqual(try selection.ordered(["other", "first", "second"], identifier: { $0 }), ["second", "first"])
    }
}
