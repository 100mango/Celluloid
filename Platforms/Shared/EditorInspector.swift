import SwiftUI
import CelluloidDomain
import CelluloidRendering
// VISION_PASSIVE_FOCUS_BEGIN:import
#if os(visionOS) && DEBUG && CELLULOID_VISION_FOCUS_DIAGNOSTIC
import UIKit
#endif
// VISION_PASSIVE_FOCUS_END:import
#if os(macOS)
import AppKit
#endif

struct EditorInspector: View {
    let recipe: EditRecipe
    @Binding var selection: UUID?
    let change: RecipeChange
    @State private var assetPanel: AssetPanel?
    @State private var showingPrivacy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Celluloid").font(.largeTitle.bold())
                Text("Native photo editor").foregroundStyle(.primary)
                #if os(macOS)
                HStack {
                    Text("Filter")
                    NativeChoicePicker(selection: Binding(get: { recipe.filter.rawValue }, set: { raw in
                        guard let preset = FilterPreset(rawValue: raw) else { return }
                        change({ $0.filter = preset }, "Change Filter")
                    }), options: FilterPreset.allCases.map { (id: $0.rawValue, title: $0.localizedTitle) },
                       label: NSLocalizedString("Filter", comment: "Filter menu"), identifier: "editor.filter")
                }
                #else
                Picker("Filter", selection: Binding(get: { recipe.filter }, set: { preset in
                    change({ $0.filter = preset }, "Change Filter")
                })) {
                    ForEach(FilterPreset.allCases, id: \.rawValue) { Text($0.localizedTitle).tag($0) }
                }.accessibilityIdentifier("editor.filter")
                #endif
                if recipe.filter == .pixellateFace { Text("Face detection can miss faces. Check the result before sharing.").font(.caption) }
                if recipe.sources.count > 1 {
                    CollagePicker(recipe: recipe, change: change)
                }
                HStack {
                    Button("Sticker") { assetPanel = .stickers }.accessibilityIdentifier("editor.add-sticker")
                    Button("Bubble") { assetPanel = .bubbles }.accessibilityIdentifier("editor.add-bubble")
                }.disabled(recipe.sources.isEmpty || recipe.overlays.count >= 100)
                .popover(item: $assetPanel) { panel in
                    AssetPaletteView(panel: panel) { overlay in add(overlay); assetPanel = nil }
                }
                SourceInspector(recipe: recipe, change: change)
                Text("Layers").font(.headline)
                if recipe.overlays.isEmpty { Text("Add a sticker or a speech bubble").foregroundStyle(.primary) }
                ForEach(recipe.overlays.reversed()) { overlay in
                    Button {
                        selection = overlay.id
                    } label: {
                        HStack {
                            Image(systemName: overlay.kind == .bubble ? "text.bubble" : "face.smiling")
                            Text(layerTitle(overlay)).lineLimit(1)
                            Spacer()
                            if selection == overlay.id { Image(systemName: "checkmark.circle.fill") }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain).padding(6)
                        .accessibilityLabel(String(format: NSLocalizedString("Select layer: %@", comment: "Layer selection"), String(layerTitle(overlay).prefix(80))))
                        .accessibilityIdentifier("layer." + overlay.id.uuidString)
                }
                if let selected = recipe.overlays.first(where: { $0.id == selection }) {
                    OverlayInspector(overlay: selected, update: update, remove: remove).id(selected.id)
                }
                Divider()
                Text("Static photos · sRGB SDR export").editorHelperText()
                Text("RAW/ProRAW and animation are not supported. Live Photos import as still images.").editorHelperText()
                Text("Save this .celluloid document to reopen all originals, layers and text. Export PNG or JPEG for a finished image.")
                    .editorHelperText()
                Button("Privacy Policy") { showingPrivacy = true }.accessibilityIdentifier("editor.privacy")
            }.padding(18)
        }.sheet(isPresented: $showingPrivacy) { PrivacyView() }
        // VISION_PASSIVE_FOCUS_BEGIN:lifecycle
        #if os(visionOS) && DEBUG && CELLULOID_VISION_FOCUS_DIAGNOSTIC
        .onAppear {
            VisionPassiveFocusProbe.shared.start(initialSourceCount: recipe.sources.count, initialOverlayCount: recipe.overlays.count)
        }
        .onDisappear { VisionPassiveFocusProbe.shared.stop(reason: "inspector_disappeared") }
        #endif
        // VISION_PASSIVE_FOCUS_END:lifecycle
    }
    private func layerTitle(_ overlay: Overlay) -> String {
        if overlay.kind == .bubble {
            return overlay.text.isEmpty ? (BubbleAsset(rawValue: overlay.asset)?.localizedTitle ?? overlay.asset) : overlay.text
        }
        return String(format: NSLocalizedString("Sticker %d", comment: "Sticker name"), (Int(overlay.asset) ?? 32) - 31)
    }
    private func add(_ overlay: Overlay) {
        selection = overlay.id
        change({ $0.overlays.append(overlay) }, "Add \(overlay.kind.rawValue.capitalized)")
    }
    private func update(_ identity: UUID, _ mutation: @escaping (inout Overlay) -> Void, _ name: String) {
        change({ $0.editOverlay(identity, mutation: mutation) }, name)
    }
    private func remove(_ overlay: Overlay) {
        selection = nil
        change({ $0.overlays.removeAll { $0.id == overlay.id } }, "Delete Layer")
    }
}

private struct CollagePicker: View {
    let recipe: EditRecipe
    let change: RecipeChange
    @State private var templates: [CollageTemplate] = []
    @State private var failure: String?
    var body: some View {
        VStack(alignment: .leading) {
            Picker("Collage Layout", selection: Binding(get: { recipe.collageTemplate ?? "" }, set: { name in
                change({ $0.collageTemplate = name }, "Change Collage Layout")
            })) {
                ForEach(templates, id: \.assetName) { Text($0.assetName).tag($0.assetName) }
            }
            if let failure { Text(failure).foregroundStyle(.red) }
        }.task(id: recipe.sources.count) {
            do { templates = try NativeResources.templates(count: recipe.sources.count); failure = nil }
            catch { failure = error.localizedDescription }
        }
    }
}

private struct OverlayInspector: View {
    let overlay: Overlay
    let update: (UUID, @escaping (inout Overlay) -> Void, String) -> Void
    let remove: (Overlay) -> Void
    #if os(macOS)
    @FocusState private var editingText: Bool
    #endif
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()
            Text("Selected Layer").font(.headline)
            if overlay.kind == .bubble {
                #if os(visionOS)
                // VISION_PASSIVE_FOCUS_BEGIN:control-open
                #if os(visionOS) && DEBUG && CELLULOID_VISION_FOCUS_DIAGNOSTIC
                if VisionPassiveFocusConfiguration.current?.mode == "control" {
                    VisionPassivePlainTextEditor().id(overlay.id)
                } else {
                    VisionBubbleTextEditor(value: overlay.text, accepts: { text in
                        var candidate = overlay; candidate.text = text
                        return (try? candidate.validate()) != nil
                    }) { text in edit("Edit Bubble Text") { $0.text = text } }.id(overlay.id)
                }
                #else
                // VISION_PASSIVE_FOCUS_END:control-open
                VisionBubbleTextEditor(value: overlay.text, accepts: { text in
                    var candidate = overlay; candidate.text = text
                    return (try? candidate.validate()) != nil
                }) { text in edit("Edit Bubble Text") { $0.text = text } }.id(overlay.id)
                // VISION_PASSIVE_FOCUS_BEGIN:control-close
                #endif
                // VISION_PASSIVE_FOCUS_END:control-close
                #else
                TextField("Bubble text", text: Binding(get: { overlay.text }, set: { text in
                    edit("Edit Bubble Text") { $0.text = text }
                }), axis: .vertical).lineLimit(3...8).accessibilityIdentifier("editor.bubble-text")
                    .focused($editingText)
                #endif
                number("Text size", \.fontSize, range: 0.005...0.2)
            }
            number("Horizontal position", \.centerX, range: -0.5...1.5)
            number("Vertical position", \.centerY, range: -0.5...1.5)
            number("Width", \.width, range: 0.02...1.5)
            number("Height", \.height, range: 0.02...1.5)
            number("Rotation", \.rotation, range: -180...180)
            Toggle("Mirror layer", isOn: Binding(get: { overlay.mirrored }, set: { value in
                edit("Mirror Layer") { $0.mirrored = value }
            }))
            HStack {
                Button("←") { nudge(x: -0.01, y: 0) }.keyboardShortcut(.leftArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer left")
                Button("↑") { nudge(x: 0, y: -0.01) }.keyboardShortcut(.upArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer up")
                Button("↓") { nudge(x: 0, y: 0.01) }.keyboardShortcut(.downArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer down")
                Button("→") { nudge(x: 0.01, y: 0) }.keyboardShortcut(.rightArrow, modifiers: [.command, .option]).accessibilityLabel("Move layer right")
            }
            HStack {
                Button("Rotate −15°") { rotate(-15) }.keyboardShortcut("[", modifiers: [.command, .option])
                Button("Rotate +15°") { rotate(15) }.keyboardShortcut("]", modifiers: [.command, .option])
            }
            Button("Delete Layer", role: .destructive) { remove(overlay) }
            Text("Move with ⌥⌘ arrows; rotate with ⌥⌘ [ or ].").editorHelperText()
        }
    }
    private func edit(_ name: String, _ mutation: @escaping (inout Overlay) -> Void) {
        update(overlay.id, mutation, name)
    }
    private func number(_ label: String, _ path: WritableKeyPath<Overlay, Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack { Text(LocalizedStringKey(label)).editorAdjustmentLabel(); Spacer(); Text(overlay[keyPath: path], format: .number.precision(.fractionLength(2))).monospacedDigit().accessibilityIdentifier("editor.layer.value." + label) }
            EditorSlider(value: Binding(get: { overlay[keyPath: path] }, set: { value in
                edit(label) { $0[keyPath: path] = value }
            }), range: range, label: NSLocalizedString(label, comment: "Layer adjustment"))
        }
    }
    #if os(macOS)
    private func finishTextInput() -> Bool {
        // A Cocoa field editor may commit on focus exit. Complete that normal
        // responder transition synchronously before applying a document command.
        if editingText, NSApp.keyWindow?.makeFirstResponder(nil) == false { return false }
        editingText = false
        return true
    }
    #endif
    private func nudge(x: Double, y: Double) {
        #if os(macOS)
        // These are document-transform commands, even when invoked while a
        // multiline field is focused. End text input before the next Undo.
        guard finishTextInput() else { return }
        #endif
        edit("Move Layer") {
            $0.centerX = min(3, max(-2, $0.centerX + x)); $0.centerY = min(3, max(-2, $0.centerY + y))
        }
    }
    private func rotate(_ delta: Double) {
        #if os(macOS)
        guard finishTextInput() else { return }
        #endif
        edit("Rotate Layer") { $0.rotation = ($0.rotation + delta).truncatingRemainder(dividingBy: 360) }
    }
}

#if os(visionOS)
/// Keep the text-input value in local state while document revisions and preview
/// tasks are published. The previous getter read an immutable recipe snapshot on
/// every input event; exact full-string UI assertions guard against lost input.
private struct VisionBubbleTextEditor: View {
    let value: String
    let accepts: (String) -> Bool
    let commit: (String) -> Void
    @State private var draft: String
    init(value: String, accepts: @escaping (String) -> Bool, commit: @escaping (String) -> Void) {
        self.value = value; self.accepts = accepts; self.commit = commit; _draft = State(initialValue: value)
    }
    var body: some View {
        TextEditor(text: $draft).frame(minHeight: 110, maxHeight: 180)
            .accessibilityLabel("Bubble text").accessibilityIdentifier("editor.bubble-text")
            .onChange(of: draft) { text in
                if text != value {
                    commit(text) // The document reports its normal validation error.
                    if !accepts(text) { draft = value } // Never display unsaved oversized text as the exported recipe.
                }
            }
            .onChange(of: value) { text in if text != draft { draft = text } }
    }
}
#endif
// VISION_PASSIVE_FOCUS_BEGIN:implementation
#if os(visionOS) && DEBUG && CELLULOID_VISION_FOCUS_DIAGNOSTIC
private struct VisionPassiveFocusConfiguration {
    let nonce: String
    let mode: String
    static var current: Self? {
        let environment = ProcessInfo.processInfo.environment
        guard let mode = environment["CELLULOID_VISION_FOCUS_MODE"], ["target", "control"].contains(mode),
              let nonce = environment["CELLULOID_VISION_FOCUS_NONCE"], nonce.count == 36,
              let identifier = UUID(uuidString: nonce), identifier.uuidString.lowercased() == nonce.lowercased() else { return nil }
        return Self(nonce: nonce, mode: mode)
    }
}

private struct VisionPassivePlainTextEditor: View {
    @State private var text = "Hello"
    var body: some View {
        TextEditor(text: $text).frame(minHeight: 110, maxHeight: 180)
            .accessibilityLabel("Bubble text").accessibilityIdentifier("editor.bubble-text")
    }
}

/// Passive public-UIKit observations only. No responder setters, delegate changes,
/// accessibility telemetry, keyboard requests, or document callbacks are installed.
@MainActor private final class VisionPassiveFocusProbe {
    static let shared = VisionPassiveFocusProbe()
    private static let identifier = "editor.bubble-text"
    private let maximumDuration: TimeInterval = 540
    private let maximumRecords = 2048
    private let maximumBytes = 524288
    private var configuration: VisionPassiveFocusConfiguration?
    private var handle: FileHandle?
    private var timer: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []
    private weak var textView: UITextView?
    private weak var identifierView: UIView?
    private weak var observedWindow: UIWindow?
    private weak var observedScene: UIWindowScene?
    private var viewLifetime = 0
    private var windowLifetime = 0
    private var sceneLifetime = 0
    private var mappingSource = "unresolved"
    private var identifierNodeCount = 0
    private var startedAt: TimeInterval = 0
    private var lastDiscovery: TimeInterval = -.infinity
    private var lastSnapshot: TimeInterval = -.infinity
    private var lastState: Data?
    private var records = 0
    private var bytes = 0
    private var previousWriteSeconds: TimeInterval = 0
    private var previousWriteSequence = 0
    private var stopping = false
    private var attempted = false

    func start(initialSourceCount: Int, initialOverlayCount: Int) {
        // A restored edited document or a blank editor must not consume this
        // process's sole attempt before the fresh image-only fixture is opened.
        guard initialSourceCount == 1, initialOverlayCount == 0,
              !attempted, let configuration = VisionPassiveFocusConfiguration.current else { return }
        attempted = true
        self.configuration = configuration
        do {
            let caches = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            let directory = caches.appendingPathComponent("CelluloidVisionFocus", isDirectory: true)
                .appendingPathComponent(configuration.nonce, isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let path = directory.appendingPathComponent(configuration.mode + ".ndjson")
            // The validated nonce is the only variable path component. Never
            // truncate or reuse an existing phase receipt, even on remount.
            try Data().write(to: path, options: [.withoutOverwriting])
            handle = try FileHandle(forWritingTo: path)
        } catch {
            print("VISION_PASSIVE_FOCUS_FILE_UNAVAILABLE mode=\(configuration.mode) nonce=\(configuration.nonce)")
            return
        }
        startedAt = ProcessInfo.processInfo.systemUptime
        write("start", ["sample_seconds": 0.1, "heartbeat_seconds": 1, "discovery_seconds": 1,
                        "maximum_duration_seconds": maximumDuration, "maximum_records": maximumRecords,
                        "maximum_bytes": maximumBytes, "keyboard_notifications": "visionOS_absence_expected_neutral",
                        "initial_source_count": initialSourceCount, "initial_overlay_count": initialOverlayCount])
        guard handle != nil else { return }
        for (name, event) in [(UITextView.textDidBeginEditingNotification, "text_did_begin"),
                              (UITextView.textDidEndEditingNotification, "text_did_end"),
                              (UITextView.textDidChangeNotification, "text_did_change")] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] note in
                MainActor.assumeIsolated {
                    guard let view = note.object as? UITextView else { return }
                    self?.editingNotification(event, view: view)
                }
            })
        }
        timer = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 100_000_000) } catch { return }
                guard let self, self.handle != nil else { return }
                self.sample()
            }
        }
    }

    func stop(reason: String) {
        guard handle != nil, !stopping else { return }
        stopping = true
        write("stop", ["reason": reason, "view_lifetime": viewLifetime])
        timer?.cancel(); timer = nil
        observers.forEach { NotificationCenter.default.removeObserver($0) }; observers.removeAll()
        try? handle?.close(); handle = nil
        textView = nil; identifierView = nil; observedWindow = nil; observedScene = nil
        stopping = false
    }

    private func sample() {
        let now = ProcessInfo.processInfo.systemUptime
        guard now - startedAt < maximumDuration else {
            if viewLifetime == 0 { write("mapping_unresolved", ["reason": "discovery_deadline", "candidate_count": 0]) }
            stop(reason: "duration_cap"); return
        }
        let proofStillContainsView: Bool
        if let view = textView, let proof = identifierView {
            proofStillContainsView = view === proof || view.isDescendant(of: proof)
        } else { proofStillContainsView = false }
        if viewLifetime > 0 && (!proofStillContainsView || textView?.window !== observedWindow
                || textView?.window?.windowScene !== observedScene
                || identifierView?.accessibilityIdentifier != Self.identifier) {
            resolveMapping(checkpoint: "lifetime")
        } else if now - lastDiscovery >= 1 {
            // Repeat the same bounded complete scan after mapping, so a second
            // exact identifier cannot remain hidden behind an unchanged cache.
            resolveMapping(checkpoint: viewLifetime == 0 ? "discovery" : "periodic_uniqueness")
        }
        snapshot(event: "snapshot", force: false)
    }

    private func editingNotification(_ event: String, view: UITextView) {
        guard handle != nil else { return }
        if textView == nil { resolveMapping(checkpoint: event) }
        guard textView === view else { return }
        resolveMapping(checkpoint: event)
        guard textView === view else { return }
        snapshot(event: event, force: true)
    }

    private func resolveMapping(checkpoint: String) {
        guard handle != nil else { return }
        let scanStarted = ProcessInfo.processInfo.systemUptime
        lastDiscovery = scanStarted
        var visitedNodes = 0
        var scanFailure: String?
        func consumeNode(depth: Int) -> Bool {
            guard scanFailure == nil else { return false }
            if depth > 64 { scanFailure = "hierarchy_depth_cap"; return false }
            if visitedNodes >= 4096 { scanFailure = "hierarchy_node_cap"; return false }
            if ProcessInfo.processInfo.systemUptime - scanStarted >= 0.020 { scanFailure = "hierarchy_work_cap"; return false }
            visitedNodes += 1
            return true
        }
        var nodes: [UIView] = []
        func visit(_ view: UIView, depth: Int) {
            guard consumeNode(depth: depth) else { return }
            if view.accessibilityIdentifier == Self.identifier { nodes.append(view) }
            for child in view.subviews {
                visit(child, depth: depth + 1)
                if scanFailure != nil { return }
            }
        }
        sceneLoop: for scene in UIApplication.shared.connectedScenes {
            guard let scene = scene as? UIWindowScene else { continue }
            for window in scene.windows {
                visit(window, depth: 0)
                if scanFailure != nil { break sceneLoop }
            }
        }
        var candidates: [(UITextView, UIView, String)] = []
        var invalidNode = false
        for node in nodes {
            if scanFailure != nil { break }
            if let native = node as? UITextView { candidates.append((native, node, "exact_native_identifier")); continue }
            var descendants: [UITextView] = []
            func descend(_ view: UIView, depth: Int) {
                guard consumeNode(depth: depth) else { return }
                if let native = view as? UITextView { descendants.append(native) }
                for child in view.subviews {
                    descend(child, depth: depth + 1)
                    if scanFailure != nil { return }
                }
            }
            for child in node.subviews {
                descend(child, depth: 1)
                if scanFailure != nil { break }
            }
            if descendants.count == 1 { candidates.append((descendants[0], node, "exact_ancestor_identifier_sole_text_view")) }
            else { invalidNode = true }
        }
        let scanSeconds = ProcessInfo.processInfo.systemUptime - scanStarted
        if scanFailure == nil && scanSeconds >= 0.020 { scanFailure = "hierarchy_work_cap" }
        if let scanFailure {
            // Both scans share one budget. Never claim a unique mapping from
            // a partial hierarchy, even when one plausible view was encountered.
            write("mapping_unresolved", ["checkpoint": checkpoint, "reason": scanFailure,
                "candidate_count": 0, "candidate_count_complete": false,
                "scan_visited_nodes": visitedNodes, "scan_work_seconds": scanSeconds])
            stop(reason: "mapping_unresolved"); return
        }
        let identities = Set(candidates.map { ObjectIdentifier($0.0) })
        if nodes.isEmpty, viewLifetime == 0 {
            write("mapping_pending", ["checkpoint": checkpoint, "candidate_count": 0, "exact_identifier_node_count": 0])
            return
        }
        guard !invalidNode, identities.count == 1 else {
            write("mapping_unresolved", ["checkpoint": checkpoint, "candidate_count": identities.count,
                                         "exact_identifier_node_count": nodes.count,
                                         "reason": invalidNode ? "identifier_descendants_not_unique" : "native_mapping_not_unique"])
            stop(reason: "mapping_unresolved"); return
        }
        // Uniqueness has been established before choosing the corresponding
        // proof node. Prefer the exact native identifier if both proofs exist.
        guard let mapped = candidates.first(where: { $0.2 == "exact_native_identifier" }) ?? candidates.first else { return }
        let changed = textView !== mapped.0 || identifierView !== mapped.1 || mappingSource != mapped.2
        if textView !== mapped.0 { viewLifetime += 1 }
        textView = mapped.0; identifierView = mapped.1; mappingSource = mapped.2; identifierNodeCount = nodes.count
        if observedWindow !== mapped.0.window { windowLifetime += 1; observedWindow = mapped.0.window }
        if observedScene !== mapped.0.window?.windowScene { sceneLifetime += 1; observedScene = mapped.0.window?.windowScene }
        if changed {
            write("mapping_resolved", ["checkpoint": checkpoint, "candidate_count": 1,
                                       "exact_identifier_node_count": nodes.count, "mapping_source": mappingSource,
                                       "matched_identifier": Self.identifier, "mapped_node_text_view_count": 1,
                                       "view_lifetime": viewLifetime, "scan_visited_nodes": visitedNodes,
                                       "scan_work_seconds": scanSeconds])
        }
    }

    private func snapshot(event: String, force: Bool) {
        guard handle != nil, let view = textView else { return }
        let workStarted = ProcessInfo.processInfo.systemUptime
        func rect(_ value: CGRect) -> [String: Double] {
            ["x": Double(value.origin.x), "y": Double(value.origin.y), "width": Double(value.width), "height": Double(value.height)]
        }
        let ancestryStarted = ProcessInfo.processInfo.systemUptime
        var ancestor = view.superview
        var ancestorCount = 0
        var ancestorHidden = false
        var ancestorAlphaNonpositive = false
        var ancestorInteractionDisabled = false
        var ancestorVisibilityComplete = true
        var effectiveAlpha = Double(view.alpha)
        while let current = ancestor {
            guard ancestorCount < 64, ProcessInfo.processInfo.systemUptime - ancestryStarted < 0.020 else {
                ancestorVisibilityComplete = false; break
            }
            ancestorCount += 1
            ancestorHidden = ancestorHidden || current.isHidden
            ancestorAlphaNonpositive = ancestorAlphaNonpositive || current.alpha <= 0
            ancestorInteractionDisabled = ancestorInteractionDisabled || !current.isUserInteractionEnabled
            effectiveAlpha *= Double(current.alpha)
            ancestor = current.superview
        }
        let ancestorVisible = ancestorVisibilityComplete && !ancestorHidden && !ancestorAlphaNonpositive
        let value = view.text ?? ""
        let synthetic = value == "Hello" || (value.count == 6 && value.filter { $0 != "A" } == "Hello")
        var state: [String: Any] = ["candidate_count": 1, "mapping_source": mappingSource,
            "exact_identifier_node_count": identifierNodeCount, "view_lifetime": viewLifetime,
            "window_lifetime": windowLifetime, "scene_lifetime": sceneLifetime,
            "is_first_responder": view.isFirstResponder, "can_become_first_responder": view.canBecomeFirstResponder,
            "is_editable": view.isEditable, "is_selectable": view.isSelectable,
            "view_is_hidden": view.isHidden, "view_alpha": Double(view.alpha),
            "view_is_user_interaction_enabled": view.isUserInteractionEnabled, "view_has_superview": view.superview != nil,
            "ancestor_count": ancestorCount, "ancestor_visibility_complete": ancestorVisibilityComplete,
            "ancestor_hidden": ancestorHidden, "ancestor_alpha_nonpositive": ancestorAlphaNonpositive,
            "ancestor_interaction_disabled": ancestorInteractionDisabled, "ancestor_visible": ancestorVisible,
            "ancestor_interactable": ancestorVisible && !ancestorInteractionDisabled,
            "effective_alpha_complete": ancestorVisibilityComplete, "effective_alpha": effectiveAlpha,
            "has_window": view.window != nil, "window_is_key": view.window?.isKeyWindow ?? false,
            "window_is_hidden": view.window?.isHidden ?? false, "window_alpha": Double(view.window?.alpha ?? 0),
            "window_is_user_interaction_enabled": view.window?.isUserInteractionEnabled ?? false,
            "scene_activation_state": view.window?.windowScene?.activationState.rawValue ?? -99,
            "view_frame": rect(view.frame), "view_bounds": rect(view.bounds),
            "text_is_synthetic": synthetic, "text_synthetic": synthetic ? value : "redacted",
            "selected_range": ["location": view.selectedRange.location, "length": view.selectedRange.length]]
        if let window = view.window {
            state["window_frame"] = rect(window.frame)
            state["view_frame_in_window"] = rect(view.convert(view.bounds, to: window))
        }
        guard let signature = try? JSONSerialization.data(withJSONObject: state, options: [.sortedKeys]) else {
            stop(reason: "snapshot_encoding_failed"); return
        }
        let now = ProcessInfo.processInfo.systemUptime
        guard force || signature != lastState || now - lastSnapshot >= 1 else { return }
        state["heartbeat"] = !force && signature == lastState
        state["snapshot_work_started_uptime"] = workStarted
        state["snapshot_work_finished_uptime"] = now
        state["snapshot_work_seconds"] = now - workStarted
        lastState = signature; lastSnapshot = now
        write(event, state)
    }

    private func write(_ event: String, _ fields: [String: Any]) {
        guard let handle, let configuration else { return }
        let writeStarted = ProcessInfo.processInfo.systemUptime
        var row = fields
        row["schema"] = "Celluloid.VisionFocusPassive.1"; row["nonce"] = configuration.nonce; row["mode"] = configuration.mode
        row["pid"] = ProcessInfo.processInfo.processIdentifier; row["seq"] = records + 1; row["event"] = event
        row["unix_seconds"] = Date().timeIntervalSince1970; row["system_uptime"] = ProcessInfo.processInfo.systemUptime
        if previousWriteSequence > 0 {
            row["previous_write_seq"] = previousWriteSequence
            row["previous_write_work_seconds"] = previousWriteSeconds
        }
        guard var data = try? JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]) else {
            if !stopping { stop(reason: "record_encoding_failed") }; return
        }
        data.append(0x0A)
        // Reserve room for the terminal record, so a cap never silently turns
        // the file into an apparently complete observation.
        if !stopping && (records >= maximumRecords - 1 || bytes + data.count > maximumBytes - 2048) {
            stop(reason: "record_or_byte_cap"); return
        }
        guard records < maximumRecords, bytes + data.count <= maximumBytes else { return }
        do {
            try handle.write(contentsOf: data); records += 1; bytes += data.count
            previousWriteSequence = records
            previousWriteSeconds = ProcessInfo.processInfo.systemUptime - writeStarted
        }
        catch { if !stopping { stop(reason: "write_failed") } }
    }
}
#endif
// VISION_PASSIVE_FOCUS_END:implementation
