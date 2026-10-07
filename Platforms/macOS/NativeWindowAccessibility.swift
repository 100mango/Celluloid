import AppKit
import SwiftUI

/// DocumentGroup has an AppKit hosting container outside the SwiftUI editor.
/// Its actual role/class tree is captured in Debug CI; an audit pass is still required.
struct NativeWindowAccessibility: NSViewRepresentable {
    var paneLabel: String? = nil
    func makeNSView(context: Context) -> Probe { let view = Probe(); view.paneLabel = paneLabel; return view }
    func updateNSView(_ view: Probe, context: Context) { view.paneLabel = paneLabel; view.labelContent() }
    final class Probe: NSView {
        var paneLabel: String?
        #if DEBUG
        private var snapshotScheduled = false
        // BEGIN CELLULOID_MAC_STORE_CAPTURE_STATE
        private var storeWindowSized = false
        // END CELLULOID_MAC_STORE_CAPTURE_STATE
        #endif
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); labelContent() }
        func labelContent() {
            if let paneLabel {
                // The b98 native AX trace identified an extra, unnamed hosting
                // Group inside each NSSplitView pane. Label only our own pane's
                // ancestor, using public roles/containment, never private class names.
                var ancestor = superview
                for _ in 0..<12 {
                    guard let view = ancestor else { break }
                    if view.superview?.superview is NSSplitView,
                       view.accessibilityRole() == .group, view.isAccessibilityElement() {
                        view.setAccessibilityLabel(paneLabel); break
                    }
                    ancestor = view.superview
                }
            } else {
                window?.contentView?.setAccessibilityLabel(NSLocalizedString("Native photo editor", comment: "Document content container"))
            }
            setAccessibilityElement(false)
            #if DEBUG
            // BEGIN CELLULOID_MAC_STORE_CAPTURE_CALL
            configureStoreWindowIfRequested()
            // END CELLULOID_MAC_STORE_CAPTURE_CALL
            guard !snapshotScheduled, window != nil, ProcessInfo.processInfo.environment["CELLULOID_AX_REPORT"] != nil else { return }
            snapshotScheduled = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.writeSnapshot() }
            #endif
        }
        #if DEBUG
        // BEGIN CELLULOID_MAC_STORE_CAPTURE_HELPER
        /// The fixed screenshot case resizes only its existing document window.
        /// No-token Debug and the complete Release projection are unchanged.
        private func configureStoreWindowIfRequested() {
            let info = ProcessInfo.processInfo
            guard paneLabel == nil, !storeWindowSized, let window,
                  let token = info.environment["CELLULOID_MAC_STORE_CAPTURE"],
                  UUID(uuidString: token)?.uuidString == token,
                  info.arguments.contains("--celluloid-store-capture"),
                  info.environment["CELLULOID_NATIVE_AUDIT_CONTROL"] == nil,
                  info.environment["CELLULOID_SANDBOX_DIAGNOSTICS"] == nil,
                  info.environment["CELLULOID_AX_REPORT"] == nil,
                  !info.arguments.contains("--celluloid-sandbox-diagnostics"),
                  let screen = window.screen ?? NSScreen.main,
                  screen.backingScaleFactor == 1,
                  screen.frame.width == 1280, screen.frame.height == 960,
                  screen.visibleFrame.width >= 1280, screen.visibleFrame.height >= 800 else { return }
            storeWindowSized = true
            let visible = screen.visibleFrame
            var frame = window.frame
            frame.size = NSSize(width: 1280, height: 800)
            let x = (visible.midX - frame.width / 2).rounded()
            let y = (visible.midY - frame.height / 2).rounded()
            frame.origin = NSPoint(x: min(max(x, visible.minX), visible.maxX - frame.width),
                                   y: min(max(y, visible.minY), visible.maxY - frame.height))
            window.setFrame(frame, display: true)
        }
        // END CELLULOID_MAC_STORE_CAPTURE_HELPER
        private func writeSnapshot() {
            guard let window, let path = ProcessInfo.processInfo.environment["CELLULOID_AX_REPORT"] else { return }
            let target = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
            let temp = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
            guard target.path.hasPrefix(temp.path + "/") else { return }
            var rows: [[String: Any]] = [], visited = Set<ObjectIdentifier>()
            func accessibility(_ element: Any, depth: Int) {
                guard depth <= 7, rows.count < 64 else { return }
                guard let node = element as? NSAccessibilityProtocol else {
                    rows.append(["tree":"accessibility","depth":depth,"class":String(String(reflecting:type(of:element)).prefix(300)),"full_accessibility_protocol":false])
                    return
                }
                let identity = ObjectIdentifier(node as AnyObject); guard visited.insert(identity).inserted else { return }
                rows.append(["tree":"accessibility","depth":depth,"class":String(String(reflecting:type(of:element)).prefix(300)),
                             "role":node.accessibilityRole()?.rawValue ?? "nil","label":String((node.accessibilityLabel() ?? "nil").prefix(200)),
                             "frame":NSStringFromRect(node.accessibilityFrame()),"element":node.isAccessibilityElement(),"enabled":node.isAccessibilityEnabled()])
                for child in (node.accessibilityChildren() ?? []).prefix(64) { accessibility(child,depth:depth+1) }
            }
            accessibility(window,depth:0)
            var viewCount = 0
            func views(_ view: NSView, depth: Int) {
                guard depth <= 7, viewCount < 64 else { return }; viewCount += 1
                rows.append(["tree":"views","depth":depth,"class":String(String(reflecting:type(of:view)).prefix(300)),
                             "role":view.accessibilityRole()?.rawValue ?? "nil","label":String((view.accessibilityLabel() ?? "nil").prefix(200)),
                             "frame":NSStringFromRect(view.frame),"element":view.isAccessibilityElement()])
                for child in view.subviews.prefix(64) { views(child,depth:depth+1) }
            }
            if let content = window.contentView { views(content,depth:0) }
            let lines = rows.compactMap { try? JSONSerialization.data(withJSONObject:$0,options:[.sortedKeys]) }.map { String(decoding:$0,as:UTF8.self) }
            let bytes = Data(lines.joined(separator:"\n").utf8)
            guard bytes.count <= 64_000 else { return }
            try? bytes.write(to:target,options:.atomic)
        }
        #endif
    }
}

/// Labels only the owned presentation pair identified by the 59f runtime trace.
/// The bridge must be inside a real AXPopover window, and its public ancestor
/// must be an AXGroup whose direct accessibility parent is that exact window
/// and whose screen frame matches it. No system-wide enumeration/class matching
/// or accessibility-child mutation is used.
struct NativePopoverAccessibility: NSViewRepresentable {
    let label: String
    func makeNSView(context: Context) -> Bridge { let view = Bridge(); view.label = label; return view }
    func updateNSView(_ view: Bridge, context: Context) { view.label = label; view.labelOwnedPresentation() }
    final class Bridge: NSView {
        var label = ""
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); labelOwnedPresentation() }
        func labelOwnedPresentation() {
            setAccessibilityElement(false)
            guard !label.isEmpty, let window, window.accessibilityRole() == .popover else { return }
            let bounds = window.accessibilityFrame()
            guard !bounds.isEmpty else { return }
            var ancestor: Any? = accessibilityParent(), visited = Set<ObjectIdentifier>()
            for _ in 0..<12 {
                guard let node = ancestor as? NSAccessibilityProtocol,
                      visited.insert(ObjectIdentifier(node as AnyObject)).inserted else { return }
                if let group = node as? NSView, group.accessibilityRole() == .group,
                   let owner = group.accessibilityParent() as? NSWindow, owner === window {
                    let frame = group.accessibilityFrame()
                    guard abs(frame.minX - bounds.minX) < 1, abs(frame.minY - bounds.minY) < 1,
                          abs(frame.width - bounds.width) < 1, abs(frame.height - bounds.height) < 1 else { return }
                    group.setAccessibilityLabel(label)
                    window.setAccessibilityLabel(label)
                    return
                }
                if node is NSWindow { return }
                ancestor = node.accessibilityParent()
            }
        }
    }
}

#if DEBUG
struct NativePopoverOwnershipProbe: NSViewRepresentable {
    let label: String
    func makeNSView(context: Context) -> Probe { let value = Probe(); value.label = label; return value }
    func updateNSView(_ view: Probe, context: Context) { view.label = label }
    final class Probe: NSView {
        var label = ""
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow(); setAccessibilityElement(false)
            guard window != nil, ProcessInfo.processInfo.environment["CELLULOID_AX_REPORT"] != nil else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in self?.record() }
        }
        private func record() {
            guard let window, let path = ProcessInfo.processInfo.environment["CELLULOID_AX_REPORT"] else { return }
            let target = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
            let temporary = FileManager.default.temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
            guard target.path.hasPrefix(temporary.path + "/") else { return }
            var roots: [Any] = [self], view = superview
            for _ in 0..<16 { guard let current = view else { break }; roots.append(current); view = current.superview }
            roots.append(window)
            var rows: [[String: Any]] = [], visited = Set<ObjectIdentifier>()
            for root in roots {
                var current: Any? = root
                for depth in 0..<24 {
                    guard let element = current, rows.count < 64 else { break }
                    guard let node = element as? NSAccessibilityProtocol else {
                        rows.append(["presentation": label, "depth": depth, "class": String(String(reflecting: type(of: element)).prefix(240)), "full_accessibility_protocol": false]); break
                    }
                    guard visited.insert(ObjectIdentifier(node as AnyObject)).inserted else { break }
                    rows.append(["presentation": label, "depth": depth, "class": String(String(reflecting: type(of: element)).prefix(240)),
                                 "role": node.accessibilityRole()?.rawValue ?? "nil", "label": String((node.accessibilityLabel() ?? "nil").prefix(240)),
                                 "frame": NSStringFromRect(node.accessibilityFrame()), "enabled": node.isAccessibilityEnabled(),
                                 "children": node.accessibilityChildren()?.count ?? 0, "is_standard_popover": node is NSPopover,
                                 "is_own_window": (node as? NSWindow) === window])
                    if node.accessibilityRole() == .application { break }
                    current = node.accessibilityParent()
                }
            }
            let lines = rows.compactMap { try? JSONSerialization.data(withJSONObject: $0, options: [.sortedKeys]) }.map { String(decoding: $0, as: UTF8.self) }
            let data = Data(lines.joined(separator: "\n").utf8)
            guard data.count <= 64_000 else { return }
            try? data.write(to: target, options: .atomic)
        }
    }
}
#endif
