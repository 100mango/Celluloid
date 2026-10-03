import XCTest
@testable import CelluloidDomain

final class LocalizationTests: XCTestCase {
    func testFriendlyLabelsDoNotChangeStoredIdentifiers() throws {
        XCTAssertEqual(FilterPreset.pixellateFace.rawValue, "PixellateFace")
        XCTAssertEqual(FilterPreset.fade.coreImageFilterName, "CIPhotoEffectInstant")
        XCTAssertEqual(FilterPreset.pixellateFace.localizedTitle, "Face Pixelation")
        XCTAssertEqual(BubbleAsset.say1.rawValue, "say1")
        XCTAssertEqual(BubbleAsset.say1.localizedTitle, "Speech 1")
        let data = try JSONEncoder().encode(FilterPreset.pixellateFace)
        XCTAssertEqual(String(data: data, encoding: .utf8), "\"PixellateFace\"")
    }
}
