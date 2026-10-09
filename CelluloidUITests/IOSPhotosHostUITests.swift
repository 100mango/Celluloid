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
        try dismissObservedWhatsNewIfPresent()
        try declineObservedPhotosNotificationsIfPresent()
        try selectObservedCollections()
        stage = "open-albums"
        try tap(photos.buttons.matching(identifier: "Albums"))
        checkpoint("albums")
        stage = "open-owned-album"
        let title = try value("album_title")
        let titleNode = try unique(photos.staticTexts.matching(NSPredicate(format: "label == %@", title)))
        titleNode.tap()
        let cell = try observedOwnedAlbumItem(title: title)
        checkpoint("single-owned-album-item")
        stage = "open-single-owned-photo"
        cell.tap()
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
        try verifyPublicFilename()
    }
    private func dismissObservedWhatsNewIfPresent() throws {
        // Observed on run 37887244922 / iOS 27.0 (24A434): this informational
        // sheet appears after Collections opens. It contains no permission or
        // agreement. Accept only the exact observed page, never any Continue.
        let title = photos.staticTexts.matching(NSPredicate(format: "label == %@", "What’s New in Photos"))
        guard title.count > 0 else { return }
        stage = "dismiss-observed-photos-whats-new"
        try withinBudget()
        guard photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
            throw failure("Unexpected alert over Photos introduction; no action taken")
        }
        _ = try unique(title)
        let observedSections = [
            "Improved Shared Albums, Share photos and videos in their original resolution with all of your friends and family, even if they don’t have an Apple device.",
            "New Ways to Organize, Quickly locate photos with Captured by Me and Identity Documents in Utilities. Use star ratings and keywords to mark your best shots.",
            "New Ways to Enjoy, Play a selection of photos and videos as a slideshow, and save the best frame of a video as a still photo."
        ]
        for label in observedSections {
            let section = photos.otherElements.matching(NSPredicate(format: "label == %@", label))
            guard section.count == 1, section.element.isHittable else {
                throw failure("Photos introduction differs from observed page; no action taken")
            }
        }
        let proceed = try unique(photos.buttons.matching(NSPredicate(format: "label == %@", "Continue")))
        checkpoint("observed-photos-whats-new")
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(proceed.label) identifier=\(proceed.identifier)")
        proceed.tap()
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                    object: title.element)], timeout: 8) == .completed else {
            throw failure("Observed Photos introduction did not close")
        }
        checkpoint("observed-photos-whats-new-dismissed")
    }
    private func verifyPublicFilename() throws {
        stage = "verify-public-photo-filename"
        try tap(photos.buttons.matching(identifier: "Info"))
        // Photos may hide the file extension in its Info panel; require the
        // exact unique controlled basename, never a date/position heuristic.
        let filename = try value("fixture_filename")
        let basename = (filename as NSString).deletingPathExtension
        // Run37918693951: Photos exposes the public filename as this field's
        // String value. Its label is "Filename", never the filename itself.
        let fields = photos.staticTexts.matching(identifier: "com.apple.photos.infoPanel.filename")
        let field = try unique(fields)
        guard fields.count == 1, field.label == "Filename",
              let publicFilename = field.value as? String,
              [filename, basename].contains(publicFilename) else {
            throw failure("Observed public filename differs from the exact owned fixture")
        }
        checkpoint("owned-photo-info")
        try tap(photos.buttons.matching(identifier: "Info"))
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
    }
    private func observedOwnedAlbumItem(title: String) throws -> XCUIElement {
        // Run37915753706: the owned album has a collectionTitle heading and a
        // single grid Image, not a title-named navigation bar or collection cell.
        // Scope to the one observed page container; mirrored AX outside it is
        // never deduplicated by position or used as an alternative selection.
        try withinBudget()
        let pages = photos.otherElements.matching(identifier: "PhotosUICore.PhotosPageContainerView_AX")
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            pages.count == 1 && pages.element.exists
        }, object: nil)
        guard XCTWaiter.wait(for: [ready], timeout: 8) == .completed else {
            throw failure("Expected one observed owned album page")
        }
        let page = pages.element
        let heading = page.staticTexts.matching(identifier: "collectionTitle")
        let count = page.staticTexts.matching(identifier: "collectionAssetCount")
        let items = page.images.matching(identifier: "PXGGridLayout-Info")
        guard heading.count == 1, count.count == 1, items.count == 1,
              heading.element.label == title, count.element.label == "1 Item" else {
            throw failure("Owned album title, item count or unique photo differs")
        }
        _ = try unique(heading)
        _ = try unique(count)
        // Add Photo is a separate Button. Header artwork has no grid identifier.
        // Only this album's sole grid Image may be tapped by the caller, which
        // still verifies the exact public fixture filename before editing.
        return try unique(items)
    }
    private func declineObservedPhotosNotificationsIfPresent() throws {
        // Run37912970403 screenshot after the introduction: only this exact
        // Photos notification request may be denied. Never grant notifications.
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let alerts = springboard.alerts
        guard alerts.firstMatch.waitForExistence(timeout: 2) else {
            guard photos.alerts.count == 0 else { throw failure("Unknown Photos alert; no action taken") }
            return
        }
        stage = "decline-observed-photos-notifications"
        try withinBudget()
        guard alerts.count == 1, photos.alerts.count == 0 else {
            throw failure("Multiple or unexpected Photos notification prompts; no action taken")
        }
        let proof = XCTAttachment(string: String(alerts.element.debugDescription.prefix(80_000)))
        proof.name = "ios-photos-host-notification-candidate-ax"; proof.lifetime = .keepAlways; add(proof)
        // Keep the action query scoped to this title and body even if the
        // system replaces its alert between observation and tap resolution.
        let observed = alerts.containing(.staticText, identifier: "“Photos” Would Like to Send You Notifications")
            .containing(.staticText, identifier: "Notifications may include alerts, sounds, and icon badges. These can be configured in Settings.")
        guard observed.count == 1 else { throw failure("Unknown notification prompt; no action taken") }
        let alert = observed.element
        let title = alert.staticTexts.matching(NSPredicate(format: "label == %@", "“Photos” Would Like to Send You Notifications"))
        let body = alert.staticTexts.matching(NSPredicate(format: "label == %@", "Notifications may include alerts, sounds, and icon badges. These can be configured in Settings."))
        let deny = alert.buttons.matching(NSPredicate(format: "label == %@", "Don’t Allow"))
        let allow = alert.buttons.matching(NSPredicate(format: "label == %@", "Allow"))
        guard title.count == 1, body.count == 1, deny.count == 1, allow.count == 1,
              alert.buttons.count == 2, title.element.isHittable, body.element.isHittable else {
            throw failure("Notification prompt differs from observed Photos request; no action taken")
        }
        let decline = try unique(deny)
        _ = try unique(allow)
        // Retain one prompt screenshot and the alert AX above; avoid a second
        // full Photos AX traversal on this 120-second critical path.
        let screenshot = XCTAttachment(screenshot: photos.screenshot())
        screenshot.name = "ios-photos-host-observed-photos-notifications"; screenshot.lifetime = .keepAlways; add(screenshot)
        print("IOS_PHOTOS_HOST_CHECKPOINT observed-photos-notifications stage=\(stage)")
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(decline.label) identifier=\(decline.identifier)")
        decline.tap()
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                    object: alert)], timeout: 8) == .completed,
              springboard.alerts.count == 0, photos.alerts.count == 0 else {
            throw failure("Observed notification denial did not close the sole prompt")
        }
        print("IOS_PHOTOS_HOST_CHECKPOINT observed-photos-notifications-declined stage=\(stage)")
    }
    private func selectObservedCollections() throws {
        // The same run showed LibraryTab still selected after the introductory
        // overlay consumed the first tap. Resolve the observed tabs afresh.
        stage = "select-observed-collections"
        try withinBudget()
        guard photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
            throw failure("Unknown alert before Collections; no action taken")
        }
        let query = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
        let library = photos.buttons.matching(identifier: "LibraryTab").matching(NSPredicate(format: "label == %@", "Library"))
        guard query.count == 1, library.count == 1 else { throw failure("Observed Photos tab identity changed") }
        let collections = try unique(query)
        if !collections.isSelected {
            guard try unique(library).isSelected else { throw failure("Expected observed Library selection before Collections") }
            print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(collections.label) identifier=\(collections.identifier)")
            collections.tap()
        }
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in collections.isSelected },
                    object: nil)], timeout: 8) == .completed else {
            throw failure("Observed Collections tab did not become selected")
        }
        checkpoint("observed-collections-selected")
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
