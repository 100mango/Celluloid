import Foundation

/// Template coordinates are the shipped top-left, 0...100 square coordinates.
/// Image ordering is significant and is never inferred from file names.
public struct TemplatePoint: Equatable, Sendable {
    public let x: Double
    public let y: Double
    public init(x: Double, y: Double) { self.x = x; self.y = y }
}

public struct CollageTemplate: Equatable, Sendable {
    public let assetName: String
    public let polygons: [[TemplatePoint]]
}

public enum TemplateError: Error, Equatable {
    case unsupportedImageCount
    case invalidTemplate(String)
}

public enum CollageTemplates {
    private struct RawTemplate: Decodable {
        let drawable_name: String
        let polygons: [[Double]]
    }

    /// Decode existing collage.json without UIKit and without force casts. This
    /// validates all requested templates atomically; malformed data never yields
    /// a partially different layout or silently removes one source image.
    public static func decode(_ data: Data, imageCount: Int) throws -> [CollageTemplate] {
        let key: String
        switch imageCount {
        case 2: key = "two_pic"
        case 3: key = "three_pic"
        case 4: key = "four_pic"
        default: throw TemplateError.unsupportedImageCount
        }
        let collection = try JSONDecoder().decode([String: [RawTemplate]].self, from: data)
        guard let templates = collection[key], !templates.isEmpty else {
            throw TemplateError.invalidTemplate(key)
        }
        var names = Set<String>()
        return try templates.map { raw in
            guard !raw.drawable_name.isEmpty,
                  raw.drawable_name.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_")).contains($0) }),
                  names.insert(raw.drawable_name).inserted,
                  raw.polygons.count == imageCount else {
                throw TemplateError.invalidTemplate(raw.drawable_name)
            }
            let polygons = try raw.polygons.map { values -> [TemplatePoint] in
                guard values.count >= 6, values.count.isMultiple(of: 2),
                      values.allSatisfy({ $0.isFinite && (0...100).contains($0) }) else {
                    throw TemplateError.invalidTemplate(raw.drawable_name)
                }
                let points = stride(from: 0, to: values.count, by: 2).map {
                    TemplatePoint(x: values[$0], y: values[$0 + 1])
                }
                let twiceArea = points.indices.reduce(0.0) { value, i in
                    let next = points[(i + 1) % points.count]
                    return value + points[i].x * next.y - next.x * points[i].y
                }
                guard abs(twiceArea) > 0 else { throw TemplateError.invalidTemplate(raw.drawable_name) }
                return points
            }
            return CollageTemplate(assetName: raw.drawable_name, polygons: polygons)
        }
    }
}
