import XCTest
import PhotosUI
import SwiftUI
@testable import Celluloid

@MainActor final class PhotoSelectionSessionTests: XCTestCase {
    func testHomeAndPickerPreparationDoNotReadOrRequestTheLibrary() {
        let library = StubSelectedPhotoLibrary()
        let session = PhotoSelectionSession(maximumSelection: 4, library: library)
        guard case .picking = session.phase else { return XCTFail("Expected idle picker") }
        XCTAssertEqual(library.requestCount, 0)
        XCTAssertTrue(library.lookups.isEmpty)
        let configuration = SystemPhotoPicker.configuration(maximumSelection: 4)
        XCTAssertEqual(configuration.selectionLimit, 4)
        XCTAssertEqual(configuration.selection, .ordered)
        XCTAssertEqual(configuration.preferredAssetRepresentationMode, .current)
        XCTAssertEqual(SystemPhotoPicker.configuration(maximumSelection: 1).selectionLimit, 1)
    }

    func testUnknownIdentityDoesNotFetchOrRequestPermission() {
        let library = StubSelectedPhotoLibrary()
        let session = PhotoSelectionSession(maximumSelection: 1, library: library)
        session.select(identifiers: [nil])
        guard case .recovery(.originalIdentityMissing) = session.phase else { return XCTFail("No silent imported-copy fallback") }
        XCTAssertTrue(library.lookups.isEmpty)
        XCTAssertEqual(library.requestCount, 0)
    }

    func testOnlyConfirmedIdentifiersReachResolver() async {
        let library = StubSelectedPhotoLibrary()
        let called = expectation(description: "Only selected metadata requested")
        library.didResolve = { called.fulfill() }
        let session = PhotoSelectionSession(maximumSelection: 4, library: library)
        session.select(identifiers: ["last", "first"])
        await fulfillment(of: [called], timeout: 2)
        XCTAssertEqual(library.lookups.map(\.orderedIdentifiers), [["last", "first"]])
        XCTAssertEqual(library.requestCount, 0)
        library.completeNext(.failure(PhotoSelectionError.originalUnavailable))
        await Task.yield()
        session.cancelPending()
    }

    func testCancelAndReselectInvalidateLateCallback() async {
        let library = StubSelectedPhotoLibrary()
        let called = expectation(description: "Lookup suspended")
        library.didResolve = { called.fulfill() }
        let session = PhotoSelectionSession(maximumSelection: 1, library: library)
        session.select(identifiers: ["old-selection"])
        await fulfillment(of: [called], timeout: 2)
        session.chooseAgain()
        library.completeNext(.failure(PhotoSelectionError.accessRequired))
        await Task.yield()
        guard case .picking = session.phase else { return XCTFail("A cancelled callback reopened recovery") }
    }

    func testGrantIsRequestedOnlyAfterExplicitAction() async {
        let library = StubSelectedPhotoLibrary()
        library.authorizationStatus = .denied
        let called = expectation(description: "Explicit grant action then metadata resolution")
        library.didResolve = { called.fulfill() }
        let session = PhotoSelectionSession(maximumSelection: 1, library: library)
        // Establish a valid selection without starting the explicit grant action.
        session.select(identifiers: ["selected"])
        await fulfillment(of: [called], timeout: 2)
        library.completeNext(.failure(PhotoSelectionError.accessRequired))
        await Task.yield()
        XCTAssertEqual(library.requestCount, 0)
        let retried = expectation(description: "Selection rechecked after explicit grant request")
        library.didResolve = { retried.fulfill() }
        session.requestAccess()
        await fulfillment(of: [retried], timeout: 2)
        XCTAssertEqual(library.requestCount, 1)
        library.completeNext(.failure(PhotoSelectionError.accessRequired))
        await Task.yield()
        XCTAssertEqual(session.authorization, .denied)
        session.cancelPending()
    }

    func testRealSelectedLookupPreservesOrderAndIdentity() async throws {
        guard PHPhotoLibrary.authorizationStatus(for: .readWrite) == .authorized else {
            throw XCTSkip("Requires the existing explicitly authorized synthetic-library CI phase")
        }
        let assets = try [803, 800, 802, 801].map {
            try XCTUnwrap(CelluloidTestFixtures.syntheticAsset(width: $0, height: 600))
        }
        let identifiers = assets.map(\.localIdentifier)
        let identity = try PhotoSelectionIdentity(identifiers: identifiers, maximumSelection: 4)
        let resolved = try await SelectedPhotoLibrary().resolve(identity)
        XCTAssertEqual(resolved.map(\.localIdentifier), identifiers)
    }

    func testDuplicatePickerFinishDeliversOnlyOnce() {
        var callbacks = 0
        let coordinator = SystemPhotoPicker.Coordinator { _ in callbacks += 1 }
        let picker = PHPickerViewController(configuration: SystemPhotoPicker.configuration(maximumSelection: 1))
        coordinator.picker(picker, didFinishPicking: [])
        coordinator.picker(picker, didFinishPicking: [])
        XCTAssertEqual(callbacks, 1)
    }

    func testSwiftUIHomeBuildsWithoutStartingSelection() {
        let host = UIHostingController(rootView: PhoneRootView())
        host.loadViewIfNeeded()
        host.view.frame = CGRect(x: 0, y: 0, width: 320, height: 568)
        host.view.layoutIfNeeded()
        XCTAssertNotNil(host.view)
    }
}

@MainActor private final class StubSelectedPhotoLibrary: SelectedPhotoLibraryAccess {
    var authorizationStatus: PHAuthorizationStatus = .notDetermined
    private(set) var requestCount = 0
    private(set) var lookups: [PhotoSelectionIdentity] = []
    private var continuations: [CheckedContinuation<[PHAsset], Error>] = []
    var didResolve: (() -> Void)?

    func requestOriginalEditingAccess() async -> PHAuthorizationStatus {
        requestCount += 1
        return authorizationStatus
    }

    func resolve(_ identity: PhotoSelectionIdentity) async throws -> [PHAsset] {
        lookups.append(identity)
        return try await withCheckedThrowingContinuation { continuation in
            continuations.append(continuation)
            didResolve?()
        }
    }

    func completeNext(_ result: Result<[PHAsset], Error>) {
        guard !continuations.isEmpty else { return XCTFail("No pending resolution") }
        continuations.removeFirst().resume(with: result)
    }
}
