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
    private var didAttemptObservedWhatsNew = false
    private var didCompleteLateObservedWhatsNew = false
    private var didAttemptObservedNotificationDenial = false
    private var didUseLateObservedNotificationWindow = false

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
        let initialTabs = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
        let initialCollections = try observedNavigationWithinOriginalWait(navigationStage: "open-collections") { remaining in
            guard initialTabs.count <= 1 else { throw self.failure("Initial Collections identity is ambiguous") }
            guard initialTabs.count == 1 else { return nil }
            let target = initialTabs.element
            guard target.isHittable, target.isEnabled else { return nil }
            _ = try remaining()
            return target
        }
        stage = "open-collections"
        try tapObservedNavigationTarget(initialCollections)
        checkpoint("collections")
        try dismissObservedWhatsNewIfPresent()
        try declineObservedPhotosNotificationsIfPresent()
        try selectObservedCollections()
        _ = try declineLateObservedNotificationsIfNeeded()
        stage = "open-albums"
        let albums = try observedAlbumsWithinOriginalWait()
        try tapObservedNavigationTarget(albums)
        checkpoint("albums")
        stage = "open-owned-album"
        let title = try value("album_title")
        let titles = photos.staticTexts.matching(NSPredicate(format: "label == %@", title))
        let titleNode = try observedNavigationWithinOriginalWait(navigationStage: "open-owned-album") { remaining in
            guard titles.count <= 1 else { throw self.failure("Owned album title became ambiguous") }
            guard titles.count == 1 else { return nil }
            let node = titles.element
            guard node.label == title else { throw self.failure("Owned album title changed") }
            guard node.isHittable, node.isEnabled else { return nil }
            _ = try remaining()
            return node
        }
        try tapObservedNavigationTarget(titleNode)
        let cell = try observedOwnedAlbumItem(title: title)
        checkpoint("single-owned-album-item")
        stage = "open-single-owned-photo"
        try tapObservedNavigationTarget(cell)
        _ = try unique(photos.buttons.matching(identifier: "Edit"))
        try verifyPublicFilename()
    }
    @discardableResult
    private func dismissObservedWhatsNewIfPresent(recognitionDeadline: TimeInterval? = nil, wallDeadline: TimeInterval? = nil) throws -> TimeInterval {
        // Observed on run 37887244922 / iOS 27.0 (24A434): this informational
        // sheet appears after Collections opens. It contains no permission or
        // agreement. Accept only the exact observed page, never any Continue.
        let title = photos.staticTexts.matching(NSPredicate(format: "label == %@", "What’s New in Photos"))
        guard title.count > 0 else { return 0 }
        guard !didAttemptObservedWhatsNew else { throw failure("Repeated Photos introduction; no action taken") }
        var activeDeadline = recognitionDeadline ?? (started + 120)
        func remaining() throws -> TimeInterval {
            try withinBudget()
            guard didLaunchOwnedPhotos, photos.state == .runningForeground else {
                throw failure("Owned Photos introduction lost foreground")
            }
            let available = min(activeDeadline, started + 120) - ProcessInfo.processInfo.systemUptime
            guard available > 0 else { throw failure("Photos introduction exhausted its absolute deadline") }
            return min(8, available)
        }
        stage = "dismiss-observed-photos-whats-new"
        try withinBudget()
        guard photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
            throw failure("Unexpected alert over Photos introduction; no action taken")
        }
        _ = try unique(title, timeout: remaining())
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
        let actions = photos.buttons.matching(NSPredicate(format: "label == %@", "Continue"))
        let proceed = try unique(actions, timeout: remaining())
        guard title.count == 1, title.element.label == "What’s New in Photos", title.element.isHittable,
              actions.count == 1, proceed.label == "Continue", proceed.isHittable, proceed.isEnabled,
              photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
            throw failure("Exact Photos introduction recognition failed; no action taken")
        }
        // Recognition, including the three exact sections above, consumes the
        // original navigation wait. Only a recognized page may use one 24-second
        // handling allocation, with a caller-supplied 32-second whole-window bound.
        _ = try remaining()
        let handlingStarted = ProcessInfo.processInfo.systemUptime
        if let recognitionDeadline = recognitionDeadline {
            guard let wallDeadline = wallDeadline, handlingStarted < recognitionDeadline,
                  recognitionDeadline <= wallDeadline else {
                throw failure("Late or invalid Photos introduction recognition")
            }
            activeDeadline = min(min(handlingStarted + 24, wallDeadline), started + 120)
            print("IOS_PHOTOS_HOST_INTRO_TIMING phase=recognized started=\(handlingStarted) recognitionDeadline=\(recognitionDeadline) handlingDeadline=\(activeDeadline) wallDeadline=\(wallDeadline)")
        }
        checkpoint("observed-photos-whats-new")
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(proceed.label) identifier=\(proceed.identifier)")
        // Evidence and AX calls spend the same handling allocation. Resolve
        // all observed identities again before the one permitted tap.
        for label in observedSections {
            let section = photos.otherElements.matching(NSPredicate(format: "label == %@", label))
            guard section.count == 1, section.element.isHittable else {
                throw failure("Photos introduction changed before tap; no action taken")
            }
        }
        guard title.count == 1, title.element.label == "What’s New in Photos", title.element.isHittable,
              actions.count == 1, proceed.label == "Continue", proceed.isHittable, proceed.isEnabled,
              photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0,
              !didAttemptObservedWhatsNew else {
            throw failure("Photos introduction owner or public controls changed; no action taken")
        }
        _ = try remaining()
        didAttemptObservedWhatsNew = true
        proceed.tap()
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                    object: title.element)], timeout: try remaining()) == .completed else {
            throw failure("Observed Photos introduction did not close")
        }
        _ = try remaining()
        checkpoint("observed-photos-whats-new-dismissed")
        _ = try remaining()
        if recognitionDeadline != nil {
            print("IOS_PHOTOS_HOST_INTRO_TIMING phase=handled elapsed=\(ProcessInfo.processInfo.systemUptime - handlingStarted) handlingDeadline=\(activeDeadline)")
        }
        _ = try remaining()
        return ProcessInfo.processInfo.systemUptime - handlingStarted
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
    private func observedOwnedAlbumItem(title: String) throws -> ObservedNavigationTarget {
        // Run37915753706: the owned album has a collectionTitle heading and a
        // single grid Image, not a title-named navigation bar or collection cell.
        // Scope to the one observed page container; mirrored AX outside it is
        // never deduplicated by position or used as an alternative selection.
        try withinBudget()
        let pages = photos.otherElements.matching(identifier: "PhotosUICore.PhotosPageContainerView_AX")
        let observedPage = try observedNavigationWithinOriginalWait(navigationStage: "open-owned-album") { remaining in
            guard pages.count <= 1 else { throw self.failure("Expected one observed owned album page") }
            guard pages.count == 1, pages.element.exists else { return nil }
            _ = try remaining()
            return pages.element
        }
        let page = observedPage.element
        let heading = page.staticTexts.matching(identifier: "collectionTitle")
        let count = page.staticTexts.matching(identifier: "collectionAssetCount")
        let items = page.images.matching(identifier: "PXGGridLayout-Info")
        guard heading.count == 1, count.count == 1, items.count == 1,
              heading.element.label == title, count.element.label == "1 Item" else {
            throw failure("Owned album title, item count or unique photo differs")
        }
        // Keep the exact owned container, full title, one-item count and sole
        // grid Image after any recognized interruption. No generic relaxation.
        return try observedNavigationWithinOriginalWait(navigationStage: "open-owned-album") { remaining in
            guard pages.count == 1, page.exists,
                  heading.count == 1, count.count == 1, items.count == 1,
                  heading.element.label == title, count.element.label == "1 Item" else {
                throw self.failure("Owned album identity changed during introduction readiness")
            }
            guard heading.element.isHittable, heading.element.isEnabled,
                  count.element.isHittable, count.element.isEnabled,
                  items.element.isHittable, items.element.isEnabled else { return nil }
            // Add Photo is a separate Button. Header artwork has no grid identifier.
            // Only this album's sole grid Image may be tapped by the caller, which
            // still verifies the exact public fixture filename before editing.
            _ = try remaining()
            return items.element
        }
    }

    private func declineObservedPhotosNotificationsIfPresent(appearanceDeadline: TimeInterval? = nil, wallDeadline: TimeInterval? = nil) throws {
        // Run37912970403 screenshot after the introduction: only this exact
        // Photos notification request may be denied. Never grant notifications.
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let alerts = springboard.alerts
        var actionDeadline = started + 120
        func remaining() throws -> TimeInterval {
            try withinBudget()
            guard didLaunchOwnedPhotos, photos.state == .runningForeground else {
                throw failure("Owned Photos notification context lost foreground")
            }
            let available = min(actionDeadline, started + 120) - ProcessInfo.processInfo.systemUptime
            guard available > 0 else { throw failure("Photos notification handling deadline reached") }
            return min(8, available)
        }
        let appearanceTimeout: TimeInterval
        if let appearanceDeadline = appearanceDeadline {
            guard let wallDeadline = wallDeadline, appearanceDeadline <= wallDeadline,
                  ProcessInfo.processInfo.systemUptime < appearanceDeadline else {
                throw failure("Invalid or expired late notification appearance window")
            }
            appearanceTimeout = min(8, appearanceDeadline - ProcessInfo.processInfo.systemUptime)
            guard appearanceTimeout > 0 else { throw failure("Late notification appearance window expired") }
        } else { appearanceTimeout = 2 }
        guard alerts.firstMatch.waitForExistence(timeout: appearanceTimeout) else {
            guard photos.alerts.count == 0 else { throw failure("Unknown Photos alert; no action taken") }
            if let wallDeadline = wallDeadline {
                guard alerts.count == 0, ProcessInfo.processInfo.systemUptime < min(wallDeadline, started + 120) else {
                    throw failure("Late notification absence observation became uncertain")
                }
                print("IOS_PHOTOS_HOST_NOTIFICATION_TIMING phase=absent observed=\(ProcessInfo.processInfo.systemUptime) wallDeadline=\(wallDeadline)")
            }
            return
        }
        guard !didAttemptObservedNotificationDenial else { throw failure("Repeated notification denial; no action taken") }
        let observedAt = ProcessInfo.processInfo.systemUptime
        if let appearanceDeadline = appearanceDeadline {
            guard let wallDeadline = wallDeadline, observedAt < appearanceDeadline else {
                throw failure("Photos notification appeared after its authorized window")
            }
            actionDeadline = min(min(observedAt + 12, wallDeadline), started + 120)
            print("IOS_PHOTOS_HOST_NOTIFICATION_TIMING phase=appeared observed=\(observedAt) appearanceDeadline=\(appearanceDeadline) handlingDeadline=\(actionDeadline) wallDeadline=\(wallDeadline)")
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
        let decline = try unique(deny, timeout: remaining())
        _ = try unique(allow, timeout: remaining())
        // Retain one prompt screenshot and the alert AX above; avoid a second
        // full Photos AX traversal on this 120-second critical path.
        let screenshot = XCTAttachment(screenshot: photos.screenshot())
        screenshot.name = "ios-photos-host-observed-photos-notifications"; screenshot.lifetime = .keepAlways; add(screenshot)
        print("IOS_PHOTOS_HOST_CHECKPOINT observed-photos-notifications stage=\(stage)")
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(decline.label) identifier=\(decline.identifier)")
        // The exact owner-scoped prompt may change while evidence is saved.
        // Revalidate every observed field, then spend the same absolute clock.
        if appearanceDeadline != nil {
            let tabs = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
            guard didCompleteLateObservedWhatsNew, tabs.count == 1, tabs.element.isSelected else {
                throw failure("Late notification stage changed before denial; no action taken")
            }
        }
        guard alerts.count == 1, photos.alerts.count == 0, observed.count == 1,
              title.count == 1, body.count == 1, deny.count == 1, allow.count == 1,
              alert.buttons.count == 2,
              title.element.label == "“Photos” Would Like to Send You Notifications",
              body.element.label == "Notifications may include alerts, sounds, and icon badges. These can be configured in Settings.",
              title.element.isHittable, body.element.isHittable,
              decline.label == "Don’t Allow", decline.isHittable, decline.isEnabled,
              allow.element.label == "Allow", allow.element.isHittable, allow.element.isEnabled,
              !didAttemptObservedNotificationDenial else {
            throw failure("Observed notification changed before denial; no action taken")
        }
        _ = try remaining()
        didAttemptObservedNotificationDenial = true
        decline.tap()
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                    object: alert)], timeout: try remaining()) == .completed,
              springboard.alerts.count == 0, photos.alerts.count == 0 else {
            throw failure("Observed notification denial did not close the sole prompt")
        }
        _ = try remaining()
        print("IOS_PHOTOS_HOST_CHECKPOINT observed-photos-notifications-declined stage=\(stage)")
        if appearanceDeadline != nil {
            print("IOS_PHOTOS_HOST_NOTIFICATION_TIMING phase=denied elapsed=\(ProcessInfo.processInfo.systemUptime - observedAt) handlingDeadline=\(actionDeadline)")
        }
        _ = try remaining()
    }
    private func declineLateObservedNotificationsIfNeeded() throws -> TimeInterval {
        guard didCompleteLateObservedWhatsNew, !didAttemptObservedNotificationDenial,
              !didUseLateObservedNotificationWindow else { return 0 }
        // Only the observed post-introduction, selected-Collections stage.
        // No notification is required; absence after eight seconds continues
        // the original Albums action, whose generic monitor remains active.
        let windowStarted = ProcessInfo.processInfo.systemUptime
        let wallDeadline = min(windowStarted + 20, started + 120)
        let appearanceDeadline = min(windowStarted + 8, wallDeadline)
        // Consume this one route-wide window even when the prompt is absent.
        // The readiness and pre-Albums call sites must never renew it.
        didUseLateObservedNotificationWindow = true
        try withinBudget()
        let tabs = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
        guard didLaunchOwnedPhotos, photos.state == .runningForeground,
              tabs.count == 1, tabs.element.isSelected, photos.alerts.count == 0 else {
            throw failure("Late notification route lacks completed introduction or selected Collections")
        }
        print("IOS_PHOTOS_HOST_NOTIFICATION_TIMING phase=window started=\(windowStarted) appearanceDeadline=\(appearanceDeadline) wallDeadline=\(wallDeadline)")
        try declineObservedPhotosNotificationsIfPresent(appearanceDeadline: appearanceDeadline, wallDeadline: wallDeadline)
        try withinBudget()
        guard ProcessInfo.processInfo.systemUptime < wallDeadline else {
            throw failure("Late notification window exhausted")
        }
        return ProcessInfo.processInfo.systemUptime - windowStarted
    }
    private typealias ObservedNavigationTarget = (element: XCUIElement, deadline: TimeInterval)
    private func tapObservedNavigationTarget(_ target: ObservedNavigationTarget) throws {
        // Logs and checkpoint evidence spend the SAME returned wait deadline.
        // No new readiness timer is opened between resolving a target and tapping.
        let element = target.element
        print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(element.label) identifier=\(element.identifier)")
        try withinBudget()
        guard ProcessInfo.processInfo.systemUptime < target.deadline,
              didLaunchOwnedPhotos, photos.state == .runningForeground,
              photos.alerts.count == 0,
              XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0,
              element.exists, element.isHittable, element.isEnabled,
              photos.staticTexts.matching(NSPredicate(format: "label == %@", "What’s New in Photos")).count == 0 else {
            throw failure("Observed navigation target changed or expired before tap")
        }
        try withinBudget()
        guard ProcessInfo.processInfo.systemUptime < target.deadline else {
            throw failure("Original navigation wait deadline reached before tap")
        }
        element.tap()
    }
    private func observedNavigationWithinOriginalWait(navigationStage: String,
            observe: (() throws -> TimeInterval) throws -> XCUIElement?) throws -> ObservedNavigationTarget {
        // Runs37959948655,38410163549,38421747828 observed the same exact
        // introduction arriving during Collections, owned album, or Albums readiness.
        // Each original wait keeps eight effective seconds. The existing route-wide
        // introduction24s and notification20s allocations may be consumed once only.
        let waitingStarted = ProcessInfo.processInfo.systemUptime
        let wallDeadline = min(waitingStarted + 32, started + 120)
        let readinessWallDeadline = min(waitingStarted + 52, started + 120)
        var deadline = min(waitingStarted + 8, wallDeadline)
        var handlingElapsed: TimeInterval = 0
        func remaining() throws -> TimeInterval {
            try withinBudget()
            let available = min(deadline, readinessWallDeadline) - ProcessInfo.processInfo.systemUptime
            guard available > 0 else { throw failure("Original navigation wait deadline reached") }
            return min(8, available)
        }
        while true {
            _ = try remaining()
            guard didLaunchOwnedPhotos, photos.state == .runningForeground else {
                throw failure("Owned Photos navigation lost foreground")
            }
            let handled = try dismissObservedWhatsNewIfPresent(recognitionDeadline: min(deadline, wallDeadline), wallDeadline: wallDeadline)
            guard handled.isFinite, handled >= 0, handled <= 24 else {
                throw failure("Photos introduction handling allocation exceeded")
            }
            if handled > 0 {
                guard handlingElapsed == 0, didAttemptObservedWhatsNew else {
                    throw failure("Repeated Photos introduction handling allocation")
                }
                handlingElapsed = handled
                didCompleteLateObservedWhatsNew = true
                deadline = min(deadline + handled, wallDeadline)
                print("IOS_PHOTOS_HOST_INTRO_TIMING phase=navigation-resume navigation=\(navigationStage) handlingElapsed=\(handlingElapsed) readinessDeadline=\(deadline) wallDeadline=\(wallDeadline)")
            }
            if didCompleteLateObservedWhatsNew, !didAttemptObservedNotificationDenial,
               !didUseLateObservedNotificationWindow {
                let tabs = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
                guard tabs.count == 1 else { throw failure("Observed Collections identity changed before notification") }
                if tabs.element.isSelected {
                    _ = try remaining()
                    let notificationElapsed = try declineLateObservedNotificationsIfNeeded()
                    guard notificationElapsed.isFinite, notificationElapsed >= 0, notificationElapsed <= 20 else {
                        throw failure("Photos notification allocation exceeded")
                    }
                    deadline = min(deadline + notificationElapsed, readinessWallDeadline)
                    print("IOS_PHOTOS_HOST_NOTIFICATION_TIMING phase=navigation-resume navigation=\(navigationStage) elapsed=\(notificationElapsed) readinessDeadline=\(deadline) wallDeadline=\(readinessWallDeadline)")
                }
            }
            stage = navigationStage
            _ = try remaining()
            guard didLaunchOwnedPhotos, photos.state == .runningForeground,
                  photos.alerts.count == 0,
                  XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
                throw failure("Unexpected Photos interruption during navigation wait; no action taken")
            }
            // The caller resolves its full original identity and readiness anew,
            // including after dismissal. A sheet arriving during observation is
            // handled by this same loop, never by a new retry clock.
            if let element = try observe(remaining) {
                _ = try remaining()
                let introduction = photos.staticTexts.matching(NSPredicate(format: "label == %@", "What’s New in Photos"))
                if introduction.count > 0 { continue }
                _ = try remaining()
                guard didLaunchOwnedPhotos, photos.state == .runningForeground,
                      photos.alerts.count == 0,
                      XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
                    throw failure("Owned Photos navigation changed before target return")
                }
                _ = try remaining()
                return (element: element, deadline: min(deadline, readinessWallDeadline))
            }
            Thread.sleep(forTimeInterval: min(0.1, try remaining()))
        }
    }
    private func observedCollectionsWithinOriginalWait(_ query: XCUIElementQuery) throws -> ObservedNavigationTarget {
        try observedNavigationWithinOriginalWait(navigationStage: "select-observed-collections") { _ in
            guard query.count == 1 else { throw self.failure("Observed Collections identity changed during wait") }
            let element = query.element
            return element.isHittable && element.isEnabled ? element : nil
        }
    }
    private func observedAlbumsWithinOriginalWait() throws -> ObservedNavigationTarget {
        // Run38421747828 exposes this exact Albums disclosure under the selected
        // Collections tab; a similarly named control is never an alternative.
        let tabs = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))
        let query = photos.buttons.matching(identifier: "albums-shelf-details-disclosure").matching(NSPredicate(format: "label == %@", "Albums"))
        return try observedNavigationWithinOriginalWait(navigationStage: "open-albums") { remaining in
            guard tabs.count == 1, tabs.element.isSelected, query.count <= 1 else {
                throw self.failure("Observed Albums or selected Collections identity changed")
            }
            guard query.count == 1 else { return nil }
            let element = query.element
            guard element.label == "Albums", element.identifier == "albums-shelf-details-disclosure" else {
                throw self.failure("Observed Albums disclosure differs")
            }
            guard element.isHittable, element.isEnabled else { return nil }
            _ = try remaining()
            return element
        }
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
        let collections = try observedCollectionsWithinOriginalWait(query)
        if !collections.element.isSelected {
            let observedCollections = try observedNavigationWithinOriginalWait(navigationStage: "select-observed-collections") { remaining in
                guard query.count == 1, library.count == 1 else { throw self.failure("Observed Photos tab identity changed") }
                let libraryTab = library.element
                guard libraryTab.isSelected else { throw self.failure("Expected observed Library selection before Collections") }
                let target = query.element
                guard libraryTab.isHittable, libraryTab.isEnabled,
                      target.isHittable, target.isEnabled else { return nil }
                _ = try remaining()
                return target
            }
            try tapObservedNavigationTarget(observedCollections)
        }
        _ = try observedNavigationWithinOriginalWait(navigationStage: "select-observed-collections") { remaining in
            guard query.count <= 1, library.count <= 1 else { throw self.failure("Observed Photos tab identity became ambiguous") }
            guard query.count == 1, library.count == 1 else { return nil }
            let selected = query.element
            guard selected.isSelected, selected.isHittable, selected.isEnabled else { return nil }
            _ = try remaining()
            return selected
        }
        checkpoint("observed-collections-selected")
    }
    private func openCelluloidExtension() throws {
        stage = "photos-edit"
        try tap(photos.buttons.matching(identifier: "Edit"))
        stage = "photos-more"
        try tap(photos.buttons.matching(identifier: "More"))
        checkpoint("editing-extensions-menu")
        // Run37954719871: More presents a public Extensions submenu first.
        // Keep direct extension selection when already exposed; never guess
        // another extension, tap a coordinate or dismiss the keyboard tutorial.
        if photos.buttons.matching(identifier: "CelluloidPhotoExtension").count == 0 {
            stage = "open-observed-extensions-menu"
            try withinBudget()
            guard photos.alerts.count == 0,
                  XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {
                throw failure("Unknown alert before Extensions; no action taken")
            }
            let entry = photos.buttons.matching(NSPredicate(format: "label == %@", "Extensions"))
            guard entry.count == 1 else { throw failure("Expected one observed Extensions entry") }
            let button = try unique(entry)
            guard entry.count == 1, button.label == "Extensions",
                  button.isHittable, button.isEnabled,
                  photos.buttons.matching(identifier: "CelluloidPhotoExtension").count == 0 else {
                throw failure("Observed Extensions entry changed; no action taken")
            }
            print("IOS_PHOTOS_HOST_ACTION stage=\(stage) label=\(button.label) identifier=\(button.identifier)")
            try withinBudget()
            guard photos.alerts.count == 0,
                  XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0,
                  entry.count == 1, button.label == "Extensions",
                  button.isHittable, button.isEnabled,
                  photos.buttons.matching(identifier: "CelluloidPhotoExtension").count == 0 else {
                throw failure("Observed Extensions state changed before tap; no action taken")
            }
            button.tap()
            checkpoint("observed-extensions-opened")
        }
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
