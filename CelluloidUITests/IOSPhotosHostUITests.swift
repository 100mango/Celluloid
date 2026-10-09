import XCTest
import UIKit

/// Diagnostic until this route passes on the actual supported Simulator image.
/// Every action resolves one visible public control; unknown UI stops with proof.
final class IOSPhotosHostUITests: XCTestCase {
    private let photos = XCUIApplication(bundleIdentifier: "com.apple.mobileslideshow")
    private var context: [String: Any] = [:]
    private var monitor: NSObjectProtocol?
    private var started: TimeInterval = 0
    private var stage = "not-started"
    private var recordedFailure = false
    private var didLaunchOwnedPhotos = false

    override func setUpWithError() throws {
        try super.setUpWithError(); continueAfterFailure = false
        executionTimeAllowance = 120
        let environment = ProcessInfo.processInfo.environment
        try XCTSkipUnless(environment["CELLULOID_IOS_PHOTOS_HOST"] == "1", "Dedicated owned Photos-host diagnostic only")
        #if !targetEnvironment(simulator)
        throw failure("Actual Photos host UI probe cannot run on a physical device")
        #endif
        guard environment["CELLULOID_IOS_PHOTOS_HOST"] == "1",
              let text = environment["CELLULOID_IOS_PHOTOS_HOST_CONTEXT"], text.utf8.count <= 64_000,
              let value = try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
              value["schema"] as? String == "celluloid.ios.photos-host.v1",
              value["source_sha"] as? String == environment["CELLULOID_EXPECTED_SOURCE_SHA"],
              value["public_filename_unique_asset_id"] as? String == value["asset_identifier"] as? String,
              value["album_identifier"] is String, value["before"] is [String: Any] else {
            throw failure("Missing prepared, source-bound, single-fixture album")
        }
        context = value; started = ProcessInfo.processInfo.systemUptime
        monitor = addUIInterruptionMonitor(withDescription: "Record and stop unknown Photos host interruption") { [weak self] alert in
            self?.checkpoint("unexpected-system-interruption")
            let proof = XCTAttachment(string: alert.debugDescription); proof.name = "ios-photos-host-unknown-alert"; proof.lifetime = .keepAlways
            self?.add(proof)
            fatalError("IOS_PHOTOS_HOST_UNKNOWN_ALERT no action taken")
        }
        XCUIDevice.shared.orientation = .portrait
        photos.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
    }
    override func tearDownWithError() throws {
        // Closing this owned Simulator process is not an alternative save path.
        if didLaunchOwnedPhotos, photos.state != .notRunning { photos.terminate() }
        didLaunchOwnedPhotos = false
        if let monitor = monitor { removeUIInterruptionMonitor(monitor) }
        monitor = nil
        try super.tearDownWithError()
    }
    override func record(_ issue: XCTIssue) {
        if !recordedFailure {
            recordedFailure = true
            print("IOS_PHOTOS_HOST_BLOCKED stage=\(stage)")
            checkpoint("blocked-" + stage)
        }
        super.record(issue)
    }

    func testActualPhotosExtensionSave() throws {
        try openOwnedPhoto()
        try openCelluloidExtension()
        stage = "select-sepia"
        try tap(photos.buttons.matching(identifier: "tool-filter"))
        try tap(photos.buttons.matching(identifier: "filter-Sepia"))
        stage = "add-owned-caption"
        try tap(photos.buttons.matching(identifier: "tool-bubble"))
        try tap(photos.buttons.matching(identifier: "bubble-option-0"))
        let text = try unique(photos.textViews.matching(identifier: "bubble-text"))
        text.tap(); text.typeText(try value("saved_caption"))
        try tap(photos.buttons.matching(identifier: "bubble-text-done"))
        _ = try artwork(caption: value("saved_caption"))
        checkpoint("extension-edited")
        stage = "extension-done"
        try tap(photos.buttons.matching(identifier: "Done"))
        try waitGone(photos.buttons["tool-filter"])
        checkpoint("photos-edit-after-extension")
        stage = "photos-done"
        try tap(photos.buttons.matching(identifier: "Done"))
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
        checkpoint("saved-in-photos")
        try completed("save")
    }

    func testActualPhotosExtensionReopenAndCancel() throws {
        guard context["saved"] is [String: Any] else { throw failure("Actual saved-resource readback is required") }
        try openOwnedPhoto()
        try openCelluloidExtension()
        let original = try value("saved_caption")
        let bubble = try artwork(caption: original)
        checkpoint("reopened-original-caption")
        stage = "edit-reopened-caption"
        bubble.tap()
        try tap(photos.buttons.matching(identifier: "bubble-edit-text"))
        let text = try unique(photos.textViews.matching(identifier: "bubble-text"))
        guard text.value as? String == original else { throw failure("Reopened recipe caption differs") }
        text.tap(); text.typeText(" cancelled")
        let changed = try XCTUnwrap(text.value as? String)
        guard changed != original, changed.replacingOccurrences(of: " cancelled", with: "") == original else {
            throw failure("A real pending caption change was not observed")
        }
        try tap(photos.buttons.matching(identifier: "bubble-text-done"))
        _ = try artwork(caption: changed)
        checkpoint("pending-cancelled-caption")
        stage = "extension-cancel"
        try tap(photos.buttons.matching(identifier: "Cancel"))
        // Apple documents Cancel -> Discard Changes. Observe the actual prompt;
        // never accept an unrelated alert or choose a positional/default action.
        try discardChangesIfShown()
        try waitGone(photos.buttons["tool-filter"])
        checkpoint("returned-from-extension-cancel")
        stage = "photos-cancel"
        try tap(photos.buttons.matching(identifier: "Cancel"))
        try discardChangesIfShown()
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
        checkpoint("cancelled-in-photos")
        try completed("reopen-cancel")
    }

    private func openOwnedPhoto() throws {
        stage = "launch-real-photos"
        try withinBudget()
        didLaunchOwnedPhotos = true
        photos.launch()
        guard photos.wait(for: .runningForeground, timeout: 10) else { throw failure("Photos did not enter foreground") }
        checkpoint("photos-launched")
        if context["saved"] != nil, photos.buttons["Edit"].exists {
            // Photos can restore its last single-photo screen across launches.
            // The exact public filename must still be established before Edit.
            try verifyPublicFilename()
            return
        }
        // Current public Photos route: Collections -> Albums -> exact album.
        // Names are documented route expectations, not assertions that iOS AX
        // has been observed. Missing/ambiguous nodes retain evidence and fail.
        stage = "open-collections"
        try tap(photos.buttons.matching(identifier: "Collections"))
        checkpoint("collections")
        stage = "open-albums"
        try tap(photos.buttons.matching(identifier: "Albums"))
        checkpoint("albums")
        stage = "open-owned-album"
        let title = try value("album_title")
        let titleNode = try unique(photos.staticTexts.matching(NSPredicate(format: "label == %@", title)))
        titleNode.tap()
        _ = try unique(photos.navigationBars.matching(identifier: title))
        let cells = photos.collectionViews.cells
        let cell = try unique(cells)
        checkpoint("single-owned-album-item")
        stage = "open-single-owned-photo"
        cell.tap()
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
        try verifyPublicFilename()
    }
    private func verifyPublicFilename() throws {
        stage = "verify-public-photo-filename"
        try tap(photos.buttons.matching(identifier: "Info"))
        // Photos may hide the file extension in its Info panel; require the
        // exact unique controlled basename, never a date/position heuristic.
        let filename = try value("fixture_filename")
        let basename = (filename as NSString).deletingPathExtension
        _ = try unique(photos.staticTexts.matching(NSPredicate(format: "label IN %@", [filename, basename])))
        checkpoint("owned-photo-info")
        try tap(photos.buttons.matching(identifier: "Info"))
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
    }
    private func openCelluloidExtension() throws {
        stage = "photos-edit"
        try tap(photos.buttons.matching(identifier: "Edit"))
        stage = "photos-more"
        try tap(photos.buttons.matching(identifier: "More"))
        checkpoint("editing-extensions-menu")
        stage = "invoke-celluloid-extension"
        try tap(photos.buttons.matching(identifier: "CelluloidPhotoExtension"))
        _ = try unique(photos.buttons.matching(identifier: "tool-filter"), timeout: 15)
        _ = try unique(photos.buttons.matching(identifier: "tool-bubble"))
        guard photos.state == .runningForeground else { throw failure("Real Photos host lost foreground") }
        checkpoint("actual-extension-ready")
    }
    private func artwork(caption: String) throws -> XCUIElement {
        try unique(photos.images.matching(identifier: "attachment-image").matching(NSPredicate(format: "value == %@", caption)))
    }
    private func discardChangesIfShown() throws {
        let discard = photos.buttons.matching(identifier: "Discard Changes")
        let appeared = discard.firstMatch.waitForExistence(timeout: 2)
        if appeared {
            checkpoint("discard-confirmation")
            try tap(discard)
        } else if photos.alerts.count > 0 || XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count > 0 {
            throw failure("Unknown cancellation/permission prompt; no action taken")
        }
    }
    private func unique(_ query: XCUIElementQuery, timeout: TimeInterval = 8) throws -> XCUIElement {
        try withinBudget()
        var ready: XCUIElement?
        let usable = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            let visible = query.allElementsBoundByIndex.filter { $0.isHittable }
            guard visible.count == 1, let element = visible.first, element.isEnabled else { return false }
            ready = element
            return true
        }, object: nil)
        // The real toolbar appears while asynchronous source decoding is still
        // loading. Its disabled state must become usable within this same bound.
        guard XCTWaiter.wait(for: [usable], timeout: timeout) == .completed, let element = ready else {
            throw failure("Expected one visible enabled public control at " + stage)
        }
        return element
    }
    private func tap(_ query: XCUIElementQuery) throws {
        let element = try unique(query)
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(element.label) identifier=\(element.identifier)")
        element.tap()
    }
    private func waitGone(_ element: XCUIElement) throws {
        try withinBudget()
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: element)], timeout: 20) == .completed else {
            throw failure("Host boundary did not complete at " + stage)
        }
    }
    private func withinBudget() throws {
        guard ProcessInfo.processInfo.systemUptime - started < 120 else { throw failure("Actual Photos UI case deadline reached") }
    }
    private func checkpoint(_ name: String) {
        guard didLaunchOwnedPhotos, photos.state != .notRunning else { return }
        let screenshot = XCTAttachment(screenshot: photos.screenshot()); screenshot.name = "ios-photos-host-" + name; screenshot.lifetime = .keepAlways; add(screenshot)
        let tree = XCTAttachment(string: String(photos.debugDescription.prefix(80_000))); tree.name = "ios-photos-host-" + name + "-ax"; tree.lifetime = .keepAlways; add(tree)
        print("IOS_PHOTOS_HOST_CHECKPOINT \(name) stage=\(stage)")
    }
    private func completed(_ event: String) throws {
        print("IOS_PHOTOS_HOST_UI " + String(decoding: try JSONSerialization.data(withJSONObject: [
            "event": event, "source_sha": value("source_sha"), "context_token": value("context_token"),
            "host_bundle": "com.apple.mobileslideshow", "album_identifier": value("album_identifier"),
            "asset_identifier": value("asset_identifier")], options: [.sortedKeys]), as: UTF8.self))
    }
    private func value(_ key: String) throws -> String { try XCTUnwrap(context[key] as? String) }
    private func failure(_ message: String) -> NSError { NSError(domain: "Celluloid.ActualPhotosUI", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
