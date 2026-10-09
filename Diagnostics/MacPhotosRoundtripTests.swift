import XCTest
import AppKit
import CoreFoundation
import CoreGraphics
import CoreImage
import CryptoKit
import Darwin
import ImageIO
import UniformTypeIdentifiers
import zlib

/// Diagnostic only: one unchanged writer invocation and one neutral Photos asset.
/// No actual extension callback, prior-run delivery, or release acceptance claim.
final class MacPhotosRoundtripTests: XCTestCase {
    private static let fixtureFilename = "Celluloid-Owned-Roundtrip.png"
    private static let jpegFilename = "Celluloid-Owned-Roundtrip.jpg"
    private var interruption: NSObjectProtocol?
    private var context: [String: Any] = [:]
    private var contextHash = ""
    private var stage = "not-started"
    private var firstFailure: String?
    private var testStarted: TimeInterval = 0
    private let lifecycleDeadlineSeconds = 900
    private var lifecyclePhotosPID: pid_t = 0
    private var lifecycleAssetLabel = ""
    private var singlePhotoTopologies: [String] = []
    private var lifecycleControls: [Int] = []
    private var lifecycleControlCatalog: [[Any]] = []
    private var exportOptionBindings: [[Any]] = []
    private var exportBinaryStates: [[Any]] = []
    private var binaryScalarSelfTested = false
    private var lifecycleExports: [String: [String: Any]] = [:]
    private var lifecycleICC: [String: Any]?
    private var lifecycleRoot: URL?
    private var exportRootState: stat?
    private var exportDirectoryStates: [String: stat] = [:]
    private var writerDirectory: URL?
    private var retainedWriterBytes: Data?
    private var writerDirectoryState: stat?
    private var retainedFixtureURL: URL?
    private var inputURLs: Set<URL> = []
    private var observedRawBytes = 0
    private var images: [String: [String: Any]] = [:]
    private var receipt: [String: Any] = [:]
    private var phases: [String] = []
    private struct LifecycleRaster { let bytes: Data; let rgba: Data; let metadata: [String: Any] }
    private struct BinaryScalar { let kind: String; let runtimeType: String; let encoding: String; let raw: Any; let state: Int }

    override func setUpWithError() throws {
        try super.setUpWithError(); continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["CELLULOID_PHOTOS_ROUNDTRIP_PREREQUISITE"] == "1" else {
            throw XCTSkip("Closed owned roundtrip diagnostic only")
        }
        interruption = addUIInterruptionMonitor(withDescription: "Stop unknown Photos roundtrip interruption") { _ in
            print("ROUNDTRIP_DENIED_STOP unexpected interruption; no action taken")
            fatalError("ROUNDTRIP_DENIED_STOP")
        }
    }
    override func tearDownWithError() throws {
        defer { if let interruption { removeUIInterruptionMonitor(interruption) }; interruption = nil }
        try super.tearDownWithError()
    }
    @MainActor func testOwnedWriterJPEGPhotosRoundtrip() throws {
        testStarted = ProcessInfo.processInfo.systemUptime
        let contextPath = try XCTUnwrap(ProcessInfo.processInfo.environment["CELLULOID_PHOTOS_ROUNDTRIP_CONTEXT"])
        let contextURL = URL(fileURLWithPath: contextPath).standardizedFileURL
        guard contextURL.lastPathComponent == "roundtrip-context.json" else { throw block("Unknown context file") }
        let rawContext = try boundedRegularBytes(contextURL, maximumBytes: 32_000)
        guard !rawContext.isEmpty, rawContext.count <= 32_000 else { throw block("Context cap") }
        context = try XCTUnwrap(JSONSerialization.jsonObject(with: rawContext) as? [String: Any]); contextHash = digest(rawContext)
        guard context["schema"] as? String == "Celluloid.OwnedPhotosRoundtripContext.1",
              context["parent"] as? String == "13e9a1ed63c6e7744803419f27e429a759df1209",
              context["run_attempt"] as? Int == 1, context["case_seconds"] as? Int == 900 else { throw block("Context identity/clock") }
        let runtime = try XCTUnwrap(context["runtime"] as? [String: Any])
        guard runtime["platform"] as? String == "macOS", runtime["osVersion"] as? String == "27.0.1",
              runtime["osBuildNumber"] as? String == "26A434", runtime["architecture"] as? String == "arm64",
              runtime["diagnostic_only"] as? Bool == true, runtime["qualification_equivalence"] as? Bool == false else { throw block("Exact diagnostic runtime context") }
        let actualOS = ProcessInfo.processInfo.operatingSystemVersion
        guard actualOS.majorVersion == 27, actualOS.minorVersion == 0, actualOS.patchVersion == 1 else { throw block("Actual test OS differs from context") }
        receipt = ["schema": "Celluloid.OwnedPhotosRoundtripReceipt.1", "source_sha": try value("source_sha"), "context_sha256": contextHash,
            "run_id": try value("run_id"), "run_attempt": 1, "runtime": runtime, "complete": false,
            "allowed_max_channel_delta": 2, "pixel_contract_passed": false, "historical_rgba_equal": false,
            "actual_extension_writer_observed": false, "actual_photos_callback_observed": false, "qualification_equivalence": false,
            "inputs_checked": false, "writer_start_count": 0, "writer_claim_succeeded": false, "writer_reservation_completed": false]
        defer {
            do { try emitProof() }
            catch { print("ROUNDTRIP_PROOF_FAILED " + String(error.localizedDescription.prefix(500))) }
        }
        try verifySourcesAndBuild()
        let inputs = try XCTUnwrap(context["inputs"] as? [String: [String: Any]])
        let root = URL(fileURLWithPath: try value("repository_root")).standardizedFileURL
        let paths = ["source": "Platforms/MacExtensionTests/Fixtures/lifecycle-source.png", "jpeg": "Diagnostics/Fixtures/intended.jpg",
                     "expected": "Diagnostics/Fixtures/lifecycle-expected-save.png", "historical": "Diagnostics/Fixtures/lifecycle-saved.png"]
        guard Set(inputs.keys) == Set(paths.keys) else { throw block("Fixed input set") }
        for (name, rel) in paths {
            let url = root.appendingPathComponent(rel).standardizedFileURL
            guard inputs[name]?["path"] as? String == url.path, url == url.resolvingSymlinksInPath() else { throw block("Input path binding") }
            inputURLs.insert(url)
        }
        func input(_ name: String) throws -> Data {
            let row = try XCTUnwrap(inputs[name]); let url = URL(fileURLWithPath: try XCTUnwrap(row["path"] as? String))
            let bytes = try readBoundedOwnedFile(url, maximumBytes: 65_536)
            guard bytes.count == row["bytes"] as? Int, digest(bytes) == row["sha256"] as? String else { throw block("Input size/hash mismatch") }
            return bytes
        }
        stage = "reference"
        let sourceBytes = try input("source"), jpeg = try input("jpeg"), expectedBytes = try input("expected"), historyBytes = try input("historical")
        guard digest(sourceBytes) == "6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772",
              digest(jpeg) == "1f6b8bb3ea7963c0663965da27c9b41e717335b3d4a6f011a70e83762c1904ba" else { throw block("Frozen source/JPEG changed") }
        let source = try lifecycleRaster(sourceBytes, expectedFormat: UTType.png.identifier)
        let expected = try expectedFade(source)
        guard expected.jpegSHA256 == digest(jpeg), expected.raster.bytes == expectedBytes else { throw block("Independent reference drift before Photos") }
        let decoded = try decodedJPEG(jpeg)
        guard decoded.bytes == expectedBytes else { throw block("JPEG decode differs from frozen independent PNG") }
        let history = try lifecycleRaster(historyBytes, expectedFormat: UTType.png.identifier)
        receipt["source_fixture_sha256"] = digest(sourceBytes); receipt["jpeg_sha256"] = digest(jpeg)
        receipt["expected_rgba_sha256"] = digest(expected.raster.rgba); receipt["historical_rgba_sha256"] = digest(history.rgba)
        receipt["inputs_checked"] = true; phases.append("reference")
        try verifyBinaryScalarContract()
        let parent = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
        let writerRoot = parent.appendingPathComponent("CelluloidPhotosRoundtrip-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: writerRoot, withIntermediateDirectories: false)
        writerDirectory = writerRoot
        var initialWriterDirectory = stat()
        guard writerRoot.path.withCString({ lstat($0, &initialWriterDirectory) }) == 0, initialWriterDirectory.st_mode & S_IFMT == S_IFDIR, initialWriterDirectory.st_uid == getuid() else { throw block("Unowned newly-created writer directory") }
        writerDirectoryState = initialWriterDirectory
        try verifyWriterDirectory(empty: true)
        let destination = writerRoot.appendingPathComponent(Self.jpegFilename); retainedFixtureURL = destination
        let writer = PhotosOutputWrite(destination: destination)
        guard writer.destination == destination, !FileManager.default.fileExists(atPath: destination.path) else { throw block("Unexpected writer destination") }
        stage = "writer-start"
        let finished = expectation(description: "One exact owned writer completion")
        var result: Result<Void, PhotosOutputWrite.Failure>?; var completions = 0
        receipt["writer_start_count"] = 1
        writer.start(jpeg: jpeg) { observedWriter, observedResult in
            completions += 1
            guard observedWriter === writer else { XCTFail("Wrong diagnostic writer completion"); return }
            result = observedResult; finished.fulfill()
        }
        wait(for: [finished], timeout: try remainingTime(10))
        guard completions == 1, let result else { throw block("Missing/repeated writer completion") }
        if case .failure = result { throw block("Owned writer failed before Photos") }
        try verifyWriterDirectory(empty: false)
        let committed = try readBoundedOwnedFile(destination, maximumBytes: 65_536)
        try retainRaw(committed, name: "writer-committed.jpg")
        guard committed == jpeg else { throw block("Writer committed bytes differ; no Photos import") }
        retainedWriterBytes = committed
        guard writer.claimForDelivery() else { throw block("Diagnostic writer claim failed") }
        receipt["writer_claim_succeeded"] = true; receipt["writer_committed_sha256"] = digest(committed)
        stage = "writer-committed"; phases.append(stage)
        let photos = XCUIApplication(bundleIdentifier: "com.apple.Photos")
        guard NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos").isEmpty else { throw block("Pre-existing Photos process; no launch or termination") }
        photos.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        _ = try remainingTime(1); photos.launch()
        let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        guard hosts.count == 1, let host = hosts.first, host.bundleURL?.path == "/System/Applications/Photos.app",
              host.executableURL?.path == "/System/Applications/Photos.app/Contents/MacOS/Photos" else { throw block("Unowned Photos process") }
        lifecyclePhotosPID = host.processIdentifier
        receipt["photos_identity"] = ["pid": lifecyclePhotosPID, "bundle": host.bundleURL!.path, "executable": host.executableURL!.path]
        try rejectLifecycleAlert(photos)
        let started = photos.buttons["Get Started"]
        if started.waitForExistence(timeout: try remainingTime(5)) {
            guard photos.buttons.matching(identifier: "Get Started").count == 1, started.isEnabled, started.isHittable else { throw block("Ambiguous first-use action") }
            try deadlineClick(started)
        }
        let empty = photos.staticTexts["_NS:99"]
        guard empty.waitForExistence(timeout: try remainingTime(10)), empty.value as? String == "Welcome to Photos" else { throw block("Photos library not observed empty") }
        let assets = photos.collectionViews["photos_collection_view"].descendants(matching: .any).matching(identifier: "mediaKind_asset")
        guard assets.count == 0 else { throw block("Nonempty library; no import") }; receipt["initial_asset_count"] = 0
        try requireNoSheet(photos); try importFixture(destination, into: photos)
        guard assets.firstMatch.waitForExistence(timeout: try remainingTime(20)), assets.count == 1, assets.firstMatch.isHittable else { throw block("Import did not produce one asset; no retry") }
        lifecycleAssetLabel = assets.firstMatch.label
        guard !lifecycleAssetLabel.isEmpty, lifecycleAssetLabel.utf8.count <= 300 else { throw block("Unbounded imported label") }
        receipt["asset_label"] = lifecycleAssetLabel; receipt["imported_asset_count"] = 1
        guard try readBoundedOwnedFile(destination, maximumBytes: 65_536) == committed else { throw block("Committed file changed during import") }
        writer.completeDelivery()
        let drained = expectation(description: "Diagnostic writer queue drained after completeDelivery")
        PhotosOutputWrite.afterPendingWorkForTesting { drained.fulfill() }
        wait(for: [drained], timeout: try remainingTime(5))
        receipt["writer_reservation_completed"] = true
        try deadlineClick(assets.firstMatch, twice: true); try guardAsset(photos)
        stage = "imported"; phases.append(stage)
        let original = try exportOwned("original", in: photos, original: true)
        guard original == jpeg && original == committed else { throw block("Unmodified JPEG bytes differ; no PNG export") }
        _ = try checkedJPEG(original)
        receipt["unmodified_original_sha256"] = digest(original); try guardAsset(photos)
        stage = "original-exported"; phases.append(stage); lifecycleControls.removeAll()
        let exported = try exportOwned("saved", in: photos, original: false)
        let raster = try lifecycleRaster(exported, expectedFormat: UTType.png.identifier)
        images["photos-roundtrip.png"]?["rgba_sha256"] = digest(raster.rgba)
        try guardAsset(photos); try verifySourcesAndBuild()
        let delta = try maximumDelta(raster.rgba, expected.raster.rgba)
        receipt["png_rgba_sha256"] = digest(raster.rgba); receipt["max_channel_delta"] = delta
        receipt["pixel_contract_passed"] = delta <= 2; receipt["historical_rgba_equal"] = raster.rgba == history.rgba
        stage = "png-exported"; phases.append(stage); receipt["complete"] = true
        if delta > 2 { throw block("ROUNDTRIP_PNG_PIXEL_GATE") }
    }
    private func value(_ key: String) throws -> String { try XCTUnwrap(context[key] as? String) }
    private func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
    private func verifySourcesAndBuild() throws {
        _ = try remainingTime(1)
        let root = URL(fileURLWithPath: try value("repository_root")).standardizedFileURL
        for (name, rel) in [("test_source", "Diagnostics/MacPhotosRoundtripTests.swift"), ("writer_source", "CelluloidPhotoExtension/PhotosOutputWrite.swift"), ("script", "Scripts/mac_photos_roundtrip.py")] {
            let path = try value(name + "_path")
            guard path == root.appendingPathComponent(rel).path,
                  try digest(boundedRegularBytes(URL(fileURLWithPath: path), maximumBytes: 2 * 1024 * 1024)) == value(name + "_sha256") else { throw block("Changed source binding") }
        }
        let builds = try XCTUnwrap(context["build_identity"] as? [String: [String: Any]])
        guard Set(builds.keys) == Set(["app", "extension", "extension_debug_dylib", "test"]) else { throw block("Build identity set") }
        guard Bundle(for: Self.self).executableURL?.standardizedFileURL.path == builds["test"]?["path"] as? String else { throw block("Actual diagnostic test executable mismatch") }
        for row in builds.values {
            let url = URL(fileURLWithPath: try XCTUnwrap(row["path"] as? String))
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            guard url.standardizedFileURL == url.resolvingSymlinksInPath(), attributes[.type] as? FileAttributeType == .typeRegular,
                  let count = attributes[.size] as? Int, count > 0, count <= 64 * 1024 * 1024, count == row["bytes"] as? Int else { throw block("Build file identity/size") }
            guard digest(try boundedRegularBytes(url, maximumBytes: 64 * 1024 * 1024)) == row["sha256"] as? String else { throw block("Build bytes changed") }
        }
    }
    @MainActor private func guardAsset(_ photos: XCUIApplication) throws {
        _ = try remainingTime(1)
        let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
        guard hosts.count == 1, hosts[0].processIdentifier == lifecyclePhotosPID,
              hosts[0].bundleURL?.path == "/System/Applications/Photos.app",
              hosts[0].executableURL?.path == "/System/Applications/Photos.app/Contents/MacOS/Photos" else { throw block("Photos process changed") }
        try soleAsset(in: photos, assetLabel: lifecycleAssetLabel)
    }
    private func retainRaw(_ bytes: Data, name: String) throws {
        guard ["writer-committed.jpg", "photos-original.jpg", "photos-roundtrip.png"].contains(name), images[name] == nil,
              !bytes.isEmpty, bytes.count <= 65_536, observedRawBytes + bytes.count <= 131_072 else { throw block("Raw boundary evidence cap/name") }
        observedRawBytes += bytes.count; images[name] = ["bytes": bytes.count, "sha256": digest(bytes)]
        let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: name.hasSuffix("png") ? UTType.png.identifier : UTType.jpeg.identifier)
        attachment.name = "celluloid-roundtrip-" + name; attachment.lifetime = .keepAlways; add(attachment)
    }
    private func lifecycleReceipt(photosPID: pid_t) throws -> [String: Any] {
        ["control_catalog": lifecycleControlCatalog, "export_option_bindings": exportOptionBindings,
         "binary_states": exportBinaryStates, "single_photo_topologies": singlePhotoTopologies, "photos_pid": photosPID]
    }
    private func emitProof() throws {
        receipt["stage"] = stage; receipt["phases"] = phases; receipt["images"] = images
        receipt["case_elapsed_seconds"] = ProcessInfo.processInfo.systemUptime - testStarted
        receipt["control_catalog"] = lifecycleControlCatalog; receipt["export_option_bindings"] = exportOptionBindings
        receipt["binary_states"] = exportBinaryStates; receipt["single_photo_topologies"] = singlePhotoTopologies
        receipt["binary_scalar_self_tested"] = binaryScalarSelfTested
        receipt["srgb_icc_reference"] = lifecycleICC.map { $0 as Any } ?? NSNull()
        receipt["failure"] = firstFailure.map { $0 as Any } ?? NSNull()
        let bytes = try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys])
        guard !bytes.isEmpty, bytes.count <= 32_000 else { throw block("Receipt cap") }
        var envelope: [String: Any] = ["schema": "Celluloid.OwnedPhotosRoundtripProof.1", "context_sha256": contextHash,
            "bytes": bytes.count, "sha256": digest(bytes), "base64": bytes.base64EncodedString()]
        for key in ["source_sha", "test_source_sha256", "writer_source_sha256", "script_sha256"] { envelope[key] = try value(key) }
        print("MAC_PHOTOS_ROUNDTRIP_PROOF " + String(decoding: try JSONSerialization.data(withJSONObject: envelope, options: [.sortedKeys]), as: UTF8.self))
    }
    private func block(_ reason: String, operation: [String: Any]? = nil) -> NSError {
        if firstFailure == nil { firstFailure = String(reason.prefix(1800)) }
        print("ROUNDTRIP_BLOCKED stage=" + stage + " reason=" + reason)
        return NSError(domain: "Celluloid.OwnedPhotosRoundtrip", code: 1, userInfo: [NSLocalizedDescriptionKey: reason])
    }

    @MainActor private func importFixture(_ fixture: URL, into photos: XCUIApplication) throws {
        guard fixture == retainedFixtureURL, fixture.lastPathComponent == Self.jpegFilename else { throw block("Unknown import input") }
        try verifyWriterDirectory(empty: false)
        guard try readBoundedOwnedFile(fixture, maximumBytes: 65_536) == XCTUnwrap(retainedWriterBytes) else { throw block("Writer file changed before import UI") }
        try requireNoSheet(photos)
        try openTopMenu("File", in: photos)
        let menu = try uniqueOpenMenu(photos.menuBarItems.matching(NSPredicate(format: "title == %@", "File")), description: "File")
        _ = try lifecycleControl(menu.children(matching: .menuItem).matching(identifier: "_NS:1096"), scope: "File/Import", role: "MenuItem")
        try lifecycleWait(photos, seconds: 10, description: "Import panel absent") { photos.sheets.count > 0 }
        let initial = try destinationPanel(in: photos)
        guard initial.go == nil else { throw block("Unexpected import child sheet") }
        let label = initial.panel.label
        try rejectLifecycleAlert(photos)
        try deadlineKey(initial.panel, "g", modifierFlags: [.command, .shift])
        try lifecycleWait(photos, seconds: 10, description: "Import Go to Folder absent") {
            initial.panel.children(matching: .sheet).matching(identifier: "GoToWindow").count > 0
        }
        let input = try destinationPathField(in: photos, panelLabel: label)
        try rejectLifecycleAlert(photos); try deadlineClick(input.element)
        _ = try destinationPathField(in: photos, panelLabel: label)
        try rejectLifecycleAlert(photos); try deadlineKey(input.element, "a", modifierFlags: .command)
        _ = try destinationPathField(in: photos, panelLabel: label)
        try rejectLifecycleAlert(photos); try deadlineText(input.element, fixture.path)
        let ready = try destinationPathField(in: photos, panelLabel: label, expected: fixture.path)
        _ = try retainLifecycleControl(ready.row)
        try rejectLifecycleAlert(photos); try deadlineKey(ready.element, XCUIKeyboardKey.return, modifierFlags: [])
        try lifecycleWait(photos, seconds: 10, description: "Import Go to Folder did not dismiss") { !ready.go.exists }
        let selected = try destinationPanel(in: photos)
        guard selected.go == nil, selected.panel.label == label else { throw block("Import panel changed after path readback") }
        // New exact guard, deliberately unqualified until its first native observation:
        // one selected file cell in this known panel, carrying this exact filename.
        let cells = selected.panel.descendants(matching: .cell).matching(NSPredicate(format: "label == %@ OR title == %@ OR value == %@", Self.jpegFilename, Self.jpegFilename, Self.jpegFilename))
        let count = cells.count
        let allCells = selected.panel.descendants(matching: .cell)
        let allCount = allCells.count
        guard allCount > 0, allCount <= 128 else { throw block("Unbounded import file-cell inventory") }
        let selectedCells = allCells.allElementsBoundByIndex.filter { $0.isSelected }
        receipt["import_selection"] = ["panel_identifier": selected.panel.identifier, "panel_label": label,
            "full_path_readback": fixture.path, "filename": Self.jpegFilename, "file_cell_count": count,
            "all_cell_count": allCount, "total_selected_cell_count": selectedCells.count,
            "selected": count == 1 && cells.element(boundBy: 0).isSelected,
            "guard_native_reachability_previously_qualified": false]
        guard count == 1, selectedCells.count == 1, cells.element(boundBy: 0).isSelected else {
            try observeOwnedImportPanel(photos, fixture: fixture, panelLabel: label)
            throw block("Owned import filename not uniquely selected; no import action")
        }
        let confirm = selected.panel.descendants(matching: .button).matching(identifier: "OKButton")
        _ = try lifecycleControl(confirm, scope: "OwnedImportPanel", role: "Button", click: false)
        try rejectLifecycleAlert(photos)
        let fresh = try destinationPanel(in: photos)
        guard fresh.go == nil, fresh.panel.label == label, cells.count == 1, cells.element(boundBy: 0).isSelected,
              allCells.count == allCount, allCells.allElementsBoundByIndex.filter({ $0.isSelected }).count == 1 else { throw block("Import selection changed before confirmation") }
        try verifyWriterDirectory(empty: false)
        guard try readBoundedOwnedFile(fixture, maximumBytes: 65_536) == XCTUnwrap(retainedWriterBytes) else { throw block("Writer file changed before import confirmation") }
        _ = try lifecycleControl(confirm, scope: "OwnedImportPanel", role: "Button")
        try lifecycleWait(photos, seconds: 20, description: "Single-file import did not finish") { photos.sheets.count == 0 }
        try requireNoSheet(photos)
        guard photos.buttons["Review for Import"].exists == false, photos.buttons["Import All New Photos"].exists == false else { throw block("Unknown import review route; no secondary action") }
    }

    @MainActor private func observeOwnedImportPanel(_ photos: XCUIApplication, fixture: URL, panelLabel: String) throws {
        // Evidence only for this existing failed guard. No click, key, retry or matching fallback.
        guard receipt["import_observation"] == nil, receipt["initial_asset_count"] as? Int == 0,
              phases == ["reference", "writer-committed"], fixture == retainedFixtureURL,
              fixture.lastPathComponent == Self.jpegFilename else { throw block("Unbound import observation") }
        try verifyWriterDirectory(empty: false)
        let committed = try XCTUnwrap(retainedWriterBytes)
        guard try readBoundedOwnedFile(fixture, maximumBytes: 65_536) == committed else { throw block("Import observation writer bytes changed") }
        func requireSamePhotos() throws {
            _ = try remainingTime(1)
            let hosts = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Photos")
            guard hosts.count == 1, hosts[0].processIdentifier == lifecyclePhotosPID,
                  hosts[0].bundleURL?.path == "/System/Applications/Photos.app",
                  hosts[0].executableURL?.path == "/System/Applications/Photos.app/Contents/MacOS/Photos" else { throw block("Import observation Photos identity changed") }
        }
        try requireSamePhotos()
        try rejectLifecycleAlert(photos)
        let bound = try destinationPanel(in: photos)
        guard bound.go == nil, bound.panel.identifier == "open-panel", bound.panel.label == panelLabel else { throw block("Import observation panel changed") }
        _ = try remainingTime(1)
        let snapshot = try bound.panel.snapshot()
        try requireSamePhotos()
        guard snapshot.elementType == .sheet, snapshot.identifier == "open-panel", snapshot.label == panelLabel,
              snapshot.frame.width > 0, snapshot.frame.height > 0,
              snapshot.frame.width <= 2048, snapshot.frame.height <= 2048 else { throw block("Import observation panel bounds") }
        var nodes: [[Any]] = []
        func clipped(_ value: String) -> (String, Bool) { (String(value.prefix(80)), value.count > 80) }
        func visit(_ node: XCUIElementSnapshot, parent: Int, depth: Int) throws {
            guard nodes.count < 256, depth <= 14 else { throw block("Import observation AX node/depth cap") }
            let index = nodes.count
            let scalar: String
            if let text = node.value as? String { scalar = text }
            else if let number = node.value as? NSNumber { scalar = number.stringValue }
            else if node.value == nil { scalar = "" }
            else { scalar = "<non-scalar:" + String(String(describing: type(of: node.value!)).prefix(40)) + ">" }
            let values = [node.identifier, node.label, node.title, scalar].map(clipped)
            let frame = [node.frame.minX, node.frame.minY, node.frame.width, node.frame.height].map(Double.init)
            guard frame.allSatisfy({ $0.isFinite }) else { throw block("Import observation AX geometry") }
            let role = node.elementType == .cell ? "cell" : node.elementType == .tableRow ? "row" : node.elementType == .staticText ? "staticText" : node.elementType == .textField ? "textField" : node.elementType == .sheet ? "sheet" : "other:\(node.elementType.rawValue)"
            nodes.append([index, parent, role, values[0].0, values[1].0,
                          values[2].0, values[3].0, node.isSelected, frame, values.map { $0.1 }])
            for child in node.children { try visit(child, parent: index, depth: depth + 1) }
        }
        try visit(snapshot, parent: -1, depth: 0)
        let ax: [String: Any] = ["schema": "Celluloid.OwnedImportAX.1", "source_sha": try value("source_sha"),
            "context_sha256": contextHash, "photos_pid": lifecyclePhotosPID, "initial_asset_count": 0,
            "fixture_path": fixture.path, "fixture_sha256": digest(committed), "panel_identifier": "open-panel",
            "panel_label": panelLabel, "columns": ["index", "parent", "role", "identifier", "label", "title", "value", "selected", "frame", "truncated_attributes"],
            "nodes": nodes, "selection_guard_unchanged": true, "no_import_confirmation": true]
        let axBytes = try JSONSerialization.data(withJSONObject: ax, options: [.sortedKeys])
        guard !axBytes.isEmpty, axBytes.count <= 32_768 else { throw block("Import observation AX byte cap") }
        try requireSamePhotos()
        try rejectLifecycleAlert(photos)
        let shotPanel = try destinationPanel(in: photos)
        guard shotPanel.go == nil, shotPanel.panel.identifier == "open-panel", shotPanel.panel.label == panelLabel,
              shotPanel.panel.frame == snapshot.frame else { throw block("Import observation screenshot panel changed") }
        _ = try remainingTime(1)
        let shot = shotPanel.panel.screenshot() // This element only; never the screen/application/window.
        try requireSamePhotos()
        let source = try XCTUnwrap(shot.image.cgImage(forProposedRect: nil, context: nil, hints: nil))
        guard source.width > 0, source.height > 0, source.width <= 4096, source.height <= 4096 else { throw block("Import observation screenshot pixel cap") }
        let scale = min(1, 640.0 / Double(max(source.width, source.height)))
        let width = max(1, Int(Double(source.width) * scale)), height = max(1, Int(Double(source.height) * scale))
        let color = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let profile = try XCTUnwrap(color.copyICCData()) as Data
        guard profile.count >= 128, profile.count <= 4096 else { throw block("Import observation preview profile cap") }
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: color, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        bitmap.interpolationQuality = .high; bitmap.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        let png = NSMutableData()
        let encoder = try XCTUnwrap(CGImageDestinationCreateWithData(png, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(encoder, try XCTUnwrap(bitmap.makeImage()), nil)
        guard CGImageDestinationFinalize(encoder), png.length > 0, png.length <= 65_536,
              observedRawBytes + axBytes.count + png.length <= 131_072 else { throw block("Import observation screenshot/aggregate cap") }
        try requireSamePhotos()
        try rejectLifecycleAlert(photos)
        let finalPanel = try destinationPanel(in: photos)
        guard finalPanel.go == nil, finalPanel.panel.identifier == "open-panel", finalPanel.panel.label == panelLabel,
              finalPanel.panel.frame == snapshot.frame else { throw block("Import observation final panel changed") }
        try verifyWriterDirectory(empty: false)
        guard try readBoundedOwnedFile(fixture, maximumBytes: 65_536) == committed else { throw block("Import observation final writer bytes changed") }
        let imageBytes = png as Data
        for (name, bytes, type) in [("import-ax.json", axBytes, UTType.json.identifier), ("import-panel.png", imageBytes, UTType.png.identifier)] {
            let attachment = XCTAttachment(data: bytes, uniformTypeIdentifier: type)
            attachment.name = "celluloid-roundtrip-" + name; attachment.lifetime = .keepAlways; add(attachment)
        }
        observedRawBytes += axBytes.count + imageBytes.count
        receipt["import_observation"] = ["schema": "Celluloid.OwnedImportObservation.1", "complete": true,
            "scope": "owned-open-panel-only", "source_sha": try value("source_sha"), "context_sha256": contextHash,
            "photos_pid": lifecyclePhotosPID, "initial_asset_count": 0, "fixture_sha256": digest(committed),
            "panel_identifier": "open-panel", "panel_label": panelLabel, "selection_guard_unchanged": true, "no_import_confirmation": true,
            "ax": ["bytes": axBytes.count, "sha256": digest(axBytes), "node_count": nodes.count],
            "screenshot": ["bytes": imageBytes.count, "sha256": digest(imageBytes), "type": UTType.png.identifier,
                "width": width, "height": height, "source_width": source.width, "source_height": source.height,
                "resized_panel_preview": true, "maximum_side": 640,
                "srgb_icc_reference": ["bytes": profile.count, "sha256": digest(profile)]]]
    }

    private func verifyWriterDirectory(empty: Bool) throws {
        _ = try remainingTime(1)
        let root = try XCTUnwrap(writerDirectory), before = try XCTUnwrap(writerDirectoryState)
        var current = stat()
        guard root == root.resolvingSymlinksInPath(), root.path.withCString({ lstat($0, &current) }) == 0,
              current.st_mode & S_IFMT == S_IFDIR, current.st_uid == getuid(),
              current.st_dev == before.st_dev, current.st_ino == before.st_ino,
              current.st_mode == before.st_mode else { throw block("Owned writer directory identity changed") }
        let members = try FileManager.default.contentsOfDirectory(atPath: root.path)
        guard members == (empty ? [] : [Self.jpegFilename]) else { throw block("Unexpected writer directory member") }
    }

    @MainActor private func editorMatches(in photos: XCUIApplication) -> XCUIElementQuery {
        photos.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Celluloid photo editor"))
    }

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
        guard ["saved", "original"].contains(directory.lastPathComponent),
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
        guard ["saved", "original"].contains(name), lifecycleExports[name] == nil else { throw block("Unexpected/repeated export phase") }
        if lifecycleRoot == nil {
            let temporary = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
            let root = temporary.appendingPathComponent("CelluloidPhotosLifecycle-" + UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            for child in ["saved", "original"] {
                try FileManager.default.createDirectory(at: root.appendingPathComponent(child, isDirectory: true), withIntermediateDirectories: false)
            }
            var rootState = stat()
            guard root.path.withCString({ lstat($0, &rootState) }) == 0, rootState.st_mode & S_IFMT == S_IFDIR, rootState.st_uid == getuid() else { throw block("Unowned new export root") }
            exportRootState = rootState
            for child in ["saved", "original"] {
                var state = stat()
                guard root.appendingPathComponent(child).path.withCString({ lstat($0, &state) }) == 0, state.st_mode & S_IFMT == S_IFDIR, state.st_uid == getuid() else { throw block("Unowned new export directory") }
                exportDirectoryStates[child] = state
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
        var rootState = stat()
        let originalRoot = try XCTUnwrap(exportRootState)
        guard root.path.withCString({ lstat($0, &rootState) }) == 0, rootState.st_mode & S_IFMT == S_IFDIR, rootState.st_uid == getuid(), rootState.st_dev == originalRoot.st_dev, rootState.st_ino == originalRoot.st_ino, rootState.st_mode == originalRoot.st_mode else { throw block("Export root owner/identity changed") }
        let members = try FileManager.default.contentsOfDirectory(atPath: root.path)
        guard Set(members) == Set(["saved", "original"]) else { throw block("Unexpected owned export root member") }
        for child in members {
            let directory = root.appendingPathComponent(child, isDirectory: true)
            var state = stat()
            let original = try XCTUnwrap(exportDirectoryStates[child])
            guard directory.path.withCString({ lstat($0, &state) }) == 0, state.st_mode & S_IFMT == S_IFDIR, state.st_uid == getuid(), state.st_dev == original.st_dev, state.st_ino == original.st_ino, state.st_mode == original.st_mode else { throw block("Export directory owner/identity changed") }
            let attributes = try FileManager.default.attributesOfItem(atPath: directory.path)
            guard attributes[.type] as? FileAttributeType == .typeDirectory,
                  directory.standardizedFileURL == directory.resolvingSymlinksInPath() else { throw block("Symlink/non-directory in owned export root") }
            let files = try FileManager.default.contentsOfDirectory(atPath: directory.path)
            guard files == (lifecycleExports[child] == nil ? [] : [child == "original" ? Self.jpegFilename : Self.fixtureFilename]) else { throw block("Unexpected or stale owned export member") }
            if !files.isEmpty {
                let file = directory.appendingPathComponent(child == "original" ? Self.jpegFilename : Self.fixtureFilename)
                var status = stat()
                guard file.path.withCString({ lstat($0, &status) }) == 0,
                      (status.st_mode & S_IFMT) == S_IFREG, status.st_uid == getuid(), status.st_nlink == 1,
                      status.st_size > 0, status.st_size <= 16 * 1024 * 1024 else { throw block("Owned export tree contains nonregular/linked/oversized file") }
            }
        }
    }

    private func boundedRegularBytes(_ canonical: URL, maximumBytes: Int) throws -> Data {
        _ = try remainingTime(1)
        let parent = canonical.deletingLastPathComponent()
        guard maximumBytes > 0, maximumBytes <= 64 * 1024 * 1024, canonical == canonical.standardizedFileURL, parent == parent.resolvingSymlinksInPath() else { throw block("Unowned bounded read path/cap") }
        let directoryFD = parent.path.withCString { Darwin.open($0, O_RDONLY | O_DIRECTORY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW) }
        guard directoryFD >= 0 else { throw block("Owned parent directory denied; no alternate location", operation: ["errno": errno]) }
        defer { Darwin.close(directoryFD) }
        var parentBefore = stat()
        guard fstat(directoryFD, &parentBefore) == 0, (parentBefore.st_mode & S_IFMT) == S_IFDIR, parentBefore.st_uid == getuid() else { throw block("Owned export parent changed") }
        let descriptor = canonical.lastPathComponent.withCString { openat(directoryFD, $0, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW) }
        guard descriptor >= 0 else { throw block("Owned file read denied or symlink; no alternate path", operation: ["filename": canonical.lastPathComponent, "errno": errno]) }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        var before = stat()
        guard fstat(descriptor, &before) == 0, (before.st_mode & S_IFMT) == S_IFREG,
              before.st_uid == getuid(), before.st_nlink == 1, before.st_size > 0, before.st_size <= Int64(maximumBytes) else {
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
              after.st_uid == getuid(), pathAfter.st_uid == getuid(), parentAfter.st_uid == getuid(),
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

    private func readBoundedOwnedFile(_ file: URL, maximumBytes: Int = 16 * 1024 * 1024) throws -> Data {
        _ = try remainingTime(1)
        let canonical = file.standardizedFileURL
        let parent = canonical.deletingLastPathComponent()
        let ownedSource = retainedFixtureURL?.standardizedFileURL == canonical || inputURLs.contains(canonical)
        let ownedExport = lifecycleRoot.map { root in
            ["saved", "original"].contains { phase in
                root.appendingPathComponent(phase).appendingPathComponent(phase == "original" ? Self.jpegFilename : Self.fixtureFilename) == canonical
            }
        } ?? false
        guard ownedSource || ownedExport, maximumBytes > 0, maximumBytes <= 16 * 1024 * 1024,
              parent == parent.resolvingSymlinksInPath(), ([Self.fixtureFilename, Self.jpegFilename].contains(canonical.lastPathComponent) || inputURLs.contains(canonical)) else {
            throw block("File is not a fixed owned source/export path")
        }
        return try boundedRegularBytes(canonical, maximumBytes: maximumBytes)
    }

    private func png(_ image: CGImage) throws -> Data {
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image,
            [kCGImagePropertyPNGDictionary: [kCGImagePropertyPNGInterlaceType: 0]] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw block("Control PNG encode failed") }
        return data as Data
    }

    private func decodedJPEG(_ bytes: Data) throws -> LifecycleRaster {
        try lifecycleRaster(png(checkedJPEG(bytes)), expectedFormat: UTType.png.identifier)
    }

    private func checkedJPEG(_ bytes: Data) throws -> CGImage {
        guard !bytes.isEmpty, bytes.count <= 128 * 1024 else { throw block("Control JPEG size bound failed") }
        let source = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        let srgb = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let profile = try XCTUnwrap(image.colorSpace?.copyICCData()) as Data
        let expectedProfile = try XCTUnwrap(srgb.copyICCData()) as Data
        guard CGImageSourceGetCount(source) == 1, CGImageSourceGetType(source) as String? == UTType.jpeg.identifier,
              properties[kCGImagePropertyPixelWidth] as? Int == 1200,
              properties[kCGImagePropertyPixelHeight] as? Int == 800,
              (properties[kCGImagePropertyOrientation] as? Int ?? 1) == 1,
              properties[kCGImagePropertyDepth] as? Int == 8,
              properties[kCGImagePropertyProfileName] as? String != nil,
              image.width == 1200, image.height == 800, image.bitsPerComponent == 8,
              image.colorSpace?.model == .rgb, profile == expectedProfile else {
            throw block("Control JPEG format/dimensions/orientation/depth/sRGB mismatch")
        }
        return image
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
    }

    private func bitmap() throws -> CGContext {
        try XCTUnwrap(CGContext(data: nil, width: 1200, height: 800, bitsPerComponent: 8, bytesPerRow: 1200 * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue))
    }

    private func lifecycleRaster(_ data: Data, expectedFormat: String) throws -> LifecycleRaster {
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

    private func maximumDelta(_ lhs: Data, _ rhs: Data) throws -> Int {
        guard lhs.count == 1200 * 800 * 4, lhs.count == rhs.count else { throw block("Pixel comparison size mismatch") }
        var maximum = 0
        for index in lhs.indices { maximum = max(maximum, abs(Int(lhs[index]) - Int(rhs[index]))) }
        return maximum
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

    @MainActor private func exportOwned(_ name: String, in photos: XCUIApplication, original: Bool) throws -> Data {
        _ = try remainingTime(1)
        guard original == (name == "original") else { throw block("Mismatched raw export/image binding") }
        try requireNoSheet(photos)
        let directory = try ownedExportDirectory(name)
        let file = directory.appendingPathComponent(original ? Self.jpegFilename : Self.fixtureFilename)
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
        guard try FileManager.default.contentsOfDirectory(atPath: directory.path) == [original ? Self.jpegFilename : Self.fixtureFilename] else { throw block("Export produced extra files or wrong filename") }
        let bytes = try readBoundedOwnedFile(file, maximumBytes: 65_536)
        let retained = original ? "photos-original.jpg" : "photos-roundtrip.png"
        try retainRaw(bytes, name: retained)
        lifecycleExports[name] = ["image": retained, "bytes": bytes.count, "sha256": digest(bytes)]
        return bytes
    }
}
