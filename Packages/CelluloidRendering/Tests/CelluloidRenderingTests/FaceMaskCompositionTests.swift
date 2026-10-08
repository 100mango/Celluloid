import XCTest
import CoreImage
import CoreGraphics
import CelluloidDomain
@testable import CelluloidRendering

final class FaceMaskCompositionTests: XCTestCase {
    func testControlledNonemptyFaceMasksComposeAndLeaveOutsidePixelsUntouched() throws {
        let extent = CGRect(x: 0, y: 0, width: 600, height: 400)
        let input = try XCTUnwrap(CIFilter(name: "CICheckerboardGenerator", parameters: [
            "inputColor0": CIColor(red: 1, green: 0.1, blue: 0.3),
            "inputColor1": CIColor(red: 0.1, green: 0.7, blue: 1),
            "inputWidth": 3.0, "inputSharpness": 1.0
        ])?.outputImage).cropped(to: extent)
        let faces = [CGRect(x: 80, y: 80, width: 70, height: 90), CGRect(x: 380, y: 230, width: 80, height: 90)]
        let renderer = RecipeRenderer(faceRegions: { _ in faces })
        let output = try renderer.apply(.pixellateFace, to: input)
        let context = CIContext()
        func region(_ image: CIImage, _ rect: CGRect) -> [UInt8] {
            var bytes = [UInt8](repeating: 0, count: Int(rect.width * rect.height) * 4)
            bytes.withUnsafeMutableBytes { context.render(image, toBitmap: $0.baseAddress!, rowBytes: Int(rect.width) * 4,
                                                          bounds: rect, format: .RGBA8, colorSpace: RasterCodec.colorSpace) }
            return bytes
        }
        for face in faces {
            let inside = CGRect(x: face.midX - 10, y: face.midY - 10, width: 20, height: 20)
            XCTAssertNotEqual(region(output, inside), region(input, inside))
        }
        let outside = CGRect(x: 240, y: 320, width: 20, height: 20)
        XCTAssertEqual(region(output, outside), region(input, outside))
        XCTAssertEqual(output.extent, extent)
        let noFaces = try RecipeRenderer(faceRegions: { _ in [] }).apply(.pixellateFace, to: input)
        XCTAssertTrue(noFaces === input)
        print("FACE_MASK_CONTROLLED passed geometry-only seam; no detector/hardware claim")
    }
}
