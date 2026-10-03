import XCTest
import UIKit
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class AdaptiveInterfaceTests: XCTestCase {
    func testShareDismissalFitsCompactLandscapeAndBothAppearances() {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 10, height: 10)).image { _ in }
        for style in [UIUserInterfaceStyle.light, .dark] {
            for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
                let traits = UITraitCollection(preferredContentSizeCategory: category)
                let share = SharePhotoViewController(image: image)
                share.overrideUserInterfaceStyle = style
                share.loadViewIfNeeded()
                share.savedLabel.font = .preferredFont(forTextStyle: .title3, compatibleWith: traits)
                share.shareButton.titleLabel?.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                share.doneButton.titleLabel?.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                for size in [CGSize(width: 320, height: 568), CGSize(width: 568, height: 320),
                             CGSize(width: 375, height: 667), CGSize(width: 667, height: 375),
                             CGSize(width: 744, height: 1133), CGSize(width: 1133, height: 744),
                             CGSize(width: 1032, height: 1376)] {
                    share.view.frame = CGRect(origin: .zero, size: size)
                    share.view.setNeedsLayout()
                    share.view.layoutIfNeeded()
                    share.viewDidLayoutSubviews()
                    share.view.layoutIfNeeded()
                    let done = share.doneButton.convert(share.doneButton.bounds, to: share.view)
                    let action = share.shareButton.convert(share.shareButton.bounds, to: share.view)
                    XCTAssertTrue(share.view.bounds.insetBy(dx: -1, dy: -1).contains(done), "Done is offscreen at \(size), \(category), \(style)")
                    XCTAssertTrue(share.view.bounds.insetBy(dx: -1, dy: -1).contains(action))
                    XCTAssertGreaterThanOrEqual(done.height, 44)
                    XCTAssertGreaterThanOrEqual(action.height, 44)
                    XCTAssertFalse(done.intersects(action))
                    XCTAssertGreaterThan(contrast(.white, .blackBackgroundColor, style: style), 4.5)
                }
            }
        }
    }

    func testBubbleArtworkTextHasIdenticalReadablePixelsInLightAndDark() {
        var model = BubbleModel.bubbles[0]
        model.content = "Test"
        var renders: [Data] = []
        for style in [UIUserInterfaceStyle.light, .dark] {
            let label = BubbleLabel(model: model)
            label.overrideUserInterfaceStyle = style
            label.frame = CGRect(x: 0, y: 0, width: 120, height: 44)
            label.backgroundColor = .white
            label.font = .systemFont(ofSize: 24)
            label.layoutIfNeeded()
            XCTAssertGreaterThan(contrast(label.textColor, .white, style: style), 7)
            renders.append(label.render().pngData()!)
            let editor = EditBubbleViewController(bubbleModel: model)
            editor.overrideUserInterfaceStyle = style
            editor.loadViewIfNeeded()
            let text = editor.view.subviews.compactMap { $0 as? UITextView }.first!
            XCTAssertGreaterThan(contrast(text.textColor!, text.backgroundColor!, style: style), 7)
        }
        XCTAssertEqual(renders[0], renders[1], "Host appearance must not recolor text in exported bubble artwork")
    }

    func testPhotoStatusBackdropUsesExplicitNavigationAndToolbarInsets() {
        let backdrop = PhotoPickerStateBackground()
        backdrop.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        backdrop.occlusionInsets = UIEdgeInsets(top: 74, left: 0, bottom: 86, right: 0)
        backdrop.layoutIfNeeded()
        XCTAssertEqual(backdrop.scrollView.frame, CGRect(x: 0, y: 74, width: 375, height: 507))
        backdrop.frame.size = CGSize(width: 667, height: 375)
        backdrop.occlusionInsets = UIEdgeInsets(top: 32, left: 0, bottom: 64, right: 0)
        backdrop.layoutIfNeeded()
        XCTAssertEqual(backdrop.scrollView.frame, CGRect(x: 0, y: 32, width: 667, height: 279))
    }

    func testBubbleFontFittingPreservesSystemFontFamily() {
        var model = BubbleModel.bubbles[0]
        model.content = "Hello 世界"
        let label = BubbleLabel(model: model)
        let family = label.font.familyName
        let holder = UIImageView(image: model.bubbleImage)
        holder.frame = CGRect(x: 0, y: 0, width: 160, height: 120)
        holder.contentMode = .scaleAspectFit
        holder.addSubview(label)
        label.adjustFrame()
        XCTAssertEqual(label.font.familyName, family)
        XCTAssertGreaterThan(label.font.pointSize, 0)
        XCTAssertLessThanOrEqual(label.font.pointSize, 16)
    }

    func testFullLocalizedTitlesFitAtNormalAndLargestTextAcrossViewports() throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 2, height: 2)).image { _ in }
        let sizes = [CGSize(width: 320, height: 568), CGSize(width: 568, height: 320),
                     CGSize(width: 375, height: 667), CGSize(width: 667, height: 375),
                     CGSize(width: 440, height: 956), CGSize(width: 956, height: 440),
                     CGSize(width: 744, height: 1133), CGSize(width: 1133, height: 744),
                     CGSize(width: 1032, height: 1376), CGSize(width: 1376, height: 1032)]
        for language in ["en", "zh-Hans"] {
            let kitURL = try XCTUnwrap(Bundle(for: BubbleLabel.self).url(forResource: language, withExtension: "lproj"))
            let kit = try XCTUnwrap(Bundle(url: kitURL))
            // English app strings use their source keys; Chinese has a resource table.
            let chineseURL = try XCTUnwrap(Bundle(for: EntranceViewController.self).url(forResource: "zh-Hans", withExtension: "lproj"))
            let chinese = try XCTUnwrap(Bundle(url: chineseURL))
            func appTitle(_ key: String) -> String {
                language == "en" ? key : chinese.localizedString(forKey: key, value: nil, table: nil)
            }
            for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
                let traits = UITraitCollection(preferredContentSizeCategory: category)
                let home = EntranceViewController()
                home.loadViewIfNeeded()
                home.editPhotoButton.label.text = kit.localizedString(forKey: "beautify", value: nil, table: nil)
                home.makeCollageButton.label.text = kit.localizedString(forKey: "collage", value: nil, table: nil)
                home.editPhotoButton.label.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                home.makeCollageButton.label.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                home.privacyPolicyButton.setTitle(appTitle("Privacy Policy"), for: .normal)
                home.privacyPolicyButton.titleLabel?.font = .preferredFont(forTextStyle: .footnote, compatibleWith: traits)
                let share = SharePhotoViewController(image: image)
                share.loadViewIfNeeded()
                share.shareButton.setTitle(kit.localizedString(forKey: "share", value: nil, table: nil), for: .normal)
                share.doneButton.setTitle(kit.localizedString(forKey: "done", value: nil, table: nil), for: .normal)
                share.savedLabel.text = kit.localizedString(forKey: "saved", value: nil, table: nil)
                share.shareButton.titleLabel?.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                share.doneButton.titleLabel?.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                share.savedLabel.font = .preferredFont(forTextStyle: .title3, compatibleWith: traits)
                let picker = PhotoPickerViewController(maximumSelection: 4) { _ in }
                picker.loadViewIfNeeded()
                picker.manageButton.isHidden = false
                picker.manageButton.setTitle(appTitle("Manage Photos"), for: .normal)
                picker.manageButton.titleLabel?.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
                for size in sizes {
                    for controller in [home as UIViewController, share, picker] {
                        controller.view.frame = CGRect(origin: .zero, size: size)
                        controller.view.setNeedsLayout()
                        controller.view.layoutIfNeeded()
                        controller.viewDidLayoutSubviews()
                        controller.view.layoutIfNeeded()
                    }
                    assertFullTitle(home.editPhotoButton.label, within: home.editPhotoButton)
                    assertFullTitle(home.makeCollageButton.label, within: home.makeCollageButton)
                    assertFullTitle(try XCTUnwrap(home.privacyPolicyButton.titleLabel), within: home.privacyPolicyButton)
                    assertFullTitle(try XCTUnwrap(share.shareButton.titleLabel), within: share.shareButton)
                    assertFullTitle(try XCTUnwrap(share.doneButton.titleLabel), within: share.doneButton)
                    assertFullTitle(share.savedLabel, within: share.view)
                    assertFullTitle(try XCTUnwrap(picker.manageButton.titleLabel), within: picker.manageButton)
                    XCTAssertGreaterThanOrEqual(picker.manageButton.bounds.height, 44)
                    XCTAssertLessThanOrEqual(picker.collectionView.frame.maxY, picker.manageButton.frame.minY)
                }
            }
        }
    }

    func testSavedScreenHidesItsUnusedNativeToolbarAfterLayout() {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 2, height: 2)).image { _ in }
        let share = SharePhotoViewController(image: image)
        let navigation = UINavigationController(rootViewController: share)
        navigation.loadViewIfNeeded()
        for size in [CGSize(width: 440, height: 956), CGSize(width: 956, height: 440)] {
            navigation.view.frame = CGRect(origin: .zero, size: size)
            navigation.setToolbarHidden(false, animated: false)
            navigation.toolbar.isHidden = false
            navigation.toolbar.accessibilityElementsHidden = false
            share.viewDidLayoutSubviews()
            XCTAssertTrue(navigation.isToolbarHidden)
            XCTAssertTrue(navigation.toolbar.isHidden)
            XCTAssertTrue(navigation.toolbar.accessibilityElementsHidden)
            XCTAssertFalse(share.shareButton.isHidden)
            XCTAssertFalse(share.doneButton.isHidden)
        }
    }

    private func assertFullTitle(_ label: UILabel, within container: UIView,
                                 file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(label.text?.isEmpty ?? true, file: file, line: line)
        XCTAssertGreaterThan(label.bounds.width, 0, file: file, line: line)
        let fullText = label.sizeThatFits(CGSize(width: label.bounds.width, height: .greatestFiniteMagnitude))
        XCTAssertGreaterThanOrEqual(label.bounds.height + 1, ceil(fullText.height),
                                   "Full title is vertically clipped: \(label.text ?? "")", file: file, line: line)
        XCTAssertGreaterThanOrEqual(label.bounds.width + 1, ceil(fullText.width),
                                   "Full title is horizontally clipped: \(label.text ?? "")", file: file, line: line)
        let visibleTitle = label.convert(label.bounds, to: container)
        XCTAssertTrue(container.bounds.insetBy(dx: -1, dy: -1).contains(visibleTitle),
                      "Title escapes its actual control: \(label.text ?? "")", file: file, line: line)
    }

    private func contrast(_ foreground: UIColor, _ background: UIColor, style: UIUserInterfaceStyle) -> CGFloat {
        func luminance(_ color: UIColor) -> CGFloat {
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            color.resolvedColor(with: UITraitCollection(userInterfaceStyle: style)).getRed(&r, green: &g, blue: &b, alpha: &a)
            func linear(_ component: CGFloat) -> CGFloat { component <= 0.04045 ? component / 12.92 : pow((component + 0.055) / 1.055, 2.4) }
            return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
        }
        let a = luminance(foreground), b = luminance(background)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }
}
