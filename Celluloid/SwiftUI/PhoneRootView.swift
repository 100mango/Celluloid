import SwiftUI
import CelluloidKit

/// SwiftUI owns presentation while retaining the original Entrance geometry.
/// Photo selection and image work start only after an explicit action.
@MainActor struct PhoneRootView: View {
    @State private var destination: Destination?

    enum Destination: String, Identifiable {
        case beautify, collage, privacy
        var id: String { rawValue }
    }

    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: PhoneEntryStyle.footerGap) {
                PhoneEntryActions(horizontal: PhoneEntryGeometry.isHorizontal(
                    safeSize: geometry.size, insets: geometry.safeAreaInsets),
                    beautify: showBeautify, collage: showCollage)
                PhonePrivacyButton(action: showPrivacy)
                    .padding(.horizontal, PhoneEntryStyle.footerHorizontalInset)
            }
            .padding(.bottom, PhoneEntryStyle.footerBottomInset)
            .frame(width: geometry.size.width, height: geometry.size.height)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("phone-entry-safe-area")
        }
        .background(Color.black.ignoresSafeArea())
        .fullScreenCover(item: $destination, onDismiss: presentationDismissed) { route in
            switch route {
            case .beautify: PhotoSelectionFlowView(maximumSelection: 1)
            case .collage: PhotoSelectionFlowView(maximumSelection: 4)
            case .privacy: LegacyPrivacyScreen()
            }
        }
    }

    private func showBeautify() {
        PickerEntryDiagnostics.record("app-beautify-tap")
        destination = .beautify
    }
    private func showCollage() {
        PickerEntryDiagnostics.record("app-collage-tap")
        destination = .collage
    }
    private func showPrivacy() { destination = .privacy }
    private func presentationDismissed() {
        PickerEntryDiagnostics.record("root-cover-dismissal-completed")
    }
}

/// Values taken directly from the shipped UIKit Entrance and IconButton.
/// Keep them shared with geometry tests rather than approximating the old design.
enum PhoneEntryStyle {
    static let iconSide: CGFloat = 62.5
    static let iconTitleSpacing: CGFloat = 35
    static let titleHorizontalInset: CGFloat = 12
    static let secondaryOpacity: Double = 0.7
    static let separatorThickness: CGFloat = 1
    static let separatorFraction: CGFloat = 0.65
    static let footerHorizontalInset: CGFloat = 16
    static let footerBottomInset: CGFloat = 4
    static let footerGap: CGFloat = 4
    static let footerVerticalPadding: CGFloat = 8
    static let minimumFooterHeight: CGFloat = 44
}

/// Constant-time layout only. Image decoding, file IO and Photos are absent.
struct PhoneEntryGeometry {
    let size: CGSize
    let horizontal: Bool

    static func isHorizontal(safeSize: CGSize, insets: EdgeInsets) -> Bool {
        // The UIKit rule uses the whole hosting view rather than its inset area.
        safeSize.width + insets.leading + insets.trailing > safeSize.height + insets.top + insets.bottom
    }

    func actionFrame(at index: Int) -> CGRect {
        precondition(index == 0 || index == 1)
        if horizontal {
            return CGRect(x: CGFloat(index) * size.width / 2, y: 0,
                          width: size.width / 2, height: size.height)
        }
        return CGRect(x: 0, y: CGFloat(index) * size.height / 2,
                      width: size.width, height: size.height / 2)
    }

    var separatorFrame: CGRect {
        let width = horizontal ? PhoneEntryStyle.separatorThickness : size.width * PhoneEntryStyle.separatorFraction
        let height = horizontal ? size.height * PhoneEntryStyle.separatorFraction : PhoneEntryStyle.separatorThickness
        return CGRect(x: (size.width - width) / 2, y: (size.height - height) / 2,
                      width: width, height: height)
    }
}

private struct PhoneEntryActions: View {
    let horizontal: Bool
    let beautify: () -> Void
    let collage: () -> Void

    var body: some View {
        GeometryReader { geometry in
            let layout = PhoneEntryGeometry(size: geometry.size, horizontal: horizontal)
            let first = layout.actionFrame(at: 0)
            let second = layout.actionFrame(at: 1)
            let separator = layout.separatorFrame
            ZStack(alignment: .topLeading) {
                PhoneEntryButton(title: tr(.beautify), image: "EditPhotoEntranceButton", identifier: "edit-photo", action: beautify)
                    .frame(width: first.width, height: first.height)
                    .position(x: first.midX, y: first.midY)
                PhoneEntryButton(title: tr(.collage), image: "CollageEntranceButton", identifier: "make-collage", action: collage)
                    .frame(width: second.width, height: second.height)
                    .position(x: second.midX, y: second.midY)
                Rectangle()
                    .fill(Color.white.opacity(PhoneEntryStyle.secondaryOpacity))
                    .frame(width: separator.width, height: separator.height)
                    .position(x: separator.midX, y: separator.midY)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("phone-entry-primary-area")
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
            VStack(spacing: PhoneEntryStyle.iconTitleSpacing) {
                Image(image)
                    .renderingMode(.template)
                    .resizable()
                    .scaledToFit()
                    .frame(width: PhoneEntryStyle.iconSide, height: PhoneEntryStyle.iconSide)
                    .foregroundColor(Color.white.opacity(PhoneEntryStyle.secondaryOpacity))
                    .accessibilityHidden(true)
                Text(title)
                    .font(.body)
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, PhoneEntryStyle.titleHorizontalInset)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
        .accessibilityLabel(title)
    }
}

private struct PhonePrivacyButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(NSLocalizedString("Privacy Policy", comment: "Privacy entry"))
                .font(.footnote)
                .foregroundColor(Color.white.opacity(PhoneEntryStyle.secondaryOpacity))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.vertical, PhoneEntryStyle.footerVerticalPadding)
                .frame(maxWidth: .infinity, minHeight: PhoneEntryStyle.minimumFooterHeight)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("privacy-policy")
        .accessibilityHint(NSLocalizedString("Shows the privacy policy offline.", comment: "Privacy entry hint"))
    }
}
