import XCTest
import AppKit
import CoreGraphics
import CoreFoundation
import CoreImage
import Darwin
import zlib
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

/// Opt-in, real Apple Photos host-entry v3. This test never instantiates the
/// extension controller and deliberately cannot certify the complete host E2E.
final class MacPhotosHostUITests: XCTestCase {
    private static let hostEntryContract = "Celluloid.PhotosHostEntry.3"
    private var interruption: NSObjectProtocol?
    private var contextHash = ""
    private var proofSequence = 0
    private var proofBytes = 0
    private var emittedProofs = Set<String>()
    private var emittedDiagnostics = Set<String>()
    private var context: [String: Any] = [:]
    private var stage = "not-started"
    private var firstBlockedOperation: [String: Any]?
    private var extensionMenuObservation: [String: Any]?
    private static let lifecycleContract = "Celluloid.PhotosFilterLifecycle.1"
    private static let fixtureFilename = "Celluloid-Owned-Host.png"
    private static let lifecyclePhases = ["source-retained", "fade-ready", "saved-export", "reopened-fade",
        "cancelled-export", "reverted-export", "unmodified-original", "reopened-original"]
    private var lifecycleDeadlineSeconds = 600
    private var testStarted: TimeInterval = 0
    private var lifecyclePhotosPID: pid_t = 0
    private var lifecycleAssetLabel = ""
    private var singlePhotoTopologies: [String] = []
    private var lifecycleComplete = false
    private var lifecycleRows: [[String: Any]] = []
    private var lifecycleControls: [Int] = []
    private var lifecycleControlCatalog: [[Any]] = []
    private var exportOptionBindings: [[Any]] = []
    private var exportBinaryStates: [[Any]] = []
    private var binaryScalarSelfTested = false
    private var lifecycleImages: [String: [String: Any]] = [:]
    private var lifecycleExports: [String: [String: Any]] = [:]
    private var retainedPNGHashes: [String: String] = [:]
    private var exportPNGDiagnostics: [[String: Any]] = []
    private var lifecyclePNGBytes = 0
    private var lifecycleRawBytes = 0
    private var lifecycleICC: [String: Any]?
    private var retainedSource: LifecycleRaster?
    private var retainedFixtureURL: URL?
    private var lifecycleRoot: URL?
    private struct LifecycleRaster {
        let bytes: Data
        let rgba: Data
        let metadata: [String: Any]
    }
    private struct BinaryScalar {
        let kind: String
        let runtimeType: String
        let encoding: String
        let raw: Any
        let state: Int
    }

    override func setUpWithError() throws {
        try super.setUpWithError()
        continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["CELLULOID_MAC_PHOTOS_HOST_PREREQUISITE"] == "1" else {
            throw XCTSkip("Dedicated ephemeral Photos-host prerequisite lane only")
        }
        interruption = addUIInterruptionMonitor(withDescription: "Abort unknown Photos-host interruption") { _ in
            print("MAC_HOST_FAIL_CLOSED_ABORT unexpected interruption; no alert action taken")
            fatalError("MAC_HOST_FAIL_CLOSED_ABORT")
        }
        let input = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_MAC_HOST_CONTEXT"])
        let data = try Data(contentsOf: URL(fileURLWithPath: input))
        XCTAssertLessThan(data.count, 2_000_000)
        context = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(context["app_id"] as? String, "Mango.Celluloid")
        XCTAssertEqual(context["extension_id"] as? String, "Mango.Celluloid.CelluloidPhotoExtension")
        XCTAssertEqual(context["host_entry_contract"] as? String, Self.hostEntryContract)
        let route = try XCTUnwrap(context["validation_route"] as? [String: Any])
        let clock = try XCTUnwrap(context["host_clock_profile"] as? [String: Any])
        let hostOnly = route["scope"] as? String == "photos-export-observation"
        lifecycleDeadlineSeconds = hostOnly ? 900 : 600
        XCTAssertEqual(clock["name"] as? String, hostOnly ? "photos-export-observation-900-v1" : "canonical-600-v1")
        XCTAssertEqual(clock["case_seconds"] as? Int, lifecycleDeadlineSeconds)
        XCTAssertEqual(clock["test_seconds"] as? Int, hostOnly ? 960 : 660)
        XCTAssertEqual(clock["process_seconds"] as? Int, hostOnly ? 1020 : 720)
        contextHash = digest(data)
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("script_path"))), try value("script_sha256"))
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("test_source_path"))), try value("test_source_sha256"))
    }
    override func tearDownWithError() throws {
        defer { if let interruption { removeUIInterruptionMonitor(interruption) }; interruption = nil }
        try super.tearDownWithError()
    }

    @MainActor func testInstalledExtensionIsInvokedByActualPhotos() throws {
        testStarted = ProcessInfo.processInfo.systemUptime
        try verifyBinaryScalarContract()
        try verifyInternationalTextContract()
        // Validate the exact read-only input before any host UI action. Only
        // XCTest stdout/attachments carry data back across the sandbox boundary.
        try report(["schema": "Celluloid.HostTransport.3", "host_entry_contract": Self.hostEntryContract, "source_sha": try value("source_sha"),
                    "context_sha256": contextHash, "test_source_sha256": try value("test_source_sha256"),
                    "verifier_sha256": try value("script_sha256"),
                    "app_executable_sha256": try value("app_executable_sha256"),
                    "extension_executable_sha256": try value("extension_executable_sha256"),
                    "extension_debug_dylib_sha256": try value("extension_debug_dylib_sha256"),
                    "external_writes": false, "context_validated": true], named: "transport.json")
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        var photosIdentityVerified = false
        defer {
            // Preserve the original failure before any optional AX/screenshot
            // request can itself fail. This record grants no host acceptance.
            var outcome: [String: Any] = ["source_sha": context["source_sha"] as? String ?? "missing",
                "last_stage": stage, "host_entry_contract": Self.hostEntryContract, "complete_host_e2e": false,
                "save_reopen_cancel_revert": lifecycleComplete ? "PhotosFilterLifecycle.1 complete" : "PhotosFilterLifecycle.1 incomplete"]
            if let firstBlockedOperation { outcome["first_blocked_operation"] = firstBlockedOperation }
            if !exportPNGDiagnostics.isEmpty { outcome["export_png_diagnostics"] = exportPNGDiagnostics }
            if let extensionMenuObservation { outcome["extension_menu_observation"] = extensionMenuObservation }
            if retainedSource != nil {
                try? report(lifecycleReceipt(photosPID: lifecyclePhotosPID), named: "lifecycle.json")
            }
            try? report(outcome, named: "outcome.json")
            if photosIdentityVerified, (try? remainingTime(1)) != nil {
                do { try checkpoint(photos, "last-observed", screenshot: true) }
                catch { print("MAC_HOST_DIAGNOSTIC_FAILED " + String(error.localizedDescription.prefix(1000))) }
            }
        }
        stage = "launch-exact-installed-containing-app"
        let appURL = URL(fileURLWithPath: try value("app_path")).standardizedFileURL.resolvingSymlinksInPath()
        let app = XCUIApplication(url: appURL)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        _ = try remainingTime(1); app.launch()
        let candidates = NSRunningApplication.runningApplications(withBundleIdentifier: "Mango.Celluloid")
        XCTAssertEqual(candidates.count, 1, "An unexpected containing app instance makes identity ambiguous")
        let running = try XCTUnwrap(candidates.first)
        XCTAssertEqual(running.bundleURL?.standardizedFileURL.resolvingSymlinksInPath(), appURL)
        XCTAssertEqual(running.executableURL?.standardizedFileURL.resolvingSymlinksInPath().path, try value("app_executable"))
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("app_executable"))), try value("app_executable_sha256"))
        try report(["bundle": appURL.path, "executable": try value("app_executable"), "pid": running.processIdentifier], named: "containing-process.json")
        let startupCancel = app.windows["open-panel"].buttons["CancelButton"]
        if startupCancel.waitForExistence(timeout: try remainingTime(3)) { try deadlineClick(startupCancel) }
        _ = try remainingTime(1); app.terminate()

        // Host-entry v3 tests documented Photos UI behavior. No registry query
        // is retried or relocated; the historical denied operation stays failed.

        stage = "photos-first-use-and-synthetic-import"
        photos.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        _ = try remainingTime(1); photos.launch()
        let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        XCTAssertEqual(hosts.count, 1)
        let host = try XCTUnwrap(hosts.first)
        XCTAssertEqual(host.bundleURL?.path, "/System/Applications/Photos.app")
        try report(["bundle": host.bundleURL!.path, "executable": host.executableURL?.path ?? "", "pid": host.processIdentifier], named: "photos-process.json")
        photosIdentityVerified = true
        let photosPID = host.processIdentifier
        lifecyclePhotosPID = photosPID
        // The sole first-use action already observed and qualified in the base
        // Photos27 synthetic-library lane. No account/permission alert is accepted.
        let started = photos.buttons["Get Started"]
        if started.waitForExistence(timeout: try remainingTime(5)) { try deadlineClick(started) }
        try checkpoint(photos, "initial")
        let seed = try XCTUnwrap(context["seed"] as? [String: Any])
        let mode = try XCTUnwrap(seed["mode"] as? String)
        let assets = photos.collectionViews["photos_collection_view"].descendants(matching: .any).matching(identifier: "mediaKind_asset")
        var fixtureHash: String
        if mode == "reuse-exact-sole-seeded-asset" {
            XCTAssertEqual(seed["source_sha"] as? String, try value("source_sha"))
            XCTAssertEqual(seed["app_executable_sha256"] as? String, try value("app_executable_sha256"))
            XCTAssertEqual(seed["initial_count"] as? Int, 0); XCTAssertEqual(seed["imported_count"] as? Int, 1)
            XCTAssertEqual(seed["width"] as? Int, 1200); XCTAssertEqual(seed["height"] as? Int, 800)
            XCTAssertEqual(seed["fixture_kind"] as? String, "native-ui-solid-blue")
            XCTAssertTrue(assets.firstMatch.waitForExistence(timeout: try remainingTime(20))); XCTAssertEqual(assets.count, 1)
            XCTAssertEqual(assets.firstMatch.label, seed["asset_label"] as? String)
            fixtureHash = try XCTUnwrap(seed["fixture_sha256"] as? String)
            try report(seed, named: "fixture.json")
        } else {
            XCTAssertEqual(mode, "require-empty-library")
            let empty = photos.staticTexts["_NS:99"]
            XCTAssertTrue(empty.waitForExistence(timeout: try remainingTime(10)))
            XCTAssertEqual(empty.value as? String, "Welcome to Photos", "Never import into an unknown populated library")
            XCTAssertEqual(assets.count, 0)
            let fixture = try makeFixture(); fixtureHash = try digest(fixture)
            try importFixture(fixture, into: photos)
        }
        try checkpoint(photos, "imported")
        XCTAssertTrue(assets.firstMatch.waitForExistence(timeout: try remainingTime(20)))
        XCTAssertEqual(assets.count, 1, "Only the freshly imported owned synthetic asset may be opened")
        XCTAssertTrue(assets.firstMatch.isHittable)
        let selectedAssetLabel = assets.firstMatch.label
        lifecycleAssetLabel = selectedAssetLabel
        try report(["source_sha": try value("source_sha"), "mode": mode,
                    "initial_count": 0, "selected_count": assets.count,
                    "asset_label": selectedAssetLabel, "fixture_sha256": fixtureHash,
                    "app_executable_sha256": try value("app_executable_sha256"),
                    "width": 1200, "height": 800], named: "fixture-ownership.json")
        try deadlineClick(assets.firstMatch, twice: true)
        try checkpoint(photos, "single-photo")

        stage = "observe-edit-controls"
        // Apple documents Edit, Extensions, Manage and Celluloid's display name.
        // These are runtime queries, not a claim their actual AX roles are known.
        // An absent/ambiguous/not-hittable control stops without coordinates.
        try clickNamed("Edit", in: photos)
        try checkpoint(photos, "editing")
        stage = "observe-extensions-menu"
        try clickNamed("Extensions", in: photos)
        let celluloid = try openedExtensionItems(in: photos)
        let menuCount = celluloid.count
        let menuEnabled: Bool? = menuCount == 1 ? celluloid.element(boundBy: 0).isEnabled : nil
        let menuHittable: Bool? = menuCount == 1 ? celluloid.element(boundBy: 0).isHittable : nil
        let classification = menuCount == 0 ? "no-matching-item" : menuCount != 1 ? "ambiguous"
            : menuEnabled != true ? "disabled" : menuHittable != true ? "not-hittable" : "selectable"
        // Save bounded observations in the stdout outcome before optional AX or
        // screenshot export can fail. Missing properties are null, not false.
        extensionMenuObservation = ["schema": "Celluloid.HostMenuObservation.2", "acceptance": false,
            "menu_title": "Celluloid", "menu_identifier": "editWithPlugin:",
            "menu_scope": "Extensions.menuButton/childMenu/directMenuItem", "extension_menu_button_count": 1,
            "opened_menu_count": 1, "menu_count": menuCount,
            "menu_enabled": menuEnabled.map { $0 as Any } ?? NSNull(),
            "menu_hittable": menuHittable.map { $0 as Any } ?? NSNull(), "classification": classification]
        try checkpoint(photos, "extensions", screenshot: true)
        if menuCount != 1 || menuEnabled != true || menuHittable != true {
            stage = "extension-not-selectable"
            throw block("Exact Celluloid item is not uniquely selectable in the opened Extensions menu; no settings action was taken")
        }
        let editorCountBefore = editorMatches(in: photos).count
        XCTAssertEqual(editorCountBefore, 0, "An already-present editor cannot prove this host transition")
        var selection = try hostObservation(expectedPID: photosPID, fixtureHash: fixtureHash, assetLabel: selectedAssetLabel)
        stage = "revalidate-extension-before-invoke"
        let invocationItems = try openedExtensionItems(in: photos)
        let invocationMenuCount = invocationItems.count
        let invocationEnabled: Bool? = invocationMenuCount == 1 ? invocationItems.element(boundBy: 0).isEnabled : nil
        let invocationHittable: Bool? = invocationMenuCount == 1 ? invocationItems.element(boundBy: 0).isHittable : nil
        guard invocationMenuCount == menuCount, invocationMenuCount == 1,
              invocationEnabled == menuEnabled, invocationEnabled == true,
              invocationHittable == menuHittable, invocationHittable == true else {
            throw block("Celluloid menu state changed before invocation",
                operation: ["menu_count": invocationMenuCount,
                    "menu_enabled": invocationEnabled.map { $0 as Any } ?? NSNull(),
                    "menu_hittable": invocationHittable.map { $0 as Any } ?? NSNull()])
        }
        selection.merge(["schema": "Celluloid.HostSelection.3", "menu_title": "Celluloid",
            "menu_identifier": "editWithPlugin:", "menu_scope": "Extensions.menuButton/childMenu/directMenuItem",
            "extension_menu_button_count": 1, "opened_menu_count": 1,
            "menu_count": invocationMenuCount, "menu_enabled": invocationEnabled == true,
            "menu_hittable": invocationHittable == true,
            "editor_count_before": editorCountBefore]) { _, new in new }
        try report(selection, named: "host-selection.json")
        stage = "invoke-real-photos-extension"
        try deadlineClick(invocationItems.element(boundBy: 0))
        stage = "observe-ready-editor-before-process"
        try report(readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash,
            assetLabel: selectedAssetLabel, phase: "before-process"), named: "host-editor-before-process.json")
        try checkpoint(photos, "host-editor")
        stage = "bind-extension-self-identity"
        let firstIdentity = try selfIdentityObservation(in: photos, allowWait: true)
        let secondIdentity = try selfIdentityObservation(in: photos, allowWait: false)
        guard firstIdentity.raw == secondIdentity.raw else { throw block("Editing identity changed between observations") }
        try report(["schema": "Celluloid.HostSelfIdentity.1", "host_entry_contract": Self.hostEntryContract,
            "source_sha": try value("source_sha"), "photos_pid": photosPID,
            "fixture_sha256": fixtureHash, "asset_label": selectedAssetLabel,
            "identity_identifier": "photos-extension.self-identity", "identity_element_counts": [firstIdentity.count, secondIdentity.count],
            "observations": [firstIdentity, secondIdentity].map { item in
                ["raw": item.raw, "bytes": item.raw.utf8.count, "sha256": digest(Data(item.raw.utf8))] as [String: Any]
            }], named: "extension-self-identity.json")
        stage = "observe-ready-editor-after-process"
        try report(readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash,
            assetLabel: selectedAssetLabel, phase: "after-process"), named: "host-editor-after-process.json")
        stage = "host-entry-prerequisite-passed"
        try report(["host_entry_contract": Self.hostEntryContract, "prerequisite_passed": true, "complete_host_e2e": false,
                    "production_source_base": try value("base_sha"), "source_sha": try value("source_sha"),
                    "pending": ["exact host save/cancel/revert/export UI", "resource and geometry readback", "complete lifecycle pixel oracle"]], named: "prerequisite.json")
        print("MAC_HOST_PREREQUISITE_PASSED actual Photos invocation and own-bundle identity self-observed by the extension; OS-wide uniqueness and full lifecycle unexecuted")
        try runFilterLifecycle(in: photos, photosPID: photosPID, fixtureHash: fixtureHash,
            assetLabel: selectedAssetLabel, baselineIdentity: firstIdentity.raw)

    }

    @MainActor private func importFixture(_ fixture: URL, into photos: XCUIApplication) throws {
        let file = photos.menuBarItems["File"]
        XCTAssertTrue(file.waitForExistence(timeout: try remainingTime(10))); try deadlineClick(file)
        let item = photos.menuItems["_NS:1096"] // Observed Photos27 Import… identity in base evidence.
        XCTAssertTrue(item.exists && item.isEnabled); try deadlineClick(item)
        try deadlineKey(photos, "g", modifierFlags: [.command, .shift])
        try deadlineKey(photos, "a", modifierFlags: .command); try deadlineText(photos, fixture.path)
        try deadlineKey(photos, .return, modifierFlags: [])
        let open = photos.sheets["open-panel"].buttons["OKButton"]
        XCTAssertTrue(open.waitForExistence(timeout: try remainingTime(10))); try deadlineClick(open)
        let review = photos.buttons["Review for Import"]
        if review.waitForExistence(timeout: try remainingTime(3)) { try deadlineClick(review) }
        let all = photos.buttons["Import All New Photos"]
        if all.waitForExistence(timeout: try remainingTime(3)) { try deadlineClick(all) }
        XCTAssertFalse(photos.sheets["open-panel"].exists)
    }
    @MainActor private func namedControls(_ label: String, in app: XCUIApplication) -> [XCUIElement] {
        let exact = NSPredicate(format: "label == %@", label)
        return app.buttons.matching(exact).allElementsBoundByIndex
            + app.popUpButtons.matching(exact).allElementsBoundByIndex
            + app.descendants(matching: .menuButton).matching(exact).allElementsBoundByIndex
            + app.menuItems.matching(exact).allElementsBoundByIndex
    }
    @MainActor private func clickNamed(_ label: String, in app: XCUIApplication) throws {
        let controls = namedControls(label, in: app)
        guard controls.count == 1, controls[0].isEnabled, controls[0].isHittable else {
            try checkpoint(app, "missing-control-" + label.lowercased())
            throw block("Actual control is missing/ambiguous/not hittable: " + label)
        }
        try deadlineClick(controls[0])
    }
    @MainActor private func openedExtensionItems(in photos: XCUIApplication) throws -> XCUIElementQuery {
        // Exact title/identifier and parent relationship observed in e723 AX.
        // Title is a public macOS XCTest attribute, distinct from label.
        let buttons = photos.descendants(matching: .menuButton).matching(NSPredicate(format: "label == %@", "Extensions"))
        let buttonCount = buttons.count
        guard buttonCount == 1 else { throw block("Missing or ambiguous Extensions menu button") }
        let menus = buttons.element(boundBy: 0).children(matching: .menu)
        let menuCount = menus.count
        guard menuCount == 1 else { throw block("Missing or ambiguous opened Extensions menu") }
        let menu = menus.element(boundBy: 0)
        guard menu.exists, !menu.frame.isEmpty else { throw block("Extensions menu is not visibly open") }
        return menu.children(matching: .menuItem).matching(NSPredicate(format: "title == %@ AND identifier == %@", "Celluloid", "editWithPlugin:"))
    }
    @MainActor private func editorMatches(in photos: XCUIApplication) -> XCUIElementQuery {
        photos.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Celluloid photo editor"))
    }
    @MainActor private func hostObservation(expectedPID: pid_t, fixtureHash: String, assetLabel: String) throws -> [String: Any] {
        let matches = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        XCTAssertEqual(matches.count, 1)
        let host = try XCTUnwrap(matches.first)
        XCTAssertEqual(host.processIdentifier, expectedPID, "Photos changed during the host-entry observation")
        XCTAssertEqual(host.bundleURL?.path, "/System/Applications/Photos.app")
        XCTAssertEqual(host.executableURL?.path, "/System/Applications/Photos.app/Contents/MacOS/Photos")
        return ["host_entry_contract": Self.hostEntryContract, "source_sha": try value("source_sha"),
            "photos_pid": host.processIdentifier, "photos_bundle": host.bundleURL!.path,
            "photos_executable": host.executableURL!.path, "fixture_sha256": fixtureHash, "asset_label": assetLabel]
    }
    @MainActor private func readyEditorObservation(in photos: XCUIApplication, expectedPID: pid_t,
        fixtureHash: String, assetLabel: String, phase: String) throws -> [String: Any] {
        let matches = editorMatches(in: photos)
        func observations() -> [String: Any] {
            // Each dynamic count is sampled once and reused for all decisions.
            // An observed duplicate must not disappear into a later query.
            let editorCount = matches.count
            var row: [String: Any] = ["schema": "Celluloid.HostEditor.2", "phase": phase,
                "editor_label": "Celluloid photo editor", "editor_count": editorCount]
            guard editorCount == 1 else { return row }
            let editor = matches.element(boundBy: 0)
            func labelled(_ label: String) -> XCUIElementQuery {
                editor.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label))
            }
            let filter = editor.descendants(matching: .any).matching(identifier: "photos-extension.filter")
            let filterCount = filter.count
            row.merge(["preview_label": "Edited photo preview", "preview_count": labelled("Edited photo preview").count,
                "placeholder_count": labelled("Current photo from Photos").count,
                "preparing_count": labelled("Preparing photo").count,
                "filter_identifier": "photos-extension.filter", "filter_count": filterCount,
                "filter_enabled": filterCount == 1 && filter.element(boundBy: 0).isEnabled,
                "read_only_count": editor.descendants(matching: .any).matching(identifier: "photos-extension.read-only").count,
                "error_count": editor.descendants(matching: .any).matching(identifier: "photos-extension.error").count]) { _, new in new }
            return row
        }
        func ready(_ row: [String: Any]) -> Bool {
            return row["editor_count"] as? Int == 1 && row["preview_count"] as? Int == 1 && row["placeholder_count"] as? Int == 0
                && row["preparing_count"] as? Int == 0 && row["filter_count"] as? Int == 1
                && row["filter_enabled"] as? Bool == true && row["read_only_count"] as? Int == 0
                && row["error_count"] as? Int == 0
        }
        if phase == "before-process" {
            var contradiction: String?
            let expectation = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
                guard hosts.count == 1, let host = hosts.first,
                      host.processIdentifier == expectedPID,
                      host.bundleURL?.path == "/System/Applications/Photos.app",
                      host.executableURL?.path == "/System/Applications/Photos.app/Contents/MacOS/Photos" else {
                    contradiction = "Photos identity changed during host-entry readiness"; return true
                }
                let row = observations()
                if (row["editor_count"] as? Int ?? 0) > 1 {
                    contradiction = "Ambiguous Celluloid editor during host entry"; return true
                }
                for key in ["preview_count", "placeholder_count", "preparing_count", "filter_count"] {
                    if (row[key] as? Int ?? 0) > 1 {
                        contradiction = "Ambiguous editor control during host entry: " + key; return true
                    }
                }
                if (row["read_only_count"] as? Int ?? 0) > 0 || (row["error_count"] as? Int ?? 0) > 0 {
                    contradiction = "Read-only or error state during host entry"; return true
                }
                return ready(row)
            }, object: nil)
            guard XCTWaiter.wait(for: [expectation], timeout: try remainingTime(30)) == .completed else {
                throw block("Actual Celluloid editor did not become ready")
            }
            if let contradiction { throw block(contradiction) }
        }
        // The post-process observation must already be ready; no recovery wait
        // can turn a disappeared/loading editor into a successful bracket.
        let observed = observations()
        guard ready(observed) else {
            throw block("Actual Celluloid editor is missing, ambiguous, still loading, read-only or not ready")
        }
        var record = try hostObservation(expectedPID: expectedPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        record.merge(observed) { _, new in new }
        return record
    }
    @MainActor private func checkpoint(_ app: XCUIApplication, _ name: String, screenshot: Bool = false) throws {
        try text(app.debugDescription, named: name + ".txt")
        print("MAC_HOST_STAGE " + stage + " snapshot=" + name)
        if screenshot {
            let data = app.screenshot().pngRepresentation
            let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
            let thumb = try XCTUnwrap(CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1280
            ] as CFDictionary))
            let bytes = NSMutableData()
            let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, UTType.jpeg.identifier as CFString, 1, nil))
            CGImageDestinationAddImage(destination, thumb, [kCGImageDestinationLossyCompressionQuality: 0.62] as CFDictionary)
            XCTAssertTrue(CGImageDestinationFinalize(destination)); XCTAssertLessThan(bytes.length, 700_000)
            // Only two fixed still names are used throughout this phase.
            try diagnostic(bytes as Data, named: name == "extensions" ? "extensions.jpg" : "last-observed.jpg", type: "public.jpeg")
        }
    }
    private func makeFixture() throws -> URL {
        let width = 1200, height = 800
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
            bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        for (rect, color) in [(CGRect(x: 0, y: 0, width: 810, height: 530), NSColor.red),
                              (CGRect(x: 810, y: 0, width: 390, height: 530), NSColor.green),
                              (CGRect(x: 0, y: 530, width: 810, height: 270), NSColor.blue),
                              (CGRect(x: 810, y: 530, width: 390, height: 270), NSColor.yellow)] {
            bitmap.setFillColor(color.cgColor); bitmap.fill(rect)
        }
        let image = try XCTUnwrap(bitmap.makeImage())
        let dir = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath().appendingPathComponent("CelluloidPhotosHost-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: false)
        let file = dir.appendingPathComponent(Self.fixtureFilename)
        let destination = try XCTUnwrap(CGImageDestinationCreateWithURL(file as CFURL, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil); XCTAssertTrue(CGImageDestinationFinalize(destination))
        // Preserve exact fixture bytes and decoded pixels BEFORE import or any edit.
        retainedFixtureURL = file
        let source = try lifecycleRaster(readBoundedOwnedFile(file), expectedFormat: UTType.png.identifier)
        retainedSource = source
        try retainLifecycleImage(source, named: "lifecycle-source.png")
        try lifecyclePhase("source-retained", details: ["fixture_filename": Self.fixtureFilename,
            "fixture_sha256": digest(source.bytes), "retained_before_import": true])
        try report(["source_sha": try value("source_sha"), "synthetic_filename": file.lastPathComponent, "sha256": digest(source.bytes),
                    "width": width, "height": height, "purpose": "owned filter lifecycle fixture"], named: "fixture.json")
        return file
    }
    @MainActor private func selfIdentityObservation(in photos: XCUIApplication, allowWait: Bool) throws -> (raw: String, count: Int) {
        // Read only the public AX leaf of the already-ready, uniquely observed
        // editor. No subprocess, cross-process enumeration or expected-value input.
        var observed: (raw: String, count: Int)?
        var contradiction: String?
        func sample() -> Bool {
            let editors = editorMatches(in: photos)
            let editorCount = editors.count
            guard editorCount == 1 else { contradiction = "Ready editor disappeared or became ambiguous during self-observation"; return true }
            let identities = editors.element(boundBy: 0).descendants(matching: .any).matching(identifier: "photos-extension.self-identity")
            let identityCount = identities.count
            guard identityCount <= 1 else { contradiction = "Duplicate self-identity AX leaf"; return true }
            guard identityCount == 1 else { return false }
            let leaf = identities.element(boundBy: 0)
            guard leaf.label == "CELLULOID_EXTENSION_SELF_IDENTITY_V1", let raw = leaf.value as? String,
                  !raw.isEmpty, raw.utf8.count <= 8_192,
                  let data = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data), object is [String: Any] else {
                contradiction = "Malformed or oversized self-identity AX value"; return true
            }
            observed = (raw, identityCount); return true
        }
        if allowWait {
            let expectation = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in sample() }, object: nil)
            guard XCTWaiter.wait(for: [expectation], timeout: try remainingTime(10)) == .completed else { throw block("Missing extension self-identity") }
        } else { _ = sample() }
        if let contradiction { throw block(contradiction) }
        guard let observed else { throw block("Missing extension self-identity after first observation") }
        return observed
    }
    // MARK: - Bounded stored-raster lifecycle (independent of the native oracle)

    @MainActor private func deadlineClick(_ element: XCUIElement, twice: Bool = false) throws {
        _ = try remainingTime(1)
        if twice { element.doubleClick() } else { element.click() }
    }
    @MainActor private func deadlineKey(_ element: XCUIElement, _ key: String, modifierFlags: XCUIElement.KeyModifierFlags) throws {
        _ = try remainingTime(1)
        element.typeKey(key, modifierFlags: modifierFlags)
    }
    @MainActor private func deadlineKey(_ element: XCUIElement, _ key: XCUIKeyboardKey, modifierFlags: XCUIElement.KeyModifierFlags) throws {
        _ = try remainingTime(1)
        element.typeKey(key, modifierFlags: modifierFlags)
    }
    @MainActor private func deadlineText(_ element: XCUIElement, _ text: String) throws {
        _ = try remainingTime(1)
        element.typeText(text)
    }
    private func remainingTime(_ requested: TimeInterval) throws -> TimeInterval {
        let remaining = TimeInterval(lifecycleDeadlineSeconds) - (ProcessInfo.processInfo.systemUptime - testStarted)
        guard testStarted > 0, remaining > 0 else { throw block("Source-bound Photos lifecycle deadline exhausted") }
        return min(requested, remaining)
    }
    private func lifecyclePhase(_ name: String, details: [String: Any]) throws {
        _ = try remainingTime(1)
        guard lifecycleRows.count < Self.lifecyclePhases.count,
              Self.lifecyclePhases[lifecycleRows.count] == name else { throw block("Out-of-order lifecycle phase") }
        lifecycleRows.append(["index": lifecycleRows.count, "name": name,
            "elapsed_ms": Int((ProcessInfo.processInfo.systemUptime - testStarted) * 1000),
            "controls": lifecycleControls, "details": details])
        lifecycleControls.removeAll()
    }
    private func lifecycleReceipt(photosPID: pid_t) throws -> [String: Any] {
        return ["schema": Self.lifecycleContract, "host_entry_contract": Self.hostEntryContract,
            "source_sha": try value("source_sha"), "context_sha256": contextHash,
            "test_source_sha256": try value("test_source_sha256"), "verifier_sha256": try value("script_sha256"),
            "photos_pid": photosPID, "fixture_sha256": retainedSource.map { digest($0.bytes) } ?? "",
            "asset_label": lifecycleAssetLabel, "single_photo_topologies": singlePhotoTopologies,
            "complete": lifecycleComplete, "dirty_cancel_tested": false,
            "deadline_seconds": lifecycleDeadlineSeconds, "control_columns": ["scope", "role", "identifier", "title", "label", "value", "count", "enabled", "hittable"],
            "control_catalog": lifecycleControlCatalog, "phases": lifecycleRows, "images": lifecycleImages, "raw_exports": lifecycleExports,
            "export_option_bindings": exportOptionBindings,
            "binary_states": exportBinaryStates, "binary_scalar_self_tested": binaryScalarSelfTested,
            "srgb_icc_reference": lifecycleICC.map { $0 as Any } ?? NSNull()]
    }
    @MainActor private func lifecycleGuard(_ photos: XCUIApplication, photosPID: pid_t,
        fixtureHash: String, assetLabel: String, normal: Bool = false) throws {
        _ = try remainingTime(1)
        _ = try hostObservation(expectedPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        for (path, hash) in [("app_executable", "app_executable_sha256"), ("extension_executable", "extension_executable_sha256"),
                             ("extension_debug_dylib", "extension_debug_dylib_sha256"), ("test_source_path", "test_source_sha256"),
                             ("script_path", "script_sha256")] {
            guard try digest(URL(fileURLWithPath: value(path))) == value(hash) else { throw block("Lifecycle source/product changed: " + path) }
        }
        guard let retainedSource, let retainedFixtureURL,
              digest(try readBoundedOwnedFile(retainedFixtureURL)) == digest(retainedSource.bytes),
              digest(retainedSource.bytes) == fixtureHash else { throw block("Owned lifecycle fixture changed") }
        try rejectLifecycleAlert(photos)
        if normal { try soleAsset(in: photos, assetLabel: assetLabel) }
    }
    @MainActor private func rejectLifecycleAlert(_ photos: XCUIApplication) throws {
        let alertCount = photos.alerts.count
        guard alertCount == 0 else {
            throw block("Unadmitted Photos confirmation or access alert; no action taken",
                operation: ["alert_count": alertCount, "observed_ax": String(photos.debugDescription.prefix(3000))])
        }
    }
    @MainActor private func soleAsset(in photos: XCUIApplication, assetLabel: String) throws {
        // Photos may remove its background collection after Done while retaining
        // the same single-photo canvas. Both require the exact owned image label.
        // Recorded topology is UI shape, not a persistent PHAsset identifier.
        // Sample each count once; an observed contradiction cannot be resampled away.
        let windows = photos.windows.matching(identifier: "MainWindow")
        let windowCount = windows.count
        let alertCount = photos.alerts.count
        let sheetCount = photos.sheets.count
        let dialogCount = photos.dialogs.count
        let editorCount = editorMatches(in: photos).count
        let identityCount = photos.descendants(matching: .any).matching(identifier: "photos-extension.self-identity").count
        var observed: [String: Any] = ["window_count": windowCount, "alert_count": alertCount,
            "sheet_count": sheetCount, "dialog_count": dialogCount, "editor_count": editorCount,
            "identity_count": identityCount]
        guard windowCount == 1, alertCount == 0, sheetCount == 0, dialogCount == 0,
              editorCount == 0, identityCount == 0, !assetLabel.isEmpty else {
            throw block("Owned single-photo parent or dismissal state changed", operation: observed)
        }
        let window = windows.element(boundBy: 0)
        let toolbars = window.toolbars
        let toolbarCount = toolbars.count
        let collections = window.collectionViews.matching(identifier: "photos_collection_view")
        let collectionCount = collections.count
        let canvases = window.descendants(matching: .group).matching(identifier: "IPXCanvasItemView")
        let canvasCount = canvases.count
        observed["toolbar_count"] = toolbarCount; observed["collection_count"] = collectionCount
        observed["canvas_count"] = canvasCount
        guard toolbarCount == 1, canvasCount == 1, collectionCount == 0 || collectionCount == 1 else {
            throw block("Owned single-photo topology changed", operation: observed)
        }
        let toolbar = toolbars.element(boundBy: 0)
        let images = canvases.element(boundBy: 0).images
        let imageCount = images.count
        let imageLabel = imageCount == 1 ? images.element(boundBy: 0).label : ""
        let counters = toolbar.staticTexts.matching(identifier: "_NS:10")
        let counterCount = counters.count
        let counterValue = counterCount == 1 ? (counters.element(boundBy: 0).value as? String) ?? "" : ""
        let edits = toolbar.children(matching: .button).matching(identifier: "IPXToolbarItemIDToggleEdit")
        let editCount = edits.count
        let editLabel = editCount == 1 ? edits.element(boundBy: 0).label : ""
        let editEnabled = editCount == 1 && edits.element(boundBy: 0).isEnabled
        let editHittable = editCount == 1 && edits.element(boundBy: 0).isHittable
        let doneCount = toolbar.children(matching: .button).matching(identifier: "IPXToolbarItemIDToggleDoneEdit").count
        observed["image_count"] = imageCount; observed["image_label"] = String(imageLabel.prefix(256))
        observed["counter_count"] = counterCount; observed["counter_value"] = String(counterValue.prefix(256))
        observed["edit_count"] = editCount; observed["edit_label"] = String(editLabel.prefix(256))
        observed["edit_enabled"] = editEnabled; observed["edit_hittable"] = editHittable; observed["done_count"] = doneCount
        guard imageCount == 1, imageLabel == assetLabel, counterCount == 1, counterValue == "1 of 1",
              editCount == 1, editLabel == "Edit", editEnabled, editHittable, doneCount == 0 else {
            throw block("Owned single-photo image or normal controls changed", operation: observed)
        }
        if collectionCount == 1 {
            let assets = collections.element(boundBy: 0).descendants(matching: .any).matching(identifier: "mediaKind_asset")
            let assetCount = assets.count
            let observedAssetLabel = assetCount == 1 ? assets.element(boundBy: 0).label : ""
            observed["asset_count"] = assetCount; observed["asset_label"] = String(observedAssetLabel.prefix(256))
            guard assetCount == 1, observedAssetLabel == assetLabel else {
                throw block("Owned collection asset changed", operation: observed)
            }
        }
        let topology = collectionCount == 1 ? "collection-present" : "collection-absent"
        if !singlePhotoTopologies.contains(topology) {
            guard singlePhotoTopologies.count < 2 else { throw block("Excessive single-photo topologies") }
            singlePhotoTopologies.append(topology)
        }
    }
    @MainActor private func lifecycleControl(_ query: XCUIElementQuery, scope: String, role: String,
        click: Bool = true) throws -> XCUIElement {
        _ = try remainingTime(1)
        let count = query.count
        guard count == 1 else { throw block("Missing/ambiguous lifecycle control", operation: ["scope": scope, "role": role, "count": count]) }
        let element = query.element(boundBy: 0)
        let enabled = element.isEnabled, hittable = element.isHittable
        guard enabled, hittable else { throw block("Lifecycle control disabled/not hittable", operation: ["scope": scope,
            "role": role, "identifier": element.identifier, "label": element.label, "enabled": enabled, "hittable": hittable]) }
        let row: [Any] = [scope, role, element.identifier, element.title, element.label,
            (element.value as? String) ?? "", count, enabled, hittable]
        _ = try retainLifecycleControl(row)
        if click { try deadlineClick(element) }
        return element
    }
    private func retainLifecycleControl(_ row: [Any]) throws -> Int {
        _ = try remainingTime(1)
        guard row.prefix(6).allSatisfy({ (($0 as? String)?.utf8.count ?? 1025) <= 1024 }), lifecycleControlCatalog.count < 100 else {
            throw block("Oversized lifecycle control observation")
        }
        let encoded = try JSONSerialization.data(withJSONObject: row)
        let found = try lifecycleControlCatalog.firstIndex { try JSONSerialization.data(withJSONObject: $0) == encoded }
        let index = found ?? lifecycleControlCatalog.count
        if found == nil { lifecycleControlCatalog.append(row) }
        lifecycleControls.append(index)
        guard lifecycleControls.count <= 40 else { throw block("Excessive lifecycle controls in one phase") }
        return index
    }
    @MainActor private func toolbarAction(_ title: String, id: String, role: XCUIElement.ElementType,
        in photos: XCUIApplication) throws {
        try rejectLifecycleAlert(photos)
        let windows = photos.windows.matching(identifier: "MainWindow")
        guard windows.count == 1, windows.element(boundBy: 0).toolbars.count == 1 else { throw block("Unknown Photos toolbar parent") }
        _ = try lifecycleControl(windows.element(boundBy: 0).toolbars.element(boundBy: 0).children(matching: role)
            .matching(NSPredicate(format: "identifier == %@ AND label == %@", id, title)),
            scope: "MainWindow/Toolbar", role: role == .checkBox ? "CheckBox" : "Button")
    }
    @MainActor private func lifecycleWait(_ photos: XCUIApplication, seconds: TimeInterval = 30,
        description: String, condition: @escaping () -> Bool) throws {
        var alert: String?
        let predicate = NSPredicate { _, _ in
            if photos.alerts.count > 0 { alert = String(photos.debugDescription.prefix(3000)); return true }
            return condition()
        }
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)],
                            timeout: try remainingTime(seconds)) == .completed else { throw block(description) }
        if let alert { throw block("Unknown Photos alert; no confirmation taken", operation: ["observed_ax": alert]) }
        _ = try remainingTime(1)
    }
    @MainActor private func requireNoSheet(_ photos: XCUIApplication) throws {
        try rejectLifecycleAlert(photos)
        guard photos.sheets.count == 0, photos.dialogs.count == 0 else {
            throw block("Unadmitted Photos sheet/dialog; no confirmation taken", operation: ["observed_ax": String(photos.debugDescription.prefix(3000))])
        }
    }
    @MainActor private func closeExtension(in photos: XCUIApplication, save: Bool) throws {
        try toolbarAction(save ? "Save Changes" : "Cancel", id: save ? "a_saveChangesPressed:" : "a_cancelPressed:", role: .checkBox, in: photos)
        try lifecycleWait(photos, description: "Extension did not dismiss") {
            self.editorMatches(in: photos).count == 0 && photos.descendants(matching: .any).matching(identifier: "photos-extension.self-identity").count == 0
        }
        try requireNoSheet(photos)
        try toolbarAction("Done", id: "IPXToolbarItemIDToggleDoneEdit", role: .button, in: photos)
        try lifecycleWait(photos, description: "Photos did not return to single-photo view") {
            photos.buttons.matching(identifier: "IPXToolbarItemIDToggleEdit").count == 1
                && photos.buttons.matching(identifier: "IPXToolbarItemIDToggleDoneEdit").count == 0
        }
        try requireNoSheet(photos)
    }
    @MainActor private func filterValue(in photos: XCUIApplication) throws -> String {
        let editors = editorMatches(in: photos)
        guard editors.count == 1 else { throw block("Missing/ambiguous ready editor") }
        let filters = editors.element(boundBy: 0).popUpButtons.matching(NSPredicate(format: "identifier == %@ AND label == %@", "photos-extension.filter", "Filter"))
        guard filters.count == 1, filters.element(boundBy: 0).isEnabled,
              let value = filters.element(boundBy: 0).value as? String else { throw block("Invalid actual filter picker") }
        return value
    }
    @MainActor private func selectFade(in photos: XCUIApplication, photosPID: pid_t, fixtureHash: String, assetLabel: String) throws {
        guard try filterValue(in: photos) == "Original" else { throw block("Initial owned fixture is not Original") }
        let editor = editorMatches(in: photos).element(boundBy: 0)
        let picker = try lifecycleControl(editor.popUpButtons.matching(NSPredicate(format: "identifier == %@ AND label == %@", "photos-extension.filter", "Filter")),
            scope: "Celluloid photo editor", role: "PopUpButton")
        let menus = picker.children(matching: .menu)
        guard menus.count == 1 else { throw block("Unknown filter picker menu parent") }
        _ = try lifecycleControl(menus.element(boundBy: 0).children(matching: .menuItem).matching(NSPredicate(format: "title == %@", "Fade")),
            scope: "photos-extension.filter/Menu", role: "MenuItem")
        _ = try readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, phase: "before-process")
        guard try filterValue(in: photos) == "Fade" else { throw block("Fade was not observed after rendering") }
    }
    private func validatedIdentity(_ raw: String, photosPID: pid_t) throws -> [String: Any] {
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any])
        let keys: Set<String> = ["schema", "marker", "observation_kind", "bundle_identifier", "pid", "bundle_path", "executable_path",
            "executable_sha256", "debug_dylib_path", "debug_dylib_sha256", "generation", "content_editing_started"]
        guard Set(value.keys) == keys, value["schema"] as? String == "Celluloid.ExtensionSelfIdentity.1",
              value["marker"] as? String == "CELLULOID_EXTENSION_SELF_IDENTITY_V1", value["observation_kind"] as? String == "extension-self",
              value["bundle_identifier"] as? String == (try self.value("extension_id")), value["content_editing_started"] as? Bool == true,
              let pid = value["pid"] as? Int, pid > 0, pid < Int(Int32.max), pid != Int(photosPID),
              let generation = value["generation"] as? String, UUID(uuidString: generation) != nil,
              generation.replacingOccurrences(of: "-", with: "") != String(repeating: "0", count: 32) else { throw block("Unbound lifecycle extension identity") }
        for (observed, expected) in [("bundle_path", "extension_path"), ("executable_path", "extension_executable"),
            ("debug_dylib_path", "extension_debug_dylib"), ("executable_sha256", "extension_executable_sha256"),
            ("debug_dylib_sha256", "extension_debug_dylib_sha256")] {
            guard value[observed] as? String == (try self.value(expected)) else { throw block("Changed lifecycle self-identity: " + observed) }
        }
        return value
    }
    @MainActor private func reenter(in photos: XCUIApplication, photosPID: pid_t, fixtureHash: String,
        assetLabel: String, filter: String, previousGenerations: Set<String>) throws -> (generation: String, details: [String: Any]) {
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        try toolbarAction("Edit", id: "IPXToolbarItemIDToggleEdit", role: .button, in: photos)
        try requireNoSheet(photos)
        _ = try lifecycleControl(photos.windows["MainWindow"].toolbars.descendants(matching: .menuButton)
            .matching(NSPredicate(format: "label == %@", "Extensions")), scope: "MainWindow/Toolbar", role: "MenuButton")
        let items = try openedExtensionItems(in: photos)
        guard editorMatches(in: photos).count == 0,
              photos.descendants(matching: .any).matching(identifier: "photos-extension.self-identity").count == 0 else { throw block("Stale editor before lifecycle reentry") }
        _ = try lifecycleControl(items, scope: "Extensions/Menu", role: "MenuItem")
        _ = try readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, phase: "before-process")
        let first = try selfIdentityObservation(in: photos, allowWait: true)
        let second = try selfIdentityObservation(in: photos, allowWait: false)
        guard first.raw == second.raw else { throw block("Reentry identity changed between observations") }
        let identity = try validatedIdentity(first.raw, photosPID: photosPID)
        let generation = try XCTUnwrap(identity["generation"] as? String)
        guard !previousGenerations.contains(generation), try filterValue(in: photos) == filter else { throw block("Stale generation or wrong restored filter") }
        _ = try readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, phase: "after-process")
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        return (generation, ["filter": filter, "editor_count_before": 0, "editor_count_after": 1,
            "identity_element_counts": [first.count, second.count], "observations": [first, second].map { item in
                ["raw": item.raw, "bytes": item.raw.utf8.count, "sha256": digest(Data(item.raw.utf8))] as [String: Any]
            }])
    }
    @MainActor private func runFilterLifecycle(in photos: XCUIApplication, photosPID: pid_t, fixtureHash: String,
        assetLabel: String, baselineIdentity: String) throws {
        guard let source = retainedSource else { throw block("Lifecycle needs newly manufactured source bytes; seeded reuse cannot qualify") }
        lifecycleAssetLabel = assetLabel
        let baseline = try validatedIdentity(baselineIdentity, photosPID: photosPID)
        let initialGeneration = try XCTUnwrap(baseline["generation"] as? String)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        let reference = try expectedFade(source)
        guard try maximumDelta(reference.raster.rgba, source.rgba) > 2 else { throw block("Independent Fade reference failed to change the fixture") }
        try retainLifecycleImage(reference.raster, named: "lifecycle-expected-save.png")
        stage = "lifecycle-select-fade"
        try selectFade(in: photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        try lifecyclePhase("fade-ready", details: ["filter": "Fade", "independent_filter": "CIPhotoEffectInstant",
            "jpeg_quality": 0.95, "jpeg_sha256": reference.jpegSHA256])
        stage = "lifecycle-save-and-export"
        let beforeSaveIdentity = try selfIdentityObservation(in: photos, allowWait: false)
        guard beforeSaveIdentity.raw == baselineIdentity else { throw block("Initial editing identity changed before Save Changes") }
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        try closeExtension(in: photos, save: true)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        let saved = try exportRaster("saved", in: photos, original: false)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        let savedDelta = try maximumDelta(saved.rgba, reference.raster.rgba)
        try retainLifecycleImage(saved, named: "lifecycle-saved.png")
        guard savedDelta <= 2 else { throw block("Stored saved raster disagrees with independent JPEG-aware reference", operation: ["max_channel_delta": savedDelta]) }
        try lifecyclePhase("saved-export", details: ["max_channel_delta": savedDelta, "limit": 2, "sole_asset_count": 1])
        stage = "lifecycle-reopen-fade"
        let reopened = try reenter(in: photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel,
            filter: "Fade", previousGenerations: [initialGeneration])
        try lifecyclePhase("reopened-fade", details: reopened.details)
        // No picker/layer action is allowed between this bracket and Cancel.
        stage = "lifecycle-cancel-without-new-edit"
        let beforeCancelIdentity = try selfIdentityObservation(in: photos, allowWait: false)
        guard try validatedIdentity(beforeCancelIdentity.raw, photosPID: photosPID)["generation"] as? String == reopened.generation,
              try filterValue(in: photos) == "Fade" else { throw block("Reopened editing identity/filter changed before Cancel") }
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel)
        try closeExtension(in: photos, save: false)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        let cancelled = try exportRaster("cancelled", in: photos, original: false)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        try retainLifecycleImage(cancelled, named: "lifecycle-cancelled.png")
        guard cancelled.rgba == saved.rgba else { throw block("Nonmutating Cancel changed stored pixels") }
        try lifecyclePhase("cancelled-export", details: ["rgba_equal_saved": true, "new_edit_made": false, "sole_asset_count": 1])
        stage = "lifecycle-revert-owned-asset"
        try openTopMenu("Image", in: photos)
        let imageMenu = try uniqueOpenMenu(photos.menuBarItems.matching(NSPredicate(format: "title == %@", "Image")), description: "Image")
        _ = try lifecycleControl(imageMenu.children(matching: .menuItem).matching(NSPredicate(format: "identifier == %@ AND title == %@", "_NS:766", "Revert to Original")),
            scope: "Image/Menu", role: "MenuItem")
        // No Revert confirmation has been admitted. Any new alert/sheet is a stop.
        try requireNoSheet(photos)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        let reverted = try exportRaster("reverted", in: photos, original: false)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        try retainLifecycleImage(reverted, named: "lifecycle-reverted.png")
        guard reverted.rgba == source.rgba else { throw block("Revert did not restore original pixels") }
        try lifecyclePhase("reverted-export", details: ["rgba_equal_source": true, "sole_asset_count": 1])
        stage = "lifecycle-export-unmodified-original"
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        let original = try exportRaster("original", in: photos, original: true)
        try lifecycleGuard(photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel, normal: true)
        guard original.bytes == source.bytes else { throw block("Unmodified original export differs from retained source bytes") }
        try lifecyclePhase("unmodified-original", details: ["bytes_equal_source": true, "sha256_equal_source": true, "sole_asset_count": 1])
        stage = "lifecycle-reopen-original"
        let final = try reenter(in: photos, photosPID: photosPID, fixtureHash: fixtureHash, assetLabel: assetLabel,
            filter: "Original", previousGenerations: [initialGeneration, reopened.generation])
        try lifecyclePhase("reopened-original", details: final.details)
        try verifyOwnedExportTree()
        let usedControls = Set(lifecycleRows.flatMap { $0["controls"] as? [Int] ?? [] })
        guard usedControls == Set(lifecycleControlCatalog.indices), lifecycleControls.isEmpty,
              lifecycleImages.count == 5, lifecycleExports.count == 4, lifecycleRows.count == 8,
              try JSONSerialization.data(withJSONObject: lifecycleReceipt(photosPID: photosPID), options: [.sortedKeys]).count <= 16_000 else {
            throw block("Incomplete/oversized mandatory lifecycle proof")
        }
        _ = try remainingTime(1)
        lifecycleComplete = true
        stage = "photos-filter-lifecycle-passed"
        print("MAC_HOST_FILTER_LIFECYCLE_PASSED owned static sRGB Fade Save, reopen, nonmutating Cancel, Revert and mandatory Original reentry; dirty Cancel untested")
    }

    @MainActor private func openTopMenu(_ title: String, in photos: XCUIApplication) throws {
        try requireNoSheet(photos)
        guard photos.menuBars.count == 1 else { throw block("Unknown Photos menu-bar parent") }
        _ = try lifecycleControl(photos.menuBars.element(boundBy: 0).children(matching: .menuBarItem)
            .matching(NSPredicate(format: "title == %@", title)), scope: "Photos/MenuBar", role: "MenuBarItem")
    }
    @MainActor private func uniqueOpenMenu(_ parents: XCUIElementQuery, description: String) throws -> XCUIElement {
        guard parents.count == 1 else { throw block("Unknown menu parent: " + description) }
        let menus = parents.element(boundBy: 0).children(matching: .menu)
        guard menus.count == 1, menus.element(boundBy: 0).exists, !menus.element(boundBy: 0).frame.isEmpty else {
            throw block("Missing/ambiguous visible child menu: " + description)
        }
        return menus.element(boundBy: 0)
    }
    @MainActor private func publicLabel(_ title: String, role: XCUIElement.ElementType, in parent: XCUIElement) -> XCUIElementQuery {
        // Public visible labels may be exposed with a trailing form-label colon.
        // No private/guessed identifier or coordinate is accepted for export UI.
        parent.descendants(matching: role).matching(NSPredicate(format: "label IN %@ OR title IN %@", [title, title + ":"], [title, title + ":"]))
    }
    @MainActor private func exportSheet(in photos: XCUIApplication) throws -> XCUIElement {
        try rejectLifecycleAlert(photos)
        let sheets = photos.windows["MainWindow"].sheets
        guard sheets.count == 1, photos.sheets.count == 1, photos.dialogs.count == 0 else {
            throw block("Unknown export sheet parent", operation: ["observed_ax": String(photos.debugDescription.prefix(3000))])
        }
        return sheets.element(boundBy: 0)
    }
    // XCUIElement.value is Any?. Normalize only the admitted binary domain,
    // never debugDescription, general popup text, or a missing-value default.
    private static func binaryScalar(_ raw: Any?) -> BinaryScalar? {
        guard let raw else { return nil }
        let runtimeType = String(reflecting: Swift.type(of: raw))
        guard !runtimeType.isEmpty, runtimeType.utf8.count <= 96 else { return nil }
        if let text = raw as? String {
            guard text == "0" || text == "1" else { return nil }
            return BinaryScalar(kind: "string", runtimeType: runtimeType, encoding: "", raw: text, state: text == "1" ? 1 : 0)
        }
        guard let number = raw as? NSNumber else { return nil }
        let encoding = String(cString: number.objCType)
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            guard ["c", "B"].contains(encoding) else { return nil }
            return BinaryScalar(kind: "boolean", runtimeType: runtimeType, encoding: encoding, raw: number.boolValue, state: number.boolValue ? 1 : 0)
        }
        guard ["c", "C", "s", "S", "i", "I", "l", "L", "q", "Q", "f", "d"].contains(encoding),
              number.doubleValue.isFinite else { return nil }
        let state: Int
        if number.compare(NSNumber(value: 0)) == .orderedSame, number.decimalValue == Decimal(0) { state = 0 }
        else if number.compare(NSNumber(value: 1)) == .orderedSame, number.decimalValue == Decimal(1) { state = 1 }
        else { return nil }
        return BinaryScalar(kind: "number", runtimeType: runtimeType, encoding: encoding, raw: number, state: state)
    }
    private func verifyBinaryScalarContract() throws {
        let valid: [(Any, String, Int)] = [("0", "string", 0), ("1", "string", 1), (NSString(string: "0"), "string", 0),
            (false, "boolean", 0), (true, "boolean", 1), (NSNumber(value: false), "boolean", 0), (NSNumber(value: true), "boolean", 1),
            (0, "number", 0), (1, "number", 1), (NSNumber(value: Int64(0)), "number", 0), (NSNumber(value: UInt64(1)), "number", 1),
            (0.0, "number", 0), (NSNumber(value: Float(1)), "number", 1), (NSDecimalNumber(string: "1"), "number", 1)]
        for (raw, kind, state) in valid {
            guard let scalar = Self.binaryScalar(raw), scalar.kind == kind, scalar.state == state else {
                throw block("Binary scalar Foundation positive self-test failed", operation: ["value_type": String(reflecting: Swift.type(of: raw)), "expected_kind": kind, "expected_state": state])
            }
        }
        let invalid: [Any?] = [nil, NSNull(), "", " 0", "01", "+1", "1.0", "true", "false", "mixed", "2", -1, 2, 0.5,
            NSNumber(value: Double.nan), NSNumber(value: Double.infinity), NSNumber(value: -Double.infinity), NSNumber(value: UInt64.max),
            NSDecimalNumber(string: "1.00000000000000000001"), NSDecimalNumber.notANumber, [0], ["state": 1], Data([0])]
        for raw in invalid {
            if let scalar = Self.binaryScalar(raw) {
                throw block("Binary scalar Foundation negative self-test failed", operation: ["value_type": scalar.runtimeType, "kind": scalar.kind, "state": scalar.state])
            }
        }
        binaryScalarSelfTested = true
    }
    @MainActor private func observeExportBinary(_ query: XCUIElementQuery, role: String) throws -> (element: XCUIElement, row: [Any], scalar: BinaryScalar) {
        _ = try remainingTime(1)
        let count = query.count
        guard count == 1 else { throw block("Missing/ambiguous export binary control", operation: ["role": role, "count": count]) }
        let element = query.element(boundBy: 0)
        let identifier = element.identifier, title = element.title, label = element.label
        let disclosure = role == "DisclosureTriangle" && element.elementType == .disclosureTriangle
            && identifier == "button_disclosure" && label == "customize"
        let xmpLabels = [title, label].filter { !$0.isEmpty }
        let sidecar = role == "CheckBox" && element.elementType == .checkBox && !xmpLabels.isEmpty
            && xmpLabels.allSatisfy({ ["Export IPTC as XMP", "Export IPTC as XMP:"].contains($0) })
        guard disclosure || sidecar else { throw block("Unadmitted export binary target") }
        let enabled = element.isEnabled, hittable = element.isHittable
        guard enabled, hittable else { throw block("Export binary control disabled/not hittable") }
        let raw = element.value
        guard let scalar = Self.binaryScalar(raw) else {
            throw block("Unsupported export binary value", operation: ["role": role, "identifier": identifier,
                "value_type": String((raw.map { String(reflecting: Swift.type(of: $0)) } ?? "nil").prefix(96))])
        }
        return (element, ["ExportOptions", role, identifier, title, label, String(scalar.state), count, enabled, hittable], scalar)
    }
    private func retainExportBinary(_ observation: (element: XCUIElement, row: [Any], scalar: BinaryScalar)) throws {
        let index = try retainLifecycleControl(observation.row), scalar = observation.scalar
        let row: [Any] = [index, scalar.kind, scalar.runtimeType, scalar.encoding, scalar.raw, scalar.state]
        let encoded = try JSONSerialization.data(withJSONObject: row)
        guard encoded.count <= 256 else { throw block("Oversized export binary observation") }
        if try exportBinaryStates.contains(where: { try JSONSerialization.data(withJSONObject: $0) == encoded }) { return }
        let prospective = exportBinaryStates + [row]
        var receipt = try lifecycleReceipt(photosPID: lifecyclePhotosPID)
        receipt["binary_states"] = prospective
        guard prospective.count <= 12, try JSONSerialization.data(withJSONObject: receipt).count <= 16_000 else {
            throw block("Export binary observation would exceed lifecycle proof budget")
        }
        exportBinaryStates = prospective
    }
    @MainActor private func setExportBinary(_ query: XCUIElementQuery, role: String, desired: Int, photos: XCUIApplication) throws {
        guard (role == "DisclosureTriangle" && desired == 1) || (role == "CheckBox" && desired == 0) else { throw block("Unadmitted export binary transition") }
        let initial = try observeExportBinary(query, role: role)
        let identity = try JSONSerialization.data(withJSONObject: Array(initial.row.prefix(5)))
        try retainExportBinary(initial)
        if initial.scalar.state != desired {
            let fresh = try observeExportBinary(query, role: role)
            guard try JSONSerialization.data(withJSONObject: Array(fresh.row.prefix(5))) == identity,
                  fresh.scalar.state == initial.scalar.state else { throw block("Stale export binary identity/state before click") }
            try retainExportBinary(fresh)
            try deadlineClick(fresh.element)
            var observationFailure: Error?
            try lifecycleWait(photos, seconds: 10, description: "Export binary control did not reach requested state") {
                do {
                    let observed = try self.observeExportBinary(query, role: role)
                    guard try JSONSerialization.data(withJSONObject: Array(observed.row.prefix(5))) == identity else { throw self.block("Export binary identity changed while waiting") }
                    return observed.scalar.state == desired
                } catch { observationFailure = error; return true }
            }
            if let observationFailure { throw observationFailure }
        }
        let final = try observeExportBinary(query, role: role)
        guard try JSONSerialization.data(withJSONObject: Array(final.row.prefix(5))) == identity,
              final.scalar.state == desired else { throw block("Export binary final identity/state changed") }
        try retainExportBinary(final)
    }
    private func exportFrame(_ frame: CGRect) throws -> [Double] {
        let values = [frame.minX, frame.minY, frame.width, frame.height].map(Double.init)
        guard values.allSatisfy({ $0.isFinite && abs($0) <= 32768 }), frame.width > 0, frame.height > 0 else {
            throw block("Invalid visible export control frame")
        }
        return values
    }
    @MainActor private func exportPopup(_ title: String, in sheet: XCUIElement) throws -> (query: XCUIElementQuery, identity: String, binding: [Any]) {
        _ = try remainingTime(1)
        guard sheet.exists, sheet.identifier == "sheetWindow_export" else { throw block("Changed export options sheet") }
        let known = ["Photo Kind": "popup_photoKind", "File Name": "popup_useFileName", "Subfolder Format": "popup_subfolderFormat"]
        if let identifier = known[title] {
            let query = sheet.descendants(matching: .popUpButton).matching(identifier: identifier)
            guard query.count == 1 else { throw block("Missing/ambiguous observed export option: " + title) }
            guard query.element(boundBy: 0).isEnabled, query.element(boundBy: 0).isHittable else { throw block("Unusable observed export option: " + title) }
            return (query, identifier, [])
        }
        guard ["Color Profile", "Size"].contains(title) else { throw block("Unadmitted export option discovery") }
        let sheetFrame = sheet.frame
        let sheetRect = try exportFrame(sheetFrame)
        let direct = publicLabel(title, role: .popUpButton, in: sheet)
        let directCount = direct.count
        guard directCount <= 1 else { throw block("Ambiguous directly labelled export option: " + title) }
        if directCount == 1 {
            let control = direct.element(boundBy: 0), frame = direct.element(boundBy: 0).frame
            let texts = [control.label, control.title].filter { !$0.isEmpty }
            guard !texts.isEmpty, texts.allSatisfy({ [title, title + ":"].contains($0) }),
                  sheetFrame.contains(frame), control.isEnabled, control.isHittable else { throw block("Unusable directly labelled export option: " + title) }
            return (direct, control.identifier, ["direct", sheet.identifier, "", "", texts[0], [Double](), try exportFrame(frame), sheetRect, sheetRect])
        }
        // Only these two intended options may use a visible, same-direct-parent
        // label association. Frames identify a row; clicks never use coordinates.
        let labelPredicate = NSPredicate(format: "label IN %@ OR title IN %@ OR value IN %@", [title, title + ":"], [title, title + ":"], [title, title + ":"])
        let labels = sheet.descendants(matching: .staticText).matching(labelPredicate)
        let labelCount = labels.count
        guard labelCount == 1 else { throw block("Missing/ambiguous visible export label: " + title) }
        let label = labels.element(boundBy: 0), labelFrame = labels.element(boundBy: 0).frame
        let texts = [label.label, label.title, (label.value as? String) ?? ""].filter { !$0.isEmpty }
        guard !texts.isEmpty, texts.allSatisfy({ [title, title + ":"].contains($0) }), label.isHittable,
              sheetFrame.contains(labelFrame) else { throw block("Unusable visible export label: " + title) }
        let labelRect = try exportFrame(labelFrame)
        let groups = sheet.descendants(matching: .group)
        let groupCount = groups.count
        guard groupCount > 0, groupCount <= 8 else { throw block("Unbounded export label containers") }
        var parents: [XCUIElement] = []
        for index in 0..<groupCount {
            let group = groups.element(boundBy: index)
            let childCount = group.children(matching: .staticText).matching(labelPredicate).count
            guard childCount <= 1 else { throw block("Duplicate direct export labels") }
            if childCount == 1 { parents.append(group) }
        }
        guard parents.count == 1 else { throw block("Ambiguous direct export label parent") }
        let parent = parents[0], parentFrame = parents[0].frame
        let parentRect = try exportFrame(parentFrame)
        guard sheetFrame.contains(parentFrame), parentFrame.contains(labelFrame) else { throw block("Export label escaped its visible parent") }
        let popups = parent.children(matching: .popUpButton)
        let popupCount = popups.count
        guard popupCount > 0, popupCount <= 6 else { throw block("Unbounded associated export popups") }
        var aligned: [(control: XCUIElement, frame: CGRect)] = []
        for index in 0..<popupCount {
            let candidate = popups.element(boundBy: index), frame = popups.element(boundBy: index).frame
            _ = try exportFrame(frame)
            if parentFrame.contains(frame), frame.minX >= labelFrame.maxX,
               frame.minX - labelFrame.maxX <= 24, abs(frame.midY - labelFrame.midY) <= 6 {
                aligned.append((candidate, frame))
            }
        }
        // Count every aligned candidate before inspecting usability. A disabled
        // duplicate remains a contradiction rather than disappearing from selection.
        guard aligned.count == 1 else { throw block("Missing/ambiguous aligned export popup") }
        let control = aligned[0].control, controlFrame = aligned[0].frame
        let identifier = control.identifier
        guard !identifier.isEmpty, control.isEnabled, control.isHittable,
              [control.label, control.title].allSatisfy({ $0.isEmpty || [title, title + ":"].contains($0) }) else {
            throw block("Unusable or contradictory associated export popup")
        }
        let query = popups.matching(identifier: identifier)
        guard query.count == 1 else { throw block("Ambiguous observed export popup identity") }
        return (query, identifier, ["label-row", sheet.identifier, parent.identifier, label.identifier, texts[0],
            labelRect, try exportFrame(controlFrame), parentRect, sheetRect])
    }
    private func exportBindingSignature(_ observation: (query: XCUIElementQuery, identity: String, binding: [Any])) throws -> Data {
        try JSONSerialization.data(withJSONObject: [observation.identity, observation.binding])
    }
    private func retainExportBinding(_ binding: [Any], controlIndex: Int) throws {
        guard !binding.isEmpty else { return }
        let row: [Any] = [controlIndex] + binding
        let encoded = try JSONSerialization.data(withJSONObject: row)
        guard encoded.count <= 768 else { throw block("Oversized export option binding") }
        if try exportOptionBindings.contains(where: { try JSONSerialization.data(withJSONObject: $0) == encoded }) { return }
        let prospective = exportOptionBindings + [row]
        var receipt = try lifecycleReceipt(photosPID: lifecyclePhotosPID)
        receipt["export_option_bindings"] = prospective
        guard prospective.count <= 6, try JSONSerialization.data(withJSONObject: receipt).count <= 16_000 else {
            throw block("Export option binding would exceed lifecycle proof budget")
        }
        exportOptionBindings = prospective
    }
    @MainActor private func popup(_ title: String, choose value: String, in sheet: XCUIElement) throws -> Data {
        let observation = try exportPopup(title, in: sheet)
        let signature = try exportBindingSignature(observation)
        let control = try lifecycleControl(observation.query, scope: "ExportOptions/" + title, role: "PopUpButton", click: false)
        guard control.identifier == observation.identity else { throw block("Export option identity changed before action") }
        try retainExportBinding(observation.binding, controlIndex: try XCTUnwrap(lifecycleControls.last))
        if control.value as? String != value {
            let fresh = try exportPopup(title, in: sheet)
            guard try exportBindingSignature(fresh) == signature else { throw block("Stale export option binding before action") }
            try deadlineClick(fresh.query.element(boundBy: 0))
            let menu = try uniqueOpenMenu(fresh.query, description: title)
            _ = try lifecycleControl(menu.children(matching: .menuItem).matching(NSPredicate(format: "title == %@", value)),
                scope: "ExportOptions/" + title + "/Menu", role: "MenuItem")
        }
        let fresh = try exportPopup(title, in: sheet)
        guard try exportBindingSignature(fresh) == signature, fresh.query.element(boundBy: 0).value as? String == value else {
            throw block("Export option binding/value not retained: " + title + "=" + value)
        }
        return signature
    }
    @MainActor private func destinationPanel(in photos: XCUIApplication) throws -> (panel: XCUIElement, go: XCUIElement?) {
        _ = try remainingTime(1)
        try rejectLifecycleAlert(photos)
        let windows = photos.windows.matching(identifier: "MainWindow")
        let windowCount = windows.count, dialogCount = photos.dialogs.count
        guard windowCount == 1, dialogCount == 0 else { throw block("Unknown export destination window/dialog") }
        let panels = windows.element(boundBy: 0).children(matching: .sheet)
        let panelCount = panels.count
        guard panelCount == 1 else { throw block("Missing/ambiguous direct export destination panel") }
        let panel = panels.element(boundBy: 0)
        guard panel.identifier == "open-panel" else { throw block("Unexpected export destination panel") }
        let children = panel.children(matching: .sheet)
        let childCount = children.count, totalSheetCount = photos.sheets.count
        guard childCount <= 1, totalSheetCount == 1 + childCount else { throw block("Unexpected export destination child/sheet") }
        guard childCount == 1 else { return (panel, nil) }
        let go = children.element(boundBy: 0)
        guard go.identifier == "GoToWindow" else { throw block("Unexpected export destination child identity") }
        return (panel, go)
    }
    @MainActor private func destinationPathField(in photos: XCUIApplication, panelLabel: String, expected: String? = nil) throws -> (element: XCUIElement, row: [Any], go: XCUIElement) {
        let parent = try destinationPanel(in: photos)
        guard parent.panel.label == panelLabel, let go = parent.go else { throw block("Go to Folder parent changed") }
        let fields = go.children(matching: .textField)
        let count = fields.count
        guard count == 1 else { throw block("Missing/ambiguous direct Go to Folder path field") }
        let input = fields.element(boundBy: 0)
        let identifier = input.identifier, enabled = input.isEnabled, hittable = input.isHittable
        guard identifier == "PathTextField", enabled, hittable else { throw block("Unusable observed Go to Folder field") }
        guard let value = input.value as? String, value.utf8.count <= 512,
              expected == nil || value == expected else { throw block("Go to Folder path differs from the trusted owned directory") }
        return (input, ["ExportSavePanel/GoToWindow", "TextField", identifier, input.title, input.label, value, count, enabled, hittable], go)
    }
    @MainActor private func chooseOwnedExportDirectory(_ directory: URL, in photos: XCUIApplication, original: Bool) throws {
        let root = try XCTUnwrap(lifecycleRoot)
        guard ["saved", "cancelled", "reverted", "original"].contains(directory.lastPathComponent),
              directory == root.appendingPathComponent(directory.lastPathComponent, isDirectory: true),
              original == (directory.lastPathComponent == "original"), directory.path.utf8.count <= 512 else { throw block("Unowned export destination URL") }
        try verifyOwnedExportTree()
        let initial = try destinationPanel(in: photos), finalTitle = original ? "Export Originals" : "Export"
        guard initial.go == nil else { throw block("Unexpected preexisting Go to Folder child") }
        let panelLabel = initial.panel.label
        func confirmButton(_ panel: XCUIElement) -> XCUIElementQuery {
            panel.descendants(matching: .button).matching(NSPredicate(format: "identifier == %@ AND title == %@", "OKButton", finalTitle))
        }
        _ = try lifecycleControl(confirmButton(initial.panel), scope: "ExportSavePanel", role: "Button", click: false)
        // Poll only the known direct child scope. Full parent/alert/path checks
        // run once in destinationPathField before any text or key input.
        let openingChildren = initial.panel.children(matching: .sheet).matching(identifier: "GoToWindow")
        try deadlineKey(photos, "g", modifierFlags: [.command, .shift])
        let childOpened = NSPredicate { _, _ in openingChildren.count > 0 }
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: childOpened, object: nil)],
                            timeout: try remainingTime(10)) == .completed else { throw block("Observed Go to Folder child absent") }
        _ = try remainingTime(1)
        let input = try destinationPathField(in: photos, panelLabel: panelLabel)
        // Click the exact field. typeText requires keyboard focus and fails if
        // it cannot type; no separate undocumented focus Boolean is sampled.
        try deadlineClick(input.element)
        try deadlineKey(input.element, "a", modifierFlags: .command)
        try deadlineText(input.element, directory.path)
        let entered = try destinationPathField(in: photos, panelLabel: panelLabel, expected: directory.path)
        _ = try retainLifecycleControl(entered.row)
        let ready = try destinationPathField(in: photos, panelLabel: panelLabel, expected: directory.path)
        _ = try retainLifecycleControl(ready.row)
        guard try JSONSerialization.data(withJSONObject: entered.row) == JSONSerialization.data(withJSONObject: ready.row),
              try JSONSerialization.data(withJSONObject: lifecycleReceipt(photosPID: lifecyclePhotosPID)).count <= 16_000 else { throw block("Go to Folder readback changed or exceeded proof budget") }
        try deadlineKey(ready.element, XCUIKeyboardKey.return, modifierFlags: [])
        // Poll only the exact child captured by the final owned-path observation.
        // Full alert/parent/destination guards run once below, before any Export.
        let childDismissed = NSPredicate { _, _ in !ready.go.exists }
        guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: childDismissed, object: nil)],
                            timeout: try remainingTime(10)) == .completed else { throw block("Go to Folder child did not dismiss") }
        _ = try remainingTime(1)
        let selected = try destinationPanel(in: photos)
        guard selected.go == nil, selected.panel.label == panelLabel else { throw block("Export destination panel changed after Return") }
        let location = try lifecycleControl(selected.panel.descendants(matching: .popUpButton)
            .matching(NSPredicate(format: "identifier == %@ AND title == %@", "where popup", "Where:")), scope: "ExportSavePanel", role: "PopUpButton", click: false)
        guard location.value as? String == directory.lastPathComponent else { throw block("Save panel location does not show the owned export directory") }
        try verifyOwnedExportTree()
        try rejectLifecycleAlert(photos)
        _ = try lifecycleControl(confirmButton(selected.panel), scope: "ExportSavePanel", role: "Button")
    }
    private func ownedExportDirectory(_ name: String) throws -> URL {
        guard ["saved", "cancelled", "reverted", "original"].contains(name), lifecycleExports[name] == nil else { throw block("Unexpected/repeated export phase") }
        if lifecycleRoot == nil {
            let temporary = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
            let root = temporary.appendingPathComponent("CelluloidPhotosLifecycle-" + UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            for child in ["saved", "cancelled", "reverted", "original"] {
                try FileManager.default.createDirectory(at: root.appendingPathComponent(child, isDirectory: true), withIntermediateDirectories: false)
            }
            lifecycleRoot = root
        }
        try verifyOwnedExportTree()
        return try XCTUnwrap(lifecycleRoot).appendingPathComponent(name, isDirectory: true)
    }
    private func verifyOwnedExportTree() throws {
        _ = try remainingTime(1)
        let root = try XCTUnwrap(lifecycleRoot)
        guard root == root.resolvingSymlinksInPath() else { throw block("Owned export root became a symlink") }
        let members = try FileManager.default.contentsOfDirectory(atPath: root.path)
        guard Set(members) == Set(["saved", "cancelled", "reverted", "original"]) else { throw block("Unexpected owned export root member") }
        for child in members {
            let directory = root.appendingPathComponent(child, isDirectory: true)
            let attributes = try FileManager.default.attributesOfItem(atPath: directory.path)
            guard attributes[.type] as? FileAttributeType == .typeDirectory,
                  directory.standardizedFileURL == directory.resolvingSymlinksInPath() else { throw block("Symlink/non-directory in owned export root") }
            let files = try FileManager.default.contentsOfDirectory(atPath: directory.path)
            guard files == (lifecycleExports[child] == nil ? [] : [Self.fixtureFilename]) else { throw block("Unexpected or stale owned export member") }
            if !files.isEmpty {
                let file = directory.appendingPathComponent(Self.fixtureFilename)
                var status = stat()
                guard file.path.withCString({ lstat($0, &status) }) == 0,
                      (status.st_mode & S_IFMT) == S_IFREG, status.st_nlink == 1,
                      status.st_size > 0, status.st_size <= 16 * 1024 * 1024 else { throw block("Owned export tree contains nonregular/linked/oversized file") }
            }
        }
    }
    @MainActor private func exportRaster(_ name: String, in photos: XCUIApplication, original: Bool) throws -> LifecycleRaster {
        _ = try remainingTime(1)
        guard original == (name == "original") else { throw block("Mismatched raw export/image binding") }
        try requireNoSheet(photos)
        let directory = try ownedExportDirectory(name)
        let file = directory.appendingPathComponent(Self.fixtureFilename)
        guard !FileManager.default.fileExists(atPath: file.path) else { throw block("Export destination already exists") }
        try openTopMenu("File", in: photos)
        let fileMenu = try uniqueOpenMenu(photos.menuBarItems.matching(NSPredicate(format: "title == %@", "File")), description: "File")
        let exportItems = fileMenu.children(matching: .menuItem).matching(NSPredicate(format: "identifier == %@ AND title == %@", "_NS:1604", "Export"))
        _ = try lifecycleControl(exportItems, scope: "File/Menu", role: "MenuItem")
        let exportMenu = try uniqueOpenMenu(exportItems, description: "Export")
        _ = try lifecycleControl(exportMenu.children(matching: .menuItem).matching(NSPredicate(format: "identifier == %@ AND title == %@",
            original ? "_NS:635" : "_NS:630", original ? "Export Unmodified Original For 1 Photo" : "Export 1 Photo")),
            scope: "File/Export/Menu", role: "MenuItem")
        try lifecycleWait(photos, seconds: 10, description: "Export options sheet absent") { photos.sheets.count > 0 }
        let options = try exportSheet(in: photos)
        guard options.identifier == "sheetWindow_export" else { throw block("Unobserved export options sheet identity") }
        var optionSignatures: [String: Data] = [:]
        if original {
            try setExportBinary(publicLabel("Export IPTC as XMP", role: .checkBox, in: options), role: "CheckBox", desired: 0, photos: photos)
        } else {
            optionSignatures["Photo Kind"] = try popup("Photo Kind", choose: "PNG", in: options)
            let disclosures = options.descendants(matching: .disclosureTriangle).matching(NSPredicate(format: "identifier == %@ AND label == %@", "button_disclosure", "customize"))
            try setExportBinary(disclosures, role: "DisclosureTriangle", desired: 1, photos: photos)
            optionSignatures["Color Profile"] = try popup("Color Profile", choose: "sRGB", in: options)
            optionSignatures["Size"] = try popup("Size", choose: "Full Size", in: options)
        }
        optionSignatures["File Name"] = try popup("File Name", choose: "Use File Name", in: options)
        optionSignatures["Subfolder Format"] = try popup("Subfolder Format", choose: "None", in: options)
        for (title, wanted) in [("Photo Kind", "PNG"), ("Color Profile", "sRGB"), ("Size", "Full Size"), ("File Name", "Use File Name"), ("Subfolder Format", "None")] {
            if original && ["Photo Kind", "Color Profile", "Size"].contains(title) { continue }
            let fresh = try exportPopup(title, in: options)
            guard let signature = optionSignatures[title], try exportBindingSignature(fresh) == signature,
                  fresh.query.element(boundBy: 0).value as? String == wanted else {
                throw block("Export option changed before Export: " + title)
            }
        }
        _ = try lifecycleControl(options.children(matching: .button).matching(NSPredicate(format: "identifier == %@ AND title == %@", "button_export", "Export")), scope: "ExportOptions", role: "Button")
        try chooseOwnedExportDirectory(directory, in: photos, original: original)
        try lifecycleWait(photos, description: "Owned export did not finish") {
            photos.sheets.count == 0 && photos.dialogs.count == 0 && FileManager.default.fileExists(atPath: file.path)
        }
        try requireNoSheet(photos)
        guard try FileManager.default.contentsOfDirectory(atPath: directory.path) == [Self.fixtureFilename] else { throw block("Export produced extra files or wrong filename") }
        let rawAllowance = min(16 * 1024 * 1024, 64 * 1024 * 1024 - lifecycleRawBytes)
        guard rawAllowance > 0 else { throw block("Raw export aggregate allowance exhausted") }
        let bytes = try readBoundedOwnedFile(file, maximumBytes: rawAllowance)
        guard lifecycleRawBytes + bytes.count <= 64 * 1024 * 1024 else { throw block("Raw export aggregate exceeds 64 MiB") }
        lifecycleRawBytes += bytes.count
        let retainedImage = original ? "lifecycle-source.png" : "lifecycle-" + name + ".png"
        // Preserve exact owned bytes and bounded framing before ImageIO/profile/
        // pixel acceptance. Failed decoding never becomes an accepted image.
        exportPNGDiagnostics.append(pngInventory(bytes, phase: name))
        if original {
            guard let source = retainedSource, bytes == source.bytes else {
                let failure = block("Unmodified original export differs from retained source bytes")
                do { try retainLifecycleBytes(bytes, named: "lifecycle-original-observed.png") }
                catch { exportPNGDiagnostics[exportPNGDiagnostics.count - 1]["retention"] = "omitted: fixed diagnostic byte allowance" }
                throw failure
            }
            guard retainedPNGHashes[retainedImage] == digest(bytes) else { throw block("Original source byte retention is missing") }
        } else { try retainLifecycleBytes(bytes, named: retainedImage) }
        let raster = try lifecycleRaster(bytes, expectedFormat: UTType.png.identifier)
        lifecycleExports[name] = ["image": retainedImage, "relative_path": name + "/" + Self.fixtureFilename,
            "bytes": bytes.count, "sha256": digest(bytes)]
        return raster
    }

    private func readBoundedOwnedFile(_ file: URL, maximumBytes: Int = 16 * 1024 * 1024) throws -> Data {
        _ = try remainingTime(1)
        let canonical = file.standardizedFileURL
        let parent = canonical.deletingLastPathComponent()
        let ownedSource = retainedFixtureURL?.standardizedFileURL == canonical
        let ownedExport = lifecycleRoot.map { root in
            ["saved", "cancelled", "reverted", "original"].contains { phase in
                root.appendingPathComponent(phase).appendingPathComponent(Self.fixtureFilename) == canonical
            }
        } ?? false
        guard ownedSource || ownedExport, maximumBytes > 0, maximumBytes <= 16 * 1024 * 1024,
              parent == parent.resolvingSymlinksInPath(), canonical.lastPathComponent == Self.fixtureFilename else {
            throw block("File is not a fixed owned source/export path")
        }
        let directoryFD = parent.path.withCString { Darwin.open($0, O_RDONLY | O_DIRECTORY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW) }
        guard directoryFD >= 0 else { throw block("Owned parent directory denied; no alternate location", operation: ["errno": errno]) }
        defer { Darwin.close(directoryFD) }
        var parentBefore = stat()
        guard fstat(directoryFD, &parentBefore) == 0, (parentBefore.st_mode & S_IFMT) == S_IFDIR else { throw block("Owned export parent changed") }
        let descriptor = canonical.lastPathComponent.withCString { openat(directoryFD, $0, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW) }
        guard descriptor >= 0 else { throw block("Owned file read denied or symlink; no alternate path", operation: ["filename": file.lastPathComponent, "errno": errno]) }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        var before = stat()
        guard fstat(descriptor, &before) == 0, (before.st_mode & S_IFMT) == S_IFREG,
              before.st_nlink == 1, before.st_size > 0, before.st_size <= Int64(maximumBytes) else {
            throw block("Owned export is not a bounded single-link regular file")
        }
        let size = Int(before.st_size)
        var bytes = Data(); bytes.reserveCapacity(size)
        while bytes.count < size {
            _ = try remainingTime(1)
            let chunk = try XCTUnwrap(handle.read(upToCount: min(65_536, size - bytes.count)))
            guard !chunk.isEmpty, chunk.count <= size - bytes.count else { throw block("Owned file truncated during read") }
            bytes.append(chunk)
        }
        var after = stat(), pathAfter = stat(), parentAfter = stat()
        let pathStatus = canonical.path.withCString { lstat($0, &pathAfter) }
        let parentStatus = parent.path.withCString { lstat($0, &parentAfter) }
        guard fstat(descriptor, &after) == 0, pathStatus == 0, parentStatus == 0,
              parent == parent.resolvingSymlinksInPath(), (parentAfter.st_mode & S_IFMT) == S_IFDIR,
              parentBefore.st_dev == parentAfter.st_dev, parentBefore.st_ino == parentAfter.st_ino,
              (after.st_mode & S_IFMT) == S_IFREG, (pathAfter.st_mode & S_IFMT) == S_IFREG,
              after.st_nlink == 1, pathAfter.st_nlink == 1,
              before.st_dev == after.st_dev, before.st_ino == after.st_ino,
              after.st_dev == pathAfter.st_dev, after.st_ino == pathAfter.st_ino,
              before.st_size == after.st_size, after.st_size == pathAfter.st_size, bytes.count == size,
              before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
              before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
              before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec,
              after.st_mtimespec.tv_sec == pathAfter.st_mtimespec.tv_sec,
              after.st_mtimespec.tv_nsec == pathAfter.st_mtimespec.tv_nsec,
              after.st_ctimespec.tv_sec == pathAfter.st_ctimespec.tv_sec,
              after.st_ctimespec.tv_nsec == pathAfter.st_ctimespec.tv_nsec else { throw block("Owned export/path changed during bounded read") }
        _ = try remainingTime(1)
        return bytes
    }
    private func pngHeader(_ data: Data) throws -> (colorType: Int, profileEncoding: String) {
        let bytes = [UInt8](data)
        guard bytes.count >= 45, bytes.count <= 128 * 1024,
              Array(bytes.prefix(8)) == [137, 80, 78, 71, 13, 10, 26, 10] else { throw block("Required PNG signature/128 KiB bound failed") }
        func u32(_ offset: Int) -> Int {
            Int(bytes[offset]) << 24 | Int(bytes[offset + 1]) << 16 | Int(bytes[offset + 2]) << 8 | Int(bytes[offset + 3])
        }
        guard u32(8) == 13, String(bytes: bytes[12..<16], encoding: .ascii) == "IHDR",
              u32(16) == 1200, u32(20) == 800, bytes[24] == 8, [2, 6].contains(bytes[25]),
              bytes[26] == 0, bytes[27] == 0, bytes[28] == 0 else {
            throw block("Required PNG dimensions/depth/color type/interlace failed", operation: ["sha256": digest(data), "bytes": data.count])
        }
        var offset = 8, chunks = 0, srgb = 0, icc = 0, textChunks = 0
        while offset < bytes.count {
            guard offset <= bytes.count - 12, chunks < 64 else { throw block("PNG chunk framing limit") }
            let count = u32(offset)
            guard count <= bytes.count - offset - 12 else { throw block("Truncated PNG chunk") }
            let tag = String(bytes: bytes[(offset + 4)..<(offset + 8)], encoding: .ascii) ?? ""
            let protected = Array(bytes[(offset + 4)..<(offset + 8 + count)])
            let actualCRC = protected.withUnsafeBufferPointer { crc32(0, $0.baseAddress, uInt($0.count)) }
            guard actualCRC == uLong(u32(offset + 8 + count)) else { throw block("PNG chunk CRC mismatch before decode") }
            if tag == "iTXt" {
                textChunks += 1
                guard textChunks == 1 else { throw block("Duplicate iTXt before decode") }
                try admitInternationalText(Array(bytes[(offset + 8)..<(offset + 8 + count)]))
            }
            if tag == "sRGB" {
                guard count == 1, bytes[offset + 8] == 0 else { throw block("PNG sRGB rendering intent mismatch") }
                srgb += 1
            }
            if tag == "iCCP" {
                icc += 1
                guard icc == 1 else { throw block("Duplicate ICC profile before decode") }
                try admitICC(Array(bytes[(offset + 8)..<(offset + 8 + count)]), pngSHA256: digest(data))
            }
            guard ["IHDR", "sRGB", "iCCP", "gAMA", "cHRM", "pHYs", "eXIf", "iTXt", "IDAT", "IEND"].contains(tag) else {
                throw block("Unsupported PNG chunk before decode", operation: ["chunk": tag, "sha256": digest(data)])
            }
            guard !["acTL", "fcTL", "fdAT", "tRNS"].contains(tag) else { throw block("Animated/transparency PNG is outside the fixture contract") }
            offset += count + 12; chunks += 1
        }
        guard offset == bytes.count, (srgb == 1 && icc == 0) || (srgb == 0 && icc == 1) else {
            throw block("PNG profile missing/ambiguous; pixel conversion is not a fallback", operation: ["sha256": digest(data), "sRGB_chunks": srgb, "iCCP_chunks": icc])
        }
        return (Int(bytes[25]), srgb == 1 ? "srgb-chunk" : "icc-reference")
    }
    private func admitInternationalText(_ payload: [UInt8]) throws {
        do { try Self.validateInternationalText(payload) }
        catch { throw block("Malformed or oversized PNG iTXt structure before decode") }
    }
    private func verifyInternationalTextContract() throws {
        let prefix = Array("Comment".utf8) + [UInt8](repeating: 0, count: 5)
        let plain = prefix + Array("color-neutral 文本".utf8)
        let compressed: [UInt8] = Array("Comment".utf8) + [0, 1, 0, 0, 0] + [120, 156, 75, 206, 207, 201, 47, 210, 205, 75, 45, 45, 41, 74, 204, 81, 120, 54, 173, 253, 217, 156, 53, 0, 89, 133, 9, 153]
        for payload in [prefix, plain, compressed] { try Self.validateInternationalText(payload) }
        for payload in [[UInt8](), Array("Comment".utf8) + [0, 2, 0, 0, 0], prefix + [255], prefix + [0],
                        prefix + [UInt8](repeating: 65, count: 16_385), Array(compressed.dropLast())] {
            do { try Self.validateInternationalText(payload); throw block("Native iTXt negative unexpectedly passed") }
            catch let error as NSError where error.domain == "Celluloid.PNG.iTXt" { }
        }
        print("MAC_HOST_PNG_ITXT_STRUCTURE_SELFTEST_PASSED")
    }
    private static func validateInternationalText(_ payload: [UInt8]) throws {
        // W3C PNG 11.3.3.4: inspect only the bounded envelope and UTF-8.
        // Text is never interpreted as XML/XMP, orientation or color authority.
        guard payload.count <= 16_384, let separator = payload.firstIndex(of: 0), (1...79).contains(separator),
              separator + 5 <= payload.count else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed/oversized PNG iTXt envelope"]) }
        let keyword = Array(payload[..<separator])
        guard keyword.allSatisfy({ (32...126).contains($0) || (161...255).contains($0) }),
              keyword.first != 32, keyword.last != 32,
              !zip(keyword, keyword.dropFirst()).contains(where: { pair in pair.0 == 32 && pair.1 == 32 }) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt keyword"]) }
        let flag = payload[separator + 1], method = payload[separator + 2]
        guard [0, 1].contains(flag), flag == 0 || method == 0,
              let languageEnd = payload[(separator + 3)...].firstIndex(of: 0),
              languageEnd + 1 < payload.count,
              let translatedEnd = payload[(languageEnd + 1)...].firstIndex(of: 0) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt compression/separators"]) }
        let language = payload[(separator + 3)..<languageEnd]
        guard language.allSatisfy({ $0 == 45 || (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) }),
              String(bytes: payload[(languageEnd + 1)..<translatedEnd], encoding: .utf8) != nil else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed PNG iTXt language/translated bytes"]) }
        var text = Array(payload[(translatedEnd + 1)...])
        if flag == 1 {
            let compressed = text
            var output = [UInt8](repeating: 0, count: 16_385)
            var outputCount = uLongf(output.count), inputCount = uLong(compressed.count)
            let status = output.withUnsafeMutableBufferPointer { destination in
                compressed.withUnsafeBufferPointer { source in
                    uncompress2(destination.baseAddress, &outputCount, source.baseAddress, &inputCount)
                }
            }
            guard status == Z_OK, outputCount <= 16_384, inputCount == uLong(compressed.count) else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "PNG iTXt bounded decompression failed"]) }
            text = Array(output.prefix(Int(outputCount)))
        }
        guard text.count <= 16_384, !text.contains(0), String(bytes: text, encoding: .utf8) != nil else { throw NSError(domain: "Celluloid.PNG.iTXt", code: 1, userInfo: [NSLocalizedDescriptionKey: "Malformed/oversized PNG iTXt UTF-8"]) }
    }
    private func admitICC(_ payload: [UInt8], pngSHA256: String) throws {
        _ = try remainingTime(1)
        guard let separator = payload.firstIndex(of: 0), (1...79).contains(separator),
              separator + 2 < payload.count, payload[separator + 1] == 0 else {
            throw block("Malformed PNG ICC profile envelope before decode", operation: ["sha256": pngSHA256])
        }
        let compressed = Array(payload[(separator + 2)...])
        // Apple's public system zlib module links libz. uncompress2 admits
        // caller-sized storage and reports consumed input, so neither an ICC
        // bomb nor a trailing/concatenated stream reaches ImageIO.
        var output = [UInt8](repeating: 0, count: 4097)
        var outputCount = uLongf(output.count)
        var inputCount = uLong(compressed.count)
        let status = output.withUnsafeMutableBufferPointer { destination in
            compressed.withUnsafeBufferPointer { source in
                uncompress2(destination.baseAddress, &outputCount, source.baseAddress, &inputCount)
            }
        }
        guard status == Z_OK, outputCount > 0, outputCount <= 4096, inputCount == uLong(compressed.count) else {
            throw block("PNG ICC bounded decompression/profile admission failed before decode",
                operation: ["sha256": pngSHA256, "zlib_status": status, "decoded_bytes": Int(outputCount), "consumed_bytes": Int(inputCount)])
        }
        let actual = Data(output.prefix(Int(outputCount)))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let reference = try XCTUnwrap(srgb.copyICCData()) as Data
        guard !reference.isEmpty, reference.count <= 4096, actual == reference else {
            throw block("PNG ICC bytes differ from independent sRGB reference; pixels were not compared",
                operation: ["sha256": pngSHA256, "icc_sha256": digest(actual)])
        }
        lifecycleICC = ["bytes": reference.count, "sha256": digest(reference)]
        _ = try remainingTime(1)
    }
    private func bitmap() throws -> CGContext {
        try XCTUnwrap(CGContext(data: nil, width: 1200, height: 800, bitsPerComponent: 8, bytesPerRow: 1200 * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue))
    }
    private func lifecycleRaster(_ data: Data, expectedFormat: String) throws -> LifecycleRaster {
        _ = try remainingTime(1)
        let header = try pngHeader(data)
        let imageSource = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary))
        guard CGImageSourceGetCount(imageSource) == 1,
              CGImageSourceGetType(imageSource) as String? == expectedFormat,
              let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any],
              properties[kCGImagePropertyPixelWidth] as? Int == 1200,
              properties[kCGImagePropertyPixelHeight] as? Int == 800,
              (properties[kCGImagePropertyOrientation] as? Int ?? 1) == 1,
              properties[kCGImagePropertyDepth] as? Int == 8,
              let image = CGImageSourceCreateImageAtIndex(imageSource, 0, nil), image.width == 1200, image.height == 800,
              image.bitsPerComponent == 8, image.colorSpace?.model == .rgb else {
            throw block("Export format/dimensions/orientation/depth mismatch", operation: ["sha256": digest(data), "bytes": data.count])
        }
        let context = try bitmap()
        context.interpolationQuality = .none
        context.draw(image, in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let rgba = Data(bytes: try XCTUnwrap(context.data), count: 1200 * 800 * 4)
        guard stride(from: 3, to: rgba.count, by: 4).allSatisfy({ rgba[$0] == 255 }) else { throw block("Export alpha mismatch; opaque source required") }
        let metadata: [String: Any] = ["bytes": data.count, "sha256": digest(data), "rgba_sha256": digest(rgba),
            "format": expectedFormat, "width": 1200, "height": 800, "bit_depth": 8,
            "color_type": header.colorType, "interlace": 0, "orientation": 1, "profile": "sRGB",
            "profile_encoding": header.profileEncoding, "alpha": "opaque"]
        return LifecycleRaster(bytes: data, rgba: rgba, metadata: metadata)
    }
    private func retainLifecycleBytes(_ bytes: Data, named name: String) throws {
        let names: Set<String> = ["lifecycle-source.png", "lifecycle-expected-save.png", "lifecycle-saved.png", "lifecycle-cancelled.png", "lifecycle-reverted.png", "lifecycle-original-observed.png"]
        guard names.contains(name), retainedPNGHashes[name] == nil, !bytes.isEmpty, bytes.count <= 128 * 1024,
              lifecyclePNGBytes + bytes.count <= 640 * 1024 else { throw block("Required lifecycle PNG admission failed") }
        lifecyclePNGBytes += bytes.count
        retainedPNGHashes[name] = digest(bytes)
        let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: "public.png")
        attachment.name = "celluloid-host-lifecycle-" + name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    private func retainLifecycleImage(_ image: LifecycleRaster, named name: String) throws {
        guard name != "lifecycle-original-observed.png", lifecycleImages[name] == nil else { throw block("Duplicate/diagnostic lifecycle image metadata") }
        if retainedPNGHashes[name] == nil { try retainLifecycleBytes(image.bytes, named: name) }
        guard retainedPNGHashes[name] == digest(image.bytes) else { throw block("Retained PNG bytes changed before acceptance") }
        lifecycleImages[name] = image.metadata
    }
    private func pngInventory(_ data: Data, phase: String) -> [String: Any] {
        // Framing only, no text values, ImageIO, profile interpretation or acceptance.
        var row: [String: Any] = ["schema": "Celluloid.OwnedPNGStructure.1", "acceptance": false,
            "phase": phase, "bytes": data.count, "sha256": digest(data)]
        guard data.count >= 8, data.count <= 128 * 1024,
              Array(data.prefix(8)) == [137,80,78,71,13,10,26,10] else { row["framing"] = "invalid-signature-or-size"; return row }
        let bytes = [UInt8](data)
        var offset = 8, chunks: [[Any]] = []
        while offset <= bytes.count - 12, chunks.count < 64 {
            let count = Int(bytes[offset]) << 24 | Int(bytes[offset + 1]) << 16 | Int(bytes[offset + 2]) << 8 | Int(bytes[offset + 3])
            let rawTag = Array(bytes[(offset + 4)..<(offset + 8)])
            let tag = rawTag.allSatisfy { (65...90).contains($0) || (97...122).contains($0) }
                ? String(decoding: rawTag, as: UTF8.self) : rawTag.map { String(format: "%02x", $0) }.joined()
            chunks.append([tag, count, offset])
            guard count <= bytes.count - offset - 12 else { row["framing"] = "truncated-chunk"; row["chunks"] = chunks; return row }
            offset += count + 12
        }
        row["chunks"] = chunks
        row["framing"] = offset == bytes.count ? "complete-span" : "truncated-or-chunk-limit"
        return row
    }
    private func expectedFade(_ original: LifecycleRaster) throws -> (raster: LifecycleRaster, jpegSHA256: String) {
        _ = try remainingTime(1)
        // Deliberately independent from production filter maps, renderer and codec.
        // Match only their published sRGB/opaque/ImageIO JPEG-quality contract.
        let source = try XCTUnwrap(CGImageSourceCreateWithData(original.bytes as CFData,
            [kCGImageSourceShouldCache: false, kCGImageSourceShouldCacheImmediately: false] as CFDictionary))
        let cg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary))
        let input = CIImage(cgImage: cg)
        let filter = try XCTUnwrap(CIFilter(name: "CIPhotoEffectInstant", parameters: [kCIInputImageKey: input]))
        let filtered = try XCTUnwrap(filter.outputImage).cropped(to: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let ci = CIContext(options: [.outputColorSpace: srgb, .cacheIntermediates: false])
        defer { ci.clearCaches() }
        let output = try XCTUnwrap(ci.createCGImage(filtered, from: filtered.extent, format: .RGBA8, colorSpace: srgb))
        let composition = try bitmap()
        composition.interpolationQuality = .high
        composition.draw(output, in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let flattened = try bitmap()
        flattened.interpolationQuality = .high
        flattened.setFillColor(CGColor(gray: 1, alpha: 1))
        flattened.fill(CGRect(x: 0, y: 0, width: 1200, height: 800))
        flattened.draw(try XCTUnwrap(composition.makeImage()), in: CGRect(x: 0, y: 0, width: 1200, height: 800))
        let jpeg = NSMutableData()
        let encoder = try XCTUnwrap(CGImageDestinationCreateWithData(jpeg, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(encoder, try XCTUnwrap(flattened.makeImage()), [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
        guard CGImageDestinationFinalize(encoder), jpeg.length > 0, jpeg.length <= 16 * 1024 * 1024 else { throw block("Independent JPEG reference encode failed") }
        let decoded = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let decodedImage = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoded, 0, nil))
        guard decodedImage.width == 1200, decodedImage.height == 800 else { throw block("Independent JPEG reference dimensions changed") }
        let png = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(png, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, decodedImage,
            [kCGImagePropertyPNGDictionary: [kCGImagePropertyPNGInterlaceType: 0]] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw block("Independent PNG reference encode failed") }
        return (try lifecycleRaster(png as Data, expectedFormat: UTType.png.identifier), digest(jpeg as Data))
    }
    private func maximumDelta(_ lhs: Data, _ rhs: Data) throws -> Int {
        guard lhs.count == 1200 * 800 * 4, lhs.count == rhs.count else { throw block("Pixel comparison size mismatch") }
        var maximum = 0
        for index in lhs.indices { maximum = max(maximum, abs(Int(lhs[index]) - Int(rhs[index]))) }
        return maximum
    }

    private func value(_ key: String) throws -> String { try XCTUnwrap(context[key] as? String, "Missing bound context: " + key) }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func digest(_ url: URL) throws -> String { digest(try Data(contentsOf: url)) }
    private func text(_ string: String, named name: String) throws {
        let bytes = Data(string.utf8.prefix(120_000))
        try diagnostic(bytes, named: name, type: "public.utf8-plain-text")
    }
    private func report(_ object: [String: Any], named name: String) throws {
        try proof(JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]), named: name)
    }
    private func proof(_ bytes: Data, named name: String) throws {
        let names = ["transport.json", "containing-process.json", "photos-process.json", "fixture.json", "fixture-ownership.json",
                     "host-selection.json", "host-editor-before-process.json", "extension-self-identity.json",
                     "host-editor-after-process.json", "prerequisite.json", "lifecycle.json", "outcome.json"]
        let limit = name.hasSuffix(".txt") || name == "fixture.json" ? 120_000 : 16_000
        guard names.contains(name), !emittedProofs.contains(name), !bytes.isEmpty, bytes.count <= limit,
              proofBytes + bytes.count <= 160_000 else { throw block("Unexpected or oversized proof receipt") }
        emittedProofs.insert(name); proofBytes += bytes.count
        let record: [String: Any] = ["schema": "Celluloid.MacHostProof.2", "sequence": proofSequence,
            "name": name, "bytes": bytes.count, "sha256": digest(bytes), "base64": bytes.base64EncodedString(),
            "source_sha": try value("source_sha"), "context_sha256": contextHash,
            "test_source_sha256": try value("test_source_sha256"), "verifier_sha256": try value("script_sha256")]
        let serialized = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        print("MAC_HOST_PROOF " + String(decoding: serialized, as: UTF8.self)); proofSequence += 1
    }
    private func diagnostic(_ bytes: Data, named name: String, type: String) throws {
        let names: Set<String> = ["initial.txt", "imported.txt", "single-photo.txt", "editing.txt", "extensions.txt",
            "manage-observed.txt", "host-editor.txt", "last-observed.txt", "missing-control-edit.txt", "missing-control-extensions.txt",
            "extensions.jpg", "last-observed.jpg"]
        guard names.contains(name), !emittedDiagnostics.contains(name), !bytes.isEmpty,
              bytes.count <= (name.hasSuffix(".jpg") ? 700_000 : 120_000) else { throw block("Unexpected or oversized diagnostic attachment") }
        emittedDiagnostics.insert(name)
        let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: type)
        attachment.name = "celluloid-host-diagnostic-" + name; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func block(_ reason: String, operation: [String: Any]? = nil) -> NSError {
        if firstBlockedOperation == nil {
            var record: [String: Any] = ["stage": stage, "reason": String(reason.prefix(2000))]
            if let operation { record["operation"] = operation }
            firstBlockedOperation = record
        }
        print("MAC_HOST_BLOCKED stage=" + stage + " reason=" + reason)
        return NSError(domain: "MacPhotosHostPrerequisite", code: 1, userInfo: [NSLocalizedDescriptionKey: reason])
    }
}
