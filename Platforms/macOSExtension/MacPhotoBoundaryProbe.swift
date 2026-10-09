#if DEBUG && CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE
import AppKit
import SwiftUI
import CryptoKit
import Dispatch
import Combine
import Darwin

/// Single-use, explicitly armed owned-synthetic diagnostic. The lease is placed
/// in this Debug product's Info.plist by the source-admitted host context helper.
/// Nothing is captured from an ordinary build or merely by opening a photograph.
@MainActor final class MacPhotoBoundaryProbe: ObservableObject {
    // Byte-stable accessibility protocol marker; never a localized UI label.
    static let armReceiptMarker = "CELLULOID_OWNED_PHOTOS_BOUNDARY_ARM_V1"
    static let fixtureSHA = "6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772"
    static let bundleID = "Mango.Celluloid.CelluloidPhotoExtension"
    @Published var token = ""
    @Published private(set) var receipt = ""
    private var used = false
    private var armed: Arm?
    private var recipeObservation: AnyCancellable?
    private let lease: [String: String]?
    var enabled: Bool { lease != nil && !used }

    init() {
        let candidate = Bundle.main.object(forInfoDictionaryKey: "CelluloidOwnedPhotosBoundaryLease") as? [String: String]
        if Bundle.main.bundleIdentifier == Self.bundleID, let candidate, Self.validLease(candidate) {
            lease = candidate
        } else { lease = nil }
    }
    static func validLease(_ value: [String: String]) -> Bool {
        guard Set(value.keys) == ["schema", "source_sha", "source_tree", "run_id", "run_attempt", "fixture_sha256", "nonce", "raw_cap"],
              value["schema"] == "Celluloid.OwnedPhotosBoundaryLease.1",
              value["run_attempt"] == "1", value["fixture_sha256"] == fixtureSHA,
              value["raw_cap"] == "131072", let run = value["run_id"],
              run.range(of: "^[1-9][0-9]{0,19}$", options: .regularExpression) != nil else { return false }
        return [("source_sha", 40), ("source_tree", 40), ("nonce", 64)].allSatisfy { key, count in
            guard let text = value[key] else { return false }
            return text.range(of: "^[0-9a-f]{\(count)}$", options: .regularExpression) != nil
        }
    }
    func arm(session: MacPhotoSession, identity: MacPhotoSelfIdentity) {
        // One submitted token, no retry/re-arm on the same product/controller.
        guard enabled, let lease else { return }
        used = true
        defer { token = "" }
        guard token == lease["nonce"], let raw = identity.readyValue(for: session),
              let generation = identity.generation, let snapshot = session.snapshot,
              session.changed, snapshot.adjustment.filter == .fade, snapshot.adjustment.layers.isEmpty,
              snapshot.source.pixelWidth == 1200, snapshot.source.pixelHeight == 800,
              !snapshot.bytes.isEmpty, snapshot.bytes.count <= 65_536,
              let object = try? JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any],
              object["generation"] as? String == generation.uuidString,
              object["pid"] as? Int == Int(ProcessInfo.processInfo.processIdentifier),
              object["bundle_identifier"] as? String == Self.bundleID,
              let recipe = Self.recipe(snapshot) else { return }
        let row: [String: Any] = ["schema": "Celluloid.OwnedPhotosBoundaryArm.1", "lease": lease,
            "identity_sha256": Self.hash(Data(raw.utf8)), "generation": generation.uuidString,
            "input_sha256": Self.hash(snapshot.bytes), "recipe_sha256": Self.hash(recipe),
            "source_id": snapshot.source.id.uuidString]
        guard let data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]), data.count <= 4096 else { return }
        armed = Arm(lease: lease, identity: raw, row: row, armedAt: ProcessInfo.processInfo.systemUptime)
        receipt = String(decoding: data, as: UTF8.self)
        recipeObservation = session.$adjustment.dropFirst().sink { [weak self] _ in self?.cancel() }
    }
    func consume(identity: String?) -> Arm? {
        defer { armed = nil; receipt = ""; recipeObservation = nil }
        guard let armed, identity == armed.identity,
              ProcessInfo.processInfo.systemUptime - armed.armedAt <= 120 else { return nil }
        return armed
    }
    func cancel() { armed = nil; receipt = ""; token = ""; recipeObservation = nil }
    private static func recipe(_ snapshot: MacPhotoSnapshot) -> Data? {
        guard snapshot.adjustment.filter == .fade, snapshot.adjustment.layers.isEmpty,
              let canvas = snapshot.adjustment.referenceCanvas else { return nil }
        return try? JSONSerialization.data(withJSONObject: ["filter": "Fade", "layers": 0,
            "canvas_width": Double(canvas.width), "canvas_height": Double(canvas.height)], options: [.sortedKeys])
    }
    fileprivate static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    @MainActor struct Arm {
        let lease: [String: String]
        let identity: String
        let row: [String: Any]
        let armedAt: TimeInterval

        /// Best effort before writer.start receives THIS jpeg. This records an
        /// intended submission, never a claim that the writer or Photos accepted it.
        /// Extra synchronous IO is diagnostic-only, with checked 500ms time and
        /// byte limits. A regular-file syscall is not a hard-real-time operation.
        /// Failure returns normally and cannot suppress the production callback.
        func captureIntended(snapshot: MacPhotoSnapshot, jpeg: Data, orientation: Int32) {
            do {
                let started = DispatchTime.now().uptimeNanoseconds
                func check() throws {
                    guard !Task.isCancelled,
                          DispatchTime.now().uptimeNanoseconds - started <= 500_000_000 else { throw Failure.budget }
                }
                try check()
                guard ProcessInfo.processInfo.systemUptime - armedAt <= 120,
                      orientation == 1, snapshot.source.pixelWidth == 1200, snapshot.source.pixelHeight == 800,
                      !snapshot.bytes.isEmpty, snapshot.bytes.count <= 65_536,
                      !jpeg.isEmpty, jpeg.count <= 65_536, jpeg.starts(with: [0xff, 0xd8, 0xff]),
                      snapshot.source.id.uuidString == row["source_id"] as? String,
                      Self.probeHash(snapshot.bytes) == row["input_sha256"] as? String,
                      let recipe = MacPhotoBoundaryProbe.recipe(snapshot),
                      Self.probeHash(recipe) == row["recipe_sha256"] as? String,
                      let nonce = lease["nonce"], let generation = row["generation"] as? String else { throw Failure.binding }
                try check()
                // The sandbox's own home is the only root; no path supplied by
                // the token, PhotoKit input, accessibility, or context is used.
                let home = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).standardizedFileURL
                guard home.path.hasSuffix("/Library/Containers/" + MacPhotoBoundaryProbe.bundleID + "/Data") else { throw Failure.binding }
                let root = try FD(open(home.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW))
                let library = try root.directory("Library", create: false)
                let caches = try library.directory("Caches", create: true)
                let owned = try caches.directory("CelluloidOwnedPhotosBoundary", create: true)
                // Each lease/generation can create its directory only once.
                let run = try owned.directory(nonce, create: true, exclusive: true)
                let folder = try run.directory(generation, create: true, exclusive: true)
                try check()
                try folder.write("input.bytes", data: snapshot.bytes, check: check)
                try folder.write("intended.jpg", data: jpeg, check: check)
                var capture = row
                capture["schema"] = "Celluloid.OwnedPhotosBoundaryCapture.1"
                capture["identity_raw"] = identity
                capture["capture_stage"] = "before-writer-start-intended-same-jpeg"
                capture["writer_claim_observed"] = false
                capture["photos_acceptance_observed"] = false
                capture["performance_acceptance"] = false
                capture["orientation"] = Int(orientation)
                capture["input_bytes"] = snapshot.bytes.count
                capture["intended_jpeg_bytes"] = jpeg.count
                capture["intended_jpeg_sha256"] = Self.probeHash(jpeg)
                capture["checked_budget_ms"] = 500
                capture["hard_realtime_bound"] = false
                capture["elapsed_before_receipt_ms"] = Double(DispatchTime.now().uptimeNanoseconds - started) / 1_000_000
                let receipt = try JSONSerialization.data(withJSONObject: capture, options: [.sortedKeys, .withoutEscapingSlashes])
                guard receipt.count <= 8192 else { throw Failure.budget }
                try check()
                try folder.publishReceipt(receipt, check: check) // successful exclusive rename is the endpoint
            } catch {
                // No session.report, throw, writer mutation, callback or retry.
                // Partial files have no valid final receipt and are never evidence.
                return
            }
        }
        private static func probeHash(_ data: Data) -> String { MacPhotoBoundaryProbe.hash(data) }
    }
    private enum Failure: Error { case budget, binding, file }
    private final class FD {
        let value: Int32
        init(_ value: Int32) throws { guard value >= 0 else { throw Failure.file }; self.value = value }
        deinit { close(value) }
        func directory(_ name: String, create: Bool, exclusive: Bool = false) throws -> FD {
            if create {
                let result = mkdirat(value, name, 0o700)
                guard result == 0 || (!exclusive && errno == EEXIST) else { throw Failure.file }
            }
            let child = try FD(openat(value, name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW))
            var status = stat()
            guard fstat(child.value, &status) == 0, status.st_uid == getuid(), status.st_mode & mode_t(S_IFMT) == mode_t(S_IFDIR) else { throw Failure.file }
            return child
        }
        func publishReceipt(_ data: Data, check: () throws -> Void) throws {
            // A failed write/fstat/final budget check leaves only this fixed
            // pending file, which the reader never admits or follows.
            try write("capture.pending.json", data: data, check: check)
            try check()
            guard renameatx_np(value, "capture.pending.json", value, "capture.json", UInt32(RENAME_EXCL)) == 0 else {
                throw Failure.file
            }
            // Publication success is the endpoint. No post-publication check,
            // confirmation write, fallback, retry, or hard-real-time claim.
        }
        func write(_ name: String, data: Data, check: () throws -> Void) throws {
            try check()
            let file = try FD(openat(value, name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0o600))
            let count = data.withUnsafeBytes { Darwin.write(file.value, $0.baseAddress!, data.count) }
            guard count == data.count else { throw Failure.file }
            var status = stat()
            guard fstat(file.value, &status) == 0, status.st_nlink == 1,
                  status.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), status.st_size == off_t(data.count) else { throw Failure.file }
            try check()
        }
    }
}

struct MacPhotoBoundaryProbeView: View {
    @ObservedObject var probe: MacPhotoBoundaryProbe
    @ObservedObject var session: MacPhotoSession
    @ObservedObject var identity: MacPhotoSelfIdentity
    var body: some View {
        VStack {
            if probe.enabled {
                // This explicitly armed Debug-only operator surface is verbatim.
                TextField(text: $probe.token) {
                    Text(verbatim: "Owned synthetic diagnostic token")
                }
                    .accessibilityIdentifier("photos-extension.boundary-token")
                    .onSubmit { probe.arm(session: session, identity: identity) }
            }
            if !probe.receipt.isEmpty {
                MacPhotoBoundaryReceiptAccessibility(probe: probe).frame(width: 1, height: 1)
            }
        }
    }
}

/// The same live AppKit value pattern already used by the own-bundle identity.
/// This leaf observes only the current one-shot synthetic receipt and draws nothing.
struct MacPhotoBoundaryReceiptAccessibility: NSViewRepresentable {
    @ObservedObject var probe: MacPhotoBoundaryProbe
    func makeNSView(context: Context) -> MacPhotoBoundaryReceiptAccessibilityView {
        MacPhotoBoundaryReceiptAccessibilityView(frame: .zero)
    }
    func updateNSView(_ view: MacPhotoBoundaryReceiptAccessibilityView, context: Context) {
        view.probe = probe
        view.setAccessibilityRole(.staticText)
        view.setAccessibilityIdentifier("photos-extension.boundary-arm")
        view.setAccessibilityLabel(MacPhotoBoundaryProbe.armReceiptMarker)
        view.refreshAccessibility()
    }
    static func dismantleNSView(_ view: MacPhotoBoundaryReceiptAccessibilityView, coordinator: ()) {
        view.probe = nil
        view.refreshAccessibility()
    }
}

final class MacPhotoBoundaryReceiptAccessibilityView: NSView {
    weak var probe: MacPhotoBoundaryProbe?
    private var lastNotifiedValue: String?
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        refreshAccessibility()
    }
    func refreshAccessibility() {
        let next = currentValue
        guard next != lastNotifiedValue else { return }
        lastNotifiedValue = next
        NSAccessibility.post(element: superview ?? self, notification: .layoutChanged, userInfo: [.uiElements: [self]])
        if next != nil { NSAccessibility.post(element: self, notification: .valueChanged) }
    }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override var acceptsFirstResponder: Bool { false }
    override func isAccessibilityElement() -> Bool { currentValue != nil }
    override func accessibilityValue() -> Any? { currentValue }
    private var currentValue: String? {
        guard window != nil, !isHiddenOrHasHiddenAncestor, let probe, !probe.receipt.isEmpty else { return nil }
        return probe.receipt
    }
}
#endif
