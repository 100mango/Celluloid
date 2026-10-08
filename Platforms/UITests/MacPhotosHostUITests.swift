import XCTest
import AppKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

/// Opt-in, real Apple Photos host-entry v2. This test never instantiates the
/// extension controller and deliberately cannot certify the complete host E2E.
final class MacPhotosHostUITests: XCTestCase {
    private static let hostEntryContract = "Celluloid.PhotosHostEntry.2"
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
        contextHash = digest(data)
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("script_path"))), try value("script_sha256"))
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("test_source_path"))), try value("test_source_sha256"))
    }
    override func tearDownWithError() throws {
        defer { if let interruption { removeUIInterruptionMonitor(interruption) }; interruption = nil }
        try super.tearDownWithError()
    }

    @MainActor func testInstalledExtensionIsInvokedByActualPhotos() throws {
        // Validate the exact read-only input before any host UI action. Only
        // XCTest stdout/attachments carry data back across the sandbox boundary.
        try report(["schema": "Celluloid.HostTransport.2", "host_entry_contract": Self.hostEntryContract, "source_sha": try value("source_sha"),
                    "context_sha256": contextHash, "test_source_sha256": try value("test_source_sha256"),
                    "verifier_sha256": try value("script_sha256"),
                    "app_executable_sha256": try value("app_executable_sha256"),
                    "extension_executable_sha256": try value("extension_executable_sha256"),
                    "external_writes": false, "context_validated": true], named: "transport.json")
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        var photosIdentityVerified = false
        defer {
            // Preserve the original failure before any optional AX/screenshot
            // request can itself fail. This record grants no host acceptance.
            var outcome: [String: Any] = ["source_sha": context["source_sha"] as? String ?? "missing",
                "last_stage": stage, "host_entry_contract": Self.hostEntryContract, "complete_host_e2e": false,
                "save_reopen_cancel_revert": "not executed in prerequisite phase"]
            if let firstBlockedOperation { outcome["first_blocked_operation"] = firstBlockedOperation }
            if let extensionMenuObservation { outcome["extension_menu_observation"] = extensionMenuObservation }
            try? report(outcome, named: "outcome.json")
            if photosIdentityVerified {
                do { try checkpoint(photos, "last-observed", screenshot: true) }
                catch { print("MAC_HOST_DIAGNOSTIC_FAILED " + String(error.localizedDescription.prefix(1000))) }
            }
        }
        stage = "launch-exact-installed-containing-app"
        let appURL = URL(fileURLWithPath: try value("app_path")).standardizedFileURL.resolvingSymlinksInPath()
        let app = XCUIApplication(url: appURL)
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-ApplePersistenceIgnoreState", "YES"]
        app.launch()
        let candidates = NSRunningApplication.runningApplications(withBundleIdentifier: "Mango.Celluloid")
        XCTAssertEqual(candidates.count, 1, "An unexpected containing app instance makes identity ambiguous")
        let running = try XCTUnwrap(candidates.first)
        XCTAssertEqual(running.bundleURL?.standardizedFileURL.resolvingSymlinksInPath(), appURL)
        XCTAssertEqual(running.executableURL?.standardizedFileURL.resolvingSymlinksInPath().path, try value("app_executable"))
        XCTAssertEqual(try digest(URL(fileURLWithPath: value("app_executable"))), try value("app_executable_sha256"))
        try report(["bundle": appURL.path, "executable": try value("app_executable"), "pid": running.processIdentifier], named: "containing-process.json")
        let startupCancel = app.windows["open-panel"].buttons["CancelButton"]
        if startupCancel.waitForExistence(timeout: 3) { startupCancel.click() }
        app.terminate()

        // Host-entry v2 tests documented Photos UI behavior. No registry query
        // is retried or relocated; the historical denied operation stays failed.

        stage = "photos-first-use-and-synthetic-import"
        photos.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        photos.launch()
        let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        XCTAssertEqual(hosts.count, 1)
        let host = try XCTUnwrap(hosts.first)
        XCTAssertEqual(host.bundleURL?.path, "/System/Applications/Photos.app")
        try report(["bundle": host.bundleURL!.path, "executable": host.executableURL?.path ?? "", "pid": host.processIdentifier], named: "photos-process.json")
        photosIdentityVerified = true
        let photosPID = host.processIdentifier
        // The sole first-use action already observed and qualified in the base
        // Photos27 synthetic-library lane. No account/permission alert is accepted.
        let started = photos.buttons["Get Started"]
        if started.waitForExistence(timeout: 5) { started.click() }
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
            XCTAssertTrue(assets.firstMatch.waitForExistence(timeout: 20)); XCTAssertEqual(assets.count, 1)
            XCTAssertEqual(assets.firstMatch.label, seed["asset_label"] as? String)
            fixtureHash = try XCTUnwrap(seed["fixture_sha256"] as? String)
            try report(seed, named: "fixture.json")
        } else {
            XCTAssertEqual(mode, "require-empty-library")
            let empty = photos.staticTexts["_NS:99"]
            XCTAssertTrue(empty.waitForExistence(timeout: 10))
            XCTAssertEqual(empty.value as? String, "Welcome to Photos", "Never import into an unknown populated library")
            XCTAssertEqual(assets.count, 0)
            let fixture = try makeFixture(); fixtureHash = try digest(fixture)
            try importFixture(fixture, into: photos)
        }
        try checkpoint(photos, "imported")
        XCTAssertTrue(assets.firstMatch.waitForExistence(timeout: 20))
        XCTAssertEqual(assets.count, 1, "Only the freshly imported owned synthetic asset may be opened")
        XCTAssertTrue(assets.firstMatch.isHittable)
        let selectedAssetLabel = assets.firstMatch.label
        try report(["source_sha": try value("source_sha"), "mode": mode,
                    "initial_count": 0, "selected_count": assets.count,
                    "asset_label": selectedAssetLabel, "fixture_sha256": fixtureHash,
                    "app_executable_sha256": try value("app_executable_sha256"),
                    "width": 1200, "height": 800], named: "fixture-ownership.json")
        assets.firstMatch.doubleClick()
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
        invocationItems.element(boundBy: 0).click()
        stage = "observe-ready-editor-before-process"
        try report(readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash,
            assetLabel: selectedAssetLabel, phase: "before-process"), named: "host-editor-before-process.json")
        try checkpoint(photos, "host-editor")
        stage = "bind-running-extension-executable"
        let script = URL(fileURLWithPath: try value("script_path"))
        XCTAssertEqual(try digest(script), try value("script_sha256"))
        let processes = try command("/usr/bin/env", ["python3", script.path, "processes"])
        let processReceipt = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(processes.utf8)) as? [String: Any])
        try report(processReceipt, named: "extension-process.json")
        stage = "observe-ready-editor-after-process"
        try report(readyEditorObservation(in: photos, expectedPID: photosPID, fixtureHash: fixtureHash,
            assetLabel: selectedAssetLabel, phase: "after-process"), named: "host-editor-after-process.json")
        stage = "host-entry-prerequisite-passed"
        try report(["host_entry_contract": Self.hostEntryContract, "prerequisite_passed": true, "complete_host_e2e": false,
                    "production_source_base": try value("base_sha"), "source_sha": try value("source_sha"),
                    "pending": ["exact host save/cancel/revert/export UI", "resource and geometry readback", "complete lifecycle pixel oracle"]], named: "prerequisite.json")
        print("MAC_HOST_PREREQUISITE_PASSED actual Photos invocation and exact running extension identity; full lifecycle unexecuted")
        // Do not modify the synthetic asset or guess the host's dismissal UI.
        // Fresh runner disposal owns cleanup after the bounded evidence capture.
    }

    @MainActor private func importFixture(_ fixture: URL, into photos: XCUIApplication) throws {
        let file = photos.menuBarItems["File"]
        XCTAssertTrue(file.waitForExistence(timeout: 10)); file.click()
        let item = photos.menuItems["_NS:1096"] // Observed Photos27 Import… identity in base evidence.
        XCTAssertTrue(item.exists && item.isEnabled); item.click()
        photos.typeKey("g", modifierFlags: [.command, .shift])
        photos.typeKey("a", modifierFlags: .command); photos.typeText(fixture.path)
        photos.typeKey(.return, modifierFlags: [])
        let open = photos.sheets["open-panel"].buttons["OKButton"]
        XCTAssertTrue(open.waitForExistence(timeout: 10)); open.click()
        let review = photos.buttons["Review for Import"]
        if review.waitForExistence(timeout: 3) { review.click() }
        let all = photos.buttons["Import All New Photos"]
        if all.waitForExistence(timeout: 3) { all.click() }
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
        controls[0].click()
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
            guard XCTWaiter.wait(for: [expectation], timeout: 30) == .completed else {
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
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("CelluloidPhotosHost-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: false)
        let file = dir.appendingPathComponent("Celluloid-Owned-Host-" + UUID().uuidString + ".png")
        let destination = try XCTUnwrap(CGImageDestinationCreateWithURL(file as CFURL, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil); XCTAssertTrue(CGImageDestinationFinalize(destination))
        try report(["source_sha": try value("source_sha"), "synthetic_filename": file.lastPathComponent, "sha256": try digest(file),
                    "width": width, "height": height, "purpose": "host selection prerequisite only"], named: "fixture.json")
        return file
    }
    private func command(_ executable: String, _ args: [String]) throws -> String {
        let p = Process(), pipe = Pipe()
        p.executableURL = URL(fileURLWithPath: executable); p.arguments = args
        var environment = ProcessInfo.processInfo.environment
        for (key, value) in (context["runner_environment"] as? [String: String] ?? [:]) { environment[key] = value }
        p.environment = environment; p.standardOutput = pipe; p.standardError = pipe
        try p.run()
        let deadline = Date().addingTimeInterval(20)
        while p.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
        if p.isRunning { p.terminate(); throw block("Bounded read-only command timed out: " + executable) }
        let bytes = pipe.fileHandleForReading.readDataToEndOfFile()
        guard bytes.count <= 120_000 else { throw block("Read-only command exceeded output budget") }
        let result = String(decoding: bytes, as: UTF8.self)
        guard p.terminationStatus == 0 else {
            throw block("Read-only command failed: " + result,
                        operation: ["executable": executable, "arguments": args, "exit_code": p.terminationStatus])
        }
        return result
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
                     "host-selection.json", "host-editor-before-process.json", "extension-process.json",
                     "host-editor-after-process.json", "prerequisite.json", "outcome.json"]
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
