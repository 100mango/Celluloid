import XCTest
import SwiftUI
@testable import Celluloid

final class PhoneEntryDesignTests: XCTestCase {
    func testOriginalUIKitStyleMeasurementsAreRetained() {
        XCTAssertEqual(PhoneEntryStyle.iconSide, 62.5)
        XCTAssertEqual(PhoneEntryStyle.iconTitleSpacing, 35)
        XCTAssertEqual(PhoneEntryStyle.titleHorizontalInset, 12)
        XCTAssertEqual(PhoneEntryStyle.secondaryOpacity, 0.7)
        XCTAssertEqual(PhoneEntryStyle.separatorThickness, 1)
        XCTAssertEqual(PhoneEntryStyle.separatorFraction, 0.65)
        XCTAssertEqual(PhoneEntryStyle.footerHorizontalInset, 16)
        XCTAssertEqual(PhoneEntryStyle.footerBottomInset, 4)
        XCTAssertEqual(PhoneEntryStyle.footerGap, 4)
        XCTAssertEqual(PhoneEntryStyle.footerVerticalPadding, 8)
        XCTAssertEqual(PhoneEntryStyle.minimumFooterHeight, 44)
    }

    func testEqualPrimaryRegionsTileTheEntireAvailableArea() {
        let safeSizes = [CGSize(width: 320, height: 516), CGSize(width: 568, height: 299),
                         CGSize(width: 393, height: 759), CGSize(width: 744, height: 1061),
                         CGSize(width: 1133, height: 692), CGSize(width: 1376, height: 960)]
        let footerHeights: [CGFloat] = [44, 80, 120]
        for safe in safeSizes {
            for footerHeight in footerHeights {
                let mainSize = CGSize(width: safe.width, height: safe.height - footerHeight - 8)
                for horizontal in [false, true] {
                    let geometry = PhoneEntryGeometry(size: mainSize, horizontal: horizontal)
                    let first = geometry.actionFrame(at: 0)
                    let second = geometry.actionFrame(at: 1)
                    XCTAssertEqual(first.size, second.size)
                    XCTAssertEqual(first.union(second), CGRect(origin: .zero, size: mainSize))
                    let overlap = first.intersection(second)
                    XCTAssertTrue(overlap.isNull || overlap.width == 0 || overlap.height == 0,
                                  "The two buttons must abut without a positive-area overlap")
                    if horizontal {
                        XCTAssertEqual(first.maxX, second.minX)
                        XCTAssertEqual(first.height, mainSize.height)
                    } else {
                        XCTAssertEqual(first.maxY, second.minY)
                        XCTAssertEqual(first.width, mainSize.width)
                    }
                }
            }
        }
    }

    func testSeparatorUsesSettledLegacyFractionRatherThanInitialFixedWidth() {
        for horizontal in [false, true] {
            let geometry = PhoneEntryGeometry(size: CGSize(width: 744, height: 1009), horizontal: horizontal)
            let line = geometry.separatorFrame
            XCTAssertEqual(line.midX, 372)
            XCTAssertEqual(line.midY, 504.5)
            XCTAssertEqual(line.width, horizontal ? 1 : 744 * 0.65, accuracy: 0.0001)
            XCTAssertEqual(line.height, horizontal ? 1009 * 0.65 : 1, accuracy: 0.0001)
        }
    }

    func testOrientationUsesWholeViewportIncludingSafeInsets() {
        XCTAssertFalse(PhoneEntryGeometry.isHorizontal(safeSize: CGSize(width: 393, height: 759),
            insets: EdgeInsets(top: 59, leading: 0, bottom: 34, trailing: 0)))
        XCTAssertTrue(PhoneEntryGeometry.isHorizontal(safeSize: CGSize(width: 734, height: 372),
            insets: EdgeInsets(top: 0, leading: 59, bottom: 21, trailing: 59)))
        // Near-square window: the safe region alone is wider, but the original
        // hosting-view rule is portrait after restoring its top/bottom insets.
        XCTAssertFalse(PhoneEntryGeometry.isHorizontal(safeSize: CGSize(width: 600, height: 580),
            insets: EdgeInsets(top: 24, leading: 0, bottom: 20, trailing: 0)))
    }
}
