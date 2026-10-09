import CelluloidKit
import SwiftUI
import UIKit

/// SwiftUI owns the saved route and presentation. Only the system activity
/// controller crosses into UIKit; the saved screen retains its original design.
@MainActor
struct CelluloidSavedPhotoView: View {
    let image: UIImage
    let onDone: () -> Void
    @State private var shareRequest: CelluloidPhotoShareRequest?

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 16) {
                    Image("saved")
                        .resizable()
                        .scaledToFit()
                        .frame(height: 48)
                        .accessibilityHidden(true)
                    Text(tr(.saved))
                        .font(.title3)
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("photo-saved")
                    VStack(spacing: 12) {
                        CelluloidSavedPhotoButton(title: tr(.share), action: share)
                            .accessibilityIdentifier("share-photo")
                        CelluloidSavedPhotoButton(title: tr(.done), action: onDone)
                            .accessibilityIdentifier("share-done")
                    }
                }
                .frame(maxWidth: 360)
                .padding(16)
                .frame(maxWidth: .infinity, minHeight: geometry.size.height)
            }
        }
        .background(Color(UIColor.blackBackgroundColor).ignoresSafeArea())
        .sheet(item: $shareRequest) { request in
            CelluloidSystemShareSheet(image: request.image)
        }
    }

    private func share() {
        shareRequest = CelluloidPhotoShareRequest(image: image)
    }
}

private struct CelluloidSavedPhotoButton: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            // Measure both titles in each label to match the original equal-height
            // action stack even when just one localized title wraps at large type.
            ZStack {
                Text(tr(.share)).hidden().accessibilityHidden(true)
                Text(tr(.done)).hidden().accessibilityHidden(true)
                Text(title)
            }
            .font(.body)
            .foregroundColor(.white)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 44)
            .contentShape(RoundedRectangle(cornerRadius: 22))
            .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct CelluloidPhotoShareRequest: Identifiable {
    let id = UUID()
    let image: UIImage
}

/// The system activity UI is the only share interoperability shell.
private struct CelluloidSystemShareSheet: UIViewControllerRepresentable {
    let image: UIImage

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [image], applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
