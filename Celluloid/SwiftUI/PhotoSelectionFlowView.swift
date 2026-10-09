import SwiftUI
import PhotosUI
import CelluloidKit

@MainActor struct PhotoSelectionFlowView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    private let maximumSelection: Int
    private let traceID: String
    @StateObject private var session: PhotoSelectionSession
    @State private var managingAccess = false

    init(maximumSelection: Int, traceID: String = UUID().uuidString) {
        self.traceID = traceID
        self.maximumSelection = maximumSelection
        _session = StateObject(wrappedValue: PhotoSelectionSession(maximumSelection: maximumSelection))
    }

    var body: some View {
        ZStack {
            Color(UIColor.systemBackground).ignoresSafeArea()
            switch session.phase {
            case .picking:
                SystemPhotoPicker(maximumSelection: maximumSelection, traceID: traceID, didFinish: picked)
                    .ignoresSafeArea()
            case .resolving:
                VStack(spacing: 24) {
                    ProgressView(NSLocalizedString("Opening selected photos…", comment: "Selected asset lookup"))
                    Button(tr(.cancel), action: cancel).padding(12)
                }
                .accessibilityIdentifier("selected-photos-loading")
            case .recovery(let error):
                PhotoSelectionRecoveryView(error: error, authorization: session.authorization,
                    allowAccess: session.requestAccess, manageAccess: showAccessManagement,
                    retry: session.resolveOriginals, chooseAgain: session.chooseAgain, cancel: cancel)
            case .editing(let assets):
                CelluloidEditorView(assets: assets).ignoresSafeArea()
                    .onAppear {
                        PickerEntryDiagnostics.selected("resolved-original-identities", instance: traceID,
                            identifiers: assets.map { $0.localIdentifier })
                        PickerEntryDiagnostics.record("editor-opened", instance: traceID)
                    }
            }
        }
        .interactiveDismissDisabled()
        .sheet(isPresented: $managingAccess, onDismiss: session.refreshAccessIfRecovering) {
            LimitedPhotoAccessSheet { managingAccess = false }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { session.refreshAccessIfRecovering() }
        }
        .onDisappear(perform: session.cancelPending)
    }

    private func picked(_ results: [PHPickerResult]) {
        if results.isEmpty { cancel() }
        else { session.selected(results) }
    }
    private func showAccessManagement() { managingAccess = true }
    private func cancel() { session.cancelPending(); dismiss() }
}

private struct PhotoSelectionRecoveryView: View {
    @Environment(\.openURL) private var openURL
    let error: PhotoSelectionError
    let authorization: PHAuthorizationStatus
    let allowAccess: () -> Void
    let manageAccess: () -> Void
    let retry: () -> Void
    let chooseAgain: () -> Void
    let cancel: () -> Void

    private var canRecoverAccess: Bool {
        error != .originalIdentityMissing && error != .invalidSelection
    }

    private var message: String {
        switch error {
        case .invalidSelection:
            return NSLocalizedString("Choose between one and four images.", comment: "Invalid selection")
        case .accessRequired:
            return NSLocalizedString("Allow access to the selected originals to keep edits reversible in Photos. Choosing a photo does not grant permission to change its original.", comment: "Original editing permission")
        case .originalIdentityMissing:
            return NSLocalizedString("Photos did not provide the original identity for this selection. Choose the photo again. Editing an imported copy is not available here yet.", comment: "Picker cannot identify original")
        case .originalUnavailable:
            return NSLocalizedString("A selected original is unavailable. It may have been removed or may be outside your allowed Photos selection. Choose it again or update Photos access. No copy has been imported.", comment: "Selected original unavailable")
        }
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(message).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("photos-state")
                    if canRecoverAccess && authorization == .notDetermined {
                        Button(NSLocalizedString("Allow Original Editing", comment: "Photos permission"), action: allowAccess)
                            .accessibilityIdentifier("photos-allow-originals")
                    }
                    if canRecoverAccess && authorization == .limited {
                        Button(NSLocalizedString("Manage Photos", comment: "Limited Photos management"), action: manageAccess)
                            .accessibilityIdentifier("manage-photos")
                    }
                    if canRecoverAccess && (authorization == .denied || authorization == .restricted) {
                        Button(NSLocalizedString("Open Settings", comment: "Permission recovery"), action: showSettings)
                            .accessibilityIdentifier("photos-settings")
                    }
                    if canRecoverAccess {
                        Button(NSLocalizedString("Retry", comment: "Retry selection"), action: retry)
                            .accessibilityIdentifier("selected-photos-retry")
                    }
                    Button(NSLocalizedString("Choose Photos Again", comment: "Replace unavailable selection"), action: chooseAgain)
                        .accessibilityIdentifier("selected-photos-reselect")
                }
                .buttonStyle(SelectionRecoveryButtonStyle())
                .padding(24)
                .frame(maxWidth: 600, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle(tr(.beautify))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(tr(.cancel), action: cancel).accessibilityIdentifier("selected-photos-cancel")
                }
            }
        }
        .navigationViewStyle(.stack)
    }

    private func showSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        openURL(url)
    }
}

private struct SelectionRecoveryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 10)
            .frame(minHeight: 44, alignment: .leading)
            .foregroundColor(.accentColor)
            .opacity(configuration.isPressed ? 0.6 : 1)
    }
}
