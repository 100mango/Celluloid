import Foundation
import XCTest
@testable import CelluloidDomain

final class IdentityAndTemplateTests: XCTestCase {
    func testPersistedFilterNamesAndHistoricalFadeMapping() throws {
        XCTAssertEqual(FilterPreset.allCases.map(\.rawValue), ["Original", "Sepia", "Chrome", "Fade", "Invert", "Posterize", "Sketch", "Comic", "Crystal", "PixellateFace"])
        XCTAssertEqual(FilterPreset.fade.coreImageFilterName, "CIPhotoEffectInstant")
        for preset in FilterPreset.allCases {
            XCTAssertEqual(try JSONDecoder().decode(FilterPreset.self, from: JSONEncoder().encode(preset)), preset)
        }
        XCTAssertThrowsError(try JSONDecoder().decode(FilterPreset.self, from: Data("\"Unknown\"".utf8)))
    }

    func testAssetIdentitiesCannotEscapeBundledResources() throws {
        XCTAssertEqual(StickerAsset.all.map(\.rawValue), (32...54).map(String.init))
        XCTAssertEqual(BubbleAsset.allCases.map(\.rawValue), ["aside1", "call1", "call2", "call3", "say1", "say2", "say3", "think1", "think2", "think3"])
        for raw in ["031", "032", "31", "55", "../32", "32.png", "32.0", ""] {
            XCTAssertNil(StickerAsset(rawValue: raw))
            XCTAssertThrowsError(try JSONDecoder().decode(StickerAsset.self, from: JSONEncoder().encode(raw)))
        }
        for value in StickerAsset.all {
            XCTAssertEqual(try JSONDecoder().decode(StickerAsset.self, from: JSONEncoder().encode(value)), value)
        }
    }

    func testTemplateCoordinatesAndOrderArePreserved() throws {
        let json = #"{"two_pic":[{"drawable_name":"compose_2_4","polygons":[[0,0,61.67,0,41.67,100,0,100],[63.33,0,100,0,100,100,43.33,100]]}]}"#
        let templates = try CollageTemplates.decode(Data(json.utf8), imageCount: 2)
        XCTAssertEqual(templates.count, 1)
        XCTAssertEqual(templates[0].assetName, "compose_2_4")
        XCTAssertEqual(templates[0].polygons[0][2], TemplatePoint(x: 41.67, y: 100))
        XCTAssertEqual(templates[0].polygons[1][0], TemplatePoint(x: 63.33, y: 0))
    }

    func testInvalidTemplatesFailRatherThanDroppingAnImage() {
        let invalid = [
            #"{"two_pic":[]}"#,
            #"{"two_pic":[{"drawable_name":"../x","polygons":[[0,0,1,0,1,1],[0,0,1,0,1,1]]}]}"#,
            #"{"two_pic":[{"drawable_name":"x","polygons":[[0,0,1,0,1,1]]}]}"#,
            #"{"two_pic":[{"drawable_name":"x","polygons":[[0,0,1,0,1],[0,0,1,0,1,1]]}]}"#,
            #"{"two_pic":[{"drawable_name":"x","polygons":[[0,0,0,0,0,0],[0,0,1,0,1,1]]}]}"#,
            #"{"two_pic":[{"drawable_name":"x","polygons":[[0,0,101,0,1,1],[0,0,1,0,1,1]]}]}"#
        ]
        for json in invalid { XCTAssertThrowsError(try CollageTemplates.decode(Data(json.utf8), imageCount: 2)) }
        for count in [0, 1, 5] { XCTAssertThrowsError(try CollageTemplates.decode(Data("{}".utf8), imageCount: count)) }
    }
}
