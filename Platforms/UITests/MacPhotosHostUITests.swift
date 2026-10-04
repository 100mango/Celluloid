import XCTest
import AppKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

/// Opt-in, real Apple Photos host discovery. This test never instantiates the
/// extension controller and deliberately cannot certify the complete host E2E.
final class MacPhotosHostUITests: XCTestCase {
    private var interruption: NSObjectProtocol?
    private var reportFolder: URL?
    private var context: [String: Any] = [:]
    private var stage = "not-started"

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
        reportFolder = URL(fileURLWithPath: try value("evidence_path"))
    }
    override func tearDownWithError() throws {
        defer { if let interruption { removeUIInterruptionMonitor(interruption) }; interruption = nil }
        try super.tearDownWithError()
    }

    @MainActor func testInstalledExtensionIsInvokedByActualPhotos() throws {
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        defer {
            try? checkpoint(photos, "last-observed", screenshot: true)
            try? report(["source_sha": context["source_sha"] as? String ?? "missing",
                         "last_stage": stage, "complete_host_e2e": false,
                         "save_reopen_cancel_revert": "not executed in prerequisite phase"], named: "outcome.json")
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

        stage = "observe-registration"
        let registered = try command("/usr/bin/pluginkit", ["-m", "-v", "-i", try value("extension_id")])
        try text(registered, named: "registration-before.txt")
        // Do not add or elect an extension with pluginkit. The normal app install
        // and Photos Manage UI must reveal registration and selection themselves.

        stage = "photos-first-use-and-synthetic-import"
        photos.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        photos.launch()
        let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        XCTAssertEqual(hosts.count, 1)
        let host = try XCTUnwrap(hosts.first)
        XCTAssertEqual(host.bundleURL?.path, "/System/Applications/Photos.app")
        try report(["bundle": host.bundleURL!.path, "executable": host.executableURL?.path ?? "", "pid": host.processIdentifier], named: "photos-process.json")
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
        try report(["source_sha": try value("source_sha"), "mode": mode,
                    "initial_count": 0, "selected_count": assets.count,
                    "asset_label": assets.firstMatch.label, "fixture_sha256": fixtureHash,
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
        try checkpoint(photos, "extensions", screenshot: true)
        let celluloid = photos.menuItems.matching(NSPredicate(format: "label == %@", "Celluloid"))
        if celluloid.count != 1 || !celluloid.firstMatch.isHittable {
            stage = "extension-not-selectable-observe-manage"
            let manage = namedControls("Manage", in: photos) + namedControls("Manage…", in: photos)
            if manage.count == 1 && manage[0].isHittable {
                manage[0].click()
                let settings = XCUIApplication(bundleIdentifier: "com.apple.systempreferences")
                _ = settings.windows.firstMatch.waitForExistence(timeout: 10)
                try checkpoint(settings, "manage-observed")
                // Do not guess a toggle or change any preference in this probe.
                // The exact observed Photos Editing row must be reviewed first.
            }
            throw block("Celluloid is not uniquely selectable; actual Manage state captured, enablement not guessed")
        }
        try assertUniqueRegistration()
        stage = "invoke-real-photos-extension"
        celluloid.firstMatch.click()
        let editor = photos.descendants(matching: .any)["photos-extension.filter"].firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 30), "Actual extension editor did not appear in Photos")
        XCTAssertFalse(photos.descendants(matching: .any)["photos-extension.error"].firstMatch.exists)
        XCTAssertFalse(photos.descendants(matching: .any)["photos-extension.read-only"].firstMatch.exists)
        try checkpoint(photos, "host-editor")
        stage = "bind-running-extension-executable"
        let script = URL(fileURLWithPath: try value("script_path"))
        XCTAssertEqual(try digest(script), try value("script_sha256"))
        let processes = try command("/usr/bin/env", ["python3", script.path, "processes"])
        print("MAC_HOST_PROCESS_PROVENANCE " + processes)
        try assertUniqueRegistration()
        stage = "host-entry-prerequisite-passed"
        try report(["prerequisite_passed": true, "complete_host_e2e": false,
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
    private func assertUniqueRegistration() throws {
        let listing = try command("/usr/bin/pluginkit", ["-m", "-v", "-i", try value("extension_id")])
        try text(listing, named: "registration-selected.txt")
        let expected = URL(fileURLWithPath: try value("extension_path")).resolvingSymlinksInPath().path
        // -v returns matching bundle paths. An unfamiliar output format is a
        // blocker; never interpret a menu label or identity as path evidence.
        let paths = listing.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.hasPrefix("/") && $0.hasSuffix(".appex") }
            .map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path }
        guard paths == [expected] else { throw block("Missing/ambiguous registered extension path: " + paths.joined(separator: "; ")) }
        try report(["source_sha": try value("source_sha"), "extension_id": try value("extension_id"),
                    "expected_extension_path": expected, "registered_paths": paths,
                    "registration_text_sha256": try digest(folder().appendingPathComponent("registration-selected.txt"))],
                   named: "registration-selected.json")
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
            try (bytes as Data).write(to: try folder().appendingPathComponent(name == "extensions" ? "extensions.jpg" : "last-observed.jpg"))
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
        guard p.terminationStatus == 0 else { throw block("Read-only command failed: " + result) }
        return result
    }
    private func value(_ key: String) throws -> String { try XCTUnwrap(context[key] as? String, "Missing bound context: " + key) }
    private func folder() throws -> URL { try XCTUnwrap(reportFolder) }
    private func digest(_ url: URL) throws -> String { SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined() }
    private func text(_ string: String, named name: String) throws {
        let bytes = Data(string.utf8.prefix(120_000))
        try bytes.write(to: try folder().appendingPathComponent(name))
    }
    private func report(_ object: [String: Any], named name: String) throws {
        try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]).write(to: try folder().appendingPathComponent(name))
    }
    private func block(_ reason: String) -> NSError {
        print("MAC_HOST_BLOCKED stage=" + stage + " reason=" + reason)
        return NSError(domain: "MacPhotosHostPrerequisite", code: 1, userInfo: [NSLocalizedDescriptionKey: reason])
    }
}
