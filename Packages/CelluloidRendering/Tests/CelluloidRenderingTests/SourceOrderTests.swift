import XCTest
import CoreGraphics
import CelluloidDomain
@testable import CelluloidRendering

final class SourceOrderTests: XCTestCase {
    func testRenderedFourPhotoReorderAndRemovalPreserveActualSourcePixels() throws {
        let colors: [[CGFloat]] = [[1,0,0,1],[0,1,0,1],[0,0,1,1],[1,1,0,1]]
        let expected: [[UInt8]] = [[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,255,0,255]]
        var recipe = EditRecipe(), data: [UUID: Data] = [:], role: [UUID: Int] = [:]
        for index in colors.indices {
            let bitmap = try RasterCodec.bitmap(width: 80, height: 60)
            bitmap.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: colors[index])))
            bitmap.fill(CGRect(x: 0, y: 0, width: 80, height: 60))
            let bytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
            let source = try RasterCodec.metadata(bytes)
            recipe.sources.append(source); data[source.id] = bytes; role[source.id] = index
        }
        let sourceOrder = recipe.sources
        for order in [[0,1],[0,1,2],[0,1,2,3],[3,2,1,0],[3,1]] {
            recipe.sources = order.map { sourceOrder[$0] }
            let template = try XCTUnwrap(NativeResources.templates(count: order.count).first)
            recipe.collageTemplate = template.assetName
            let image = try RecipeRenderer().render(recipe, sources: data)
            for index in recipe.sources.indices {
                // Find a point at least two normalized units inside this visible layer and
                // outside subsequent overlapping layers. Coordinates are top-left here.
                let point = try XCTUnwrap(interiorPoint(index, polygons: template.polygons))
                let cropped = try XCTUnwrap(image.cropping(to: CGRect(x: Int(point.x * 8), y: Int(point.y * 8), width: 1, height: 1)))
                let pixel = try RasterCodec.bitmap(width: 1, height: 1)
                pixel.draw(cropped, in: CGRect(x: 0, y: 0, width: 1, height: 1))
                let bytes = Array(UnsafeBufferPointer(start: try XCTUnwrap(pixel.data).assumingMemoryBound(to: UInt8.self), count: 4))
                XCTAssertEqual(bytes, expected[try XCTUnwrap(role[recipe.sources[index].id])], "Order \(order), position \(index)")
            }
        }
    }
    private func interiorPoint(_ index: Int, polygons: [[TemplatePoint]]) -> TemplatePoint? {
        for y in stride(from: 5.0, to: 95.0, by: 5) {
            for x in stride(from: 5.0, to: 95.0, by: 5) {
                let probes = [TemplatePoint(x:x,y:y),TemplatePoint(x:x-2,y:y),TemplatePoint(x:x+2,y:y),TemplatePoint(x:x,y:y-2),TemplatePoint(x:x,y:y+2)]
                if probes.allSatisfy({ inside($0, polygon: polygons[index]) }) && polygons.dropFirst(index+1).allSatisfy({ polygon in probes.allSatisfy { !inside($0, polygon: polygon) } }) { return probes[0] }
            }
        }
        return nil
    }
    private func inside(_ p: TemplatePoint, polygon: [TemplatePoint]) -> Bool {
        var result = false
        for i in polygon.indices {
            let a = polygon[i], b = polygon[(i+1) % polygon.count]
            if (a.y > p.y) != (b.y > p.y), p.x < (b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x { result.toggle() }
        }
        return result
    }
}
