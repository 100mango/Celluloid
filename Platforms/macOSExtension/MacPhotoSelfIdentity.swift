#if DEBUG
import AppKit
import SwiftUI
import CryptoKit
import Dispatch
import Darwin

/// A debug observation of this extension only. There is no path/PID/hash input,
/// environment override, process enumeration, helper executable or file output.
/// Failure deliberately produces no accessibility proof and never blocks editing.
@MainActor final class MacPhotoSelfIdentity: ObservableObject {
    @Published private(set) var value: String?
    private(set) var generation: UUID?
    private var captureTask: Task<String?, Never>?
    private var publicationTask: Task<Void, Never>?

    deinit { captureTask?.cancel(); publicationTask?.cancel() }

    // The controller calls this only from the real startContentEditing callback.
    func contentEditingStarted() {
        invalidate()
        let token = UUID()
        generation = token
        let worker = Task.detached(priority: .utility) {
            try? MacPhotoSelfIdentityCapture.observe(generation: token)
        }
        captureTask = worker
        publicationTask = Task { [weak self] in
            let observed = await worker.value
            guard !Task.isCancelled, let self, generation == token else { return }
            value = observed
            captureTask = nil; publicationTask = nil
        }
    }

    func invalidate() {
        // Clear synchronously, before cancellation can race with publication.
        generation = nil; value = nil
        captureTask?.cancel(); captureTask = nil
        publicationTask?.cancel(); publicationTask = nil
    }

    func readyValue(for session: MacPhotoSession) -> String? {
        guard generation != nil, session.editable, session.preview != nil,
              session.placeholder == nil, !session.loading, !session.rendering,
              !session.finishing, !session.readOnly, session.error == nil else { return nil }
        return value
    }
}

/// Fixed-name, descriptor-relative reads from the actual main extension bundle.
/// Each file is capped at 32 MiB, buffers at 64 KiB and the whole capture at ten
/// seconds of checked monotonic time. Regular-file I/O remains OS-scheduled.
/// All descriptors and path identities are rechecked after BOTH hashes finish.
enum MacPhotoSelfIdentityCapture {
    static let marker = "CELLULOID_EXTENSION_SELF_IDENTITY_V1"
    static let maximumJSONBytes = 8_192
    private static let bundleIdentifier = "Mango.Celluloid.CelluloidPhotoExtension"
    private static let executableName = "CelluloidMacPhotosExtension"
    private static let debugDylibName = "CelluloidMacPhotosExtension.debug.dylib"
    private static let maximumFileBytes = 32 * 1_024 * 1_024
    private static let maximumNanoseconds: UInt64 = 10_000_000_000
    private enum Failure: Error { case invalidOwnBundle, changedFile, invalidFile, budget, read }

    static func observe(generation: UUID) throws -> String {
        let started = DispatchTime.now().uptimeNanoseconds
        try check(started)
        let ownBundle = Bundle.main
        guard ownBundle.bundleIdentifier == bundleIdentifier,
              ownBundle.object(forInfoDictionaryKey: "CFBundleExecutable") as? String == executableName,
              let ownExecutable = ownBundle.executableURL else { throw Failure.invalidOwnBundle }
        let bundle = ownBundle.bundleURL.standardizedFileURL.resolvingSymlinksInPath()
        let executable = bundle.appendingPathComponent("Contents/MacOS/" + executableName)
        let debugDylib = bundle.appendingPathComponent("Contents/MacOS/" + debugDylibName)
        let pid = ProcessInfo.processInfo.processIdentifier
        guard bundle.isFileURL, bundle.lastPathComponent == executableName + ".appex",
              ownExecutable.isFileURL,
              ownExecutable.standardizedFileURL.resolvingSymlinksInPath() == executable,
              pid > 0, [bundle, executable, debugDylib].allSatisfy({ $0.path.utf8.count <= 2_048 })
        else { throw Failure.invalidOwnBundle }

        let root = try Descriptor(open(bundle.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW))
        let rootBefore = try root.snapshot(kind: mode_t(S_IFDIR))
        let contents = try Descriptor(openat(root.fd, "Contents", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW))
        let contentsBefore = try contents.snapshot(kind: mode_t(S_IFDIR))
        let macOS = try Descriptor(openat(contents.fd, "MacOS", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW))
        let macOSBefore = try macOS.snapshot(kind: mode_t(S_IFDIR))
        let executableFile = try Descriptor(openat(macOS.fd, executableName, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW))
        let executableBefore = try executableFile.snapshot(kind: mode_t(S_IFREG))
        let dylibFile = try Descriptor(openat(macOS.fd, debugDylibName, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW))
        let dylibBefore = try dylibFile.snapshot(kind: mode_t(S_IFREG))
        let executableHash = try digest(executableFile, expected: executableBefore, started: started)
        let dylibHash = try digest(dylibFile, expected: dylibBefore, started: started)
        try check(started)

        // Recheck descriptor metadata and the directory entries that named them.
        // No-follow opens plus these comparisons reject symlinks, replacements,
        // truncation, growth and observable same-size mutations during capture.
        guard try root.snapshot(kind: mode_t(S_IFDIR)) == rootBefore,
              try contents.snapshot(kind: mode_t(S_IFDIR)) == contentsBefore,
              try macOS.snapshot(kind: mode_t(S_IFDIR)) == macOSBefore,
              try executableFile.snapshot(kind: mode_t(S_IFREG)) == executableBefore,
              try dylibFile.snapshot(kind: mode_t(S_IFREG)) == dylibBefore else { throw Failure.changedFile }
        try verifyEntry(parent: AT_FDCWD, name: bundle.path, expected: rootBefore)
        try verifyEntry(parent: root.fd, name: "Contents", expected: contentsBefore)
        try verifyEntry(parent: contents.fd, name: "MacOS", expected: macOSBefore)
        try verifyEntry(parent: macOS.fd, name: executableName, expected: executableBefore)
        try verifyEntry(parent: macOS.fd, name: debugDylibName, expected: dylibBefore)
        try check(started)

        let payload: [String: Any] = [
            "schema": "Celluloid.ExtensionSelfIdentity.1", "marker": marker,
            "observation_kind": "extension-self", "bundle_identifier": ownBundle.bundleIdentifier!,
            "pid": Int(pid), "bundle_path": bundle.path, "executable_path": executable.path,
            "executable_sha256": executableHash, "debug_dylib_path": debugDylib.path,
            "debug_dylib_sha256": dylibHash, "generation": generation.uuidString,
            "content_editing_started": true
        ]
        let bytes = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys, .withoutEscapingSlashes])
        guard bytes.count <= maximumJSONBytes else { throw Failure.budget }
        try check(started)
        return String(decoding: bytes, as: UTF8.self)
    }

    private static func check(_ started: UInt64) throws {
        try Task.checkCancellation()
        guard DispatchTime.now().uptimeNanoseconds - started <= maximumNanoseconds else { throw Failure.budget }
    }

    private static func digest(_ file: Descriptor, expected: Snapshot, started: UInt64) throws -> String {
        guard expected.links == 1, expected.size > 0, expected.size <= off_t(maximumFileBytes) else { throw Failure.invalidFile }
        var remaining = Int(expected.size), hasher = SHA256()
        var buffer = [UInt8](repeating: 0, count: 64 * 1_024)
        while remaining > 0 {
            try check(started)
            let requested = min(remaining, buffer.count)
            let count = buffer.withUnsafeMutableBytes { Darwin.read(file.fd, $0.baseAddress!, requested) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0, count <= requested else { throw Failure.read }
            hasher.update(data: Data(buffer.prefix(count)))
            remaining -= count
        }
        // A finite extra-byte read rejects growth even before the metadata check.
        try check(started)
        var extra: UInt8 = 0
        guard Darwin.read(file.fd, &extra, 1) == 0 else { throw Failure.changedFile }
        guard try file.snapshot(kind: mode_t(S_IFREG)) == expected else { throw Failure.changedFile }
        try check(started)
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private static func verifyEntry(parent: Int32, name: String, expected: Snapshot) throws {
        var status = stat()
        guard fstatat(parent, name, &status, AT_SYMLINK_NOFOLLOW) == 0,
              Snapshot(status) == expected else { throw Failure.changedFile }
    }

    private struct Snapshot: Equatable {
        let device: dev_t, inode: ino_t, mode: mode_t, links: nlink_t, size: off_t
        let modifiedSeconds: Int, modifiedNanoseconds: Int, changedSeconds: Int, changedNanoseconds: Int
        init(_ status: stat) {
            device = status.st_dev; inode = status.st_ino; mode = status.st_mode
            links = status.st_nlink; size = status.st_size
            modifiedSeconds = status.st_mtimespec.tv_sec; modifiedNanoseconds = status.st_mtimespec.tv_nsec
            changedSeconds = status.st_ctimespec.tv_sec; changedNanoseconds = status.st_ctimespec.tv_nsec
        }
    }
    private final class Descriptor {
        let fd: Int32
        init(_ fd: Int32) throws {
            guard fd >= 0 else { throw Failure.read }
            self.fd = fd
        }
        deinit { close(fd) }
        func snapshot(kind: mode_t) throws -> Snapshot {
            var status = stat()
            guard fstat(fd, &status) == 0, status.st_mode & mode_t(S_IFMT) == kind else { throw Failure.invalidFile }
            return Snapshot(status)
        }
    }
}

/// A real AppKit AX leaf is retained inside the ready SwiftUI editor. Its value
/// is read from live session state, not cached by a delayed SwiftUI update. The
/// one-point overlay draws nothing and cannot intercept mouse or keyboard input.
struct MacPhotoSelfIdentityAccessibility: NSViewRepresentable {
    @ObservedObject var identity: MacPhotoSelfIdentity
    @ObservedObject var session: MacPhotoSession
    func makeNSView(context: Context) -> MacPhotoSelfIdentityAccessibilityView {
        MacPhotoSelfIdentityAccessibilityView(frame: .zero)
    }
    func updateNSView(_ view: MacPhotoSelfIdentityAccessibilityView, context: Context) {
        view.identity = identity; view.session = session
        view.setAccessibilityRole(.staticText)
        view.setAccessibilityIdentifier("photos-extension.self-identity")
        view.setAccessibilityLabel(MacPhotoSelfIdentityCapture.marker)
        view.refreshAccessibility()
    }
    static func dismantleNSView(_ view: MacPhotoSelfIdentityAccessibilityView, coordinator: ()) {
        view.identity = nil; view.session = nil
        view.refreshAccessibility()
    }
}

final class MacPhotoSelfIdentityAccessibilityView: NSView {
    weak var identity: MacPhotoSelfIdentity?
    weak var session: MacPhotoSession?
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
        guard window != nil, !isHiddenOrHasHiddenAncestor, let identity, let session else { return nil }
        return identity.readyValue(for: session)
    }
}
#endif
