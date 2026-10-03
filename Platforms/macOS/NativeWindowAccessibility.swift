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
            guard !snapshotScheduled, window != nil, ProcessInfo.processInfo.environment["CELLULOID_AX_REPORT"] != nil else { return }
            snapshotScheduled = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.writeSnapshot() }
            #endif
        }
        #if DEBUG
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
