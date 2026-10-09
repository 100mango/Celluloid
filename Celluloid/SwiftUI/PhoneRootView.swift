import SwiftUI
import CelluloidKit

/// SwiftUI owns iPhone/iPad presentation and routes confirmed original assets
/// into the shared editing UI without starting photo work during view evaluation.
@MainActor struct PhoneRootView: View {
    @State private var destination: Destination?

    enum Destination: String, Identifiable {
        case beautify, collage, privacy
        var id: String { rawValue }
    }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 24) {
                    PhoneEntryActions(horizontal: geometry.size.width > geometry.size.height,
                                      beautify: showBeautify, collage: showCollage)
                        .frame(minHeight: max(240, geometry.size.height - 100))
                    Button(NSLocalizedString("Privacy Policy", comment: "Privacy entry"), action: showPrivacy)
                        .font(.footnote)
                        .padding(12)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("privacy-policy")
                        .accessibilityHint(NSLocalizedString("Shows the privacy policy offline.", comment: "Privacy entry hint"))
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 16)
            }
        }
        .foregroundColor(.white)
        .background(Color.black.ignoresSafeArea())
        .fullScreenCover(item: $destination) { route in
            switch route {
            case .beautify: PhotoSelectionFlowView(maximumSelection: 1)
            case .collage: PhotoSelectionFlowView(maximumSelection: 4)
            case .privacy: LegacyPrivacyScreen()
            }
        }
    }

    private func showBeautify() { destination = .beautify }
    private func showCollage() { destination = .collage }
    private func showPrivacy() { destination = .privacy }
}

private struct PhoneEntryActions: View {
    let horizontal: Bool
    let beautify: () -> Void
    let collage: () -> Void

    var body: some View {
        // A two-column lazy grid preserves child identity across rotation and
        // needs no iOS 16 ViewThatFits/AnyLayout deployment-target exception.
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 24), count: horizontal ? 2 : 1), spacing: 24) {
            PhoneEntryButton(title: tr(.beautify), image: "EditPhotoEntranceButton", identifier: "edit-photo", action: beautify)
            PhoneEntryButton(title: tr(.collage), image: "CollageEntranceButton", identifier: "make-collage", action: collage)
        }
    }
}

private struct PhoneEntryButton: View {
    let title: String
    let image: String
    let identifier: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 24) {
                Image(image).renderingMode(.template).resizable().scaledToFit().frame(width: 62.5, height: 62.5)
                Text(title).font(.body).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, minHeight: 160)
            .padding(.vertical, 20)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
        .accessibilityLabel(title)
    }
}
