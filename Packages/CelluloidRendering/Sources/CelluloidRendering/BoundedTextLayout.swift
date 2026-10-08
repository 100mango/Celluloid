import Foundation
import CoreGraphics
import CoreText

/// At most 17 shaping passes regardless of the requested font size. No truncated success.
/// Native recipes deliberately do not promise UIKit Photos-v1 text pixel equivalence.
struct BoundedTextLayout {
    let frame: CTFrame
    let fontSize: Double
    let shapingPasses: Int
    static let maximumSearchIterations = 14

    static func make(text: String, maximumFont: Double, rect: CGRect) throws -> Self {
        guard maximumFont.isFinite, maximumFont > 0, rect.width > 0, rect.height > 0,
              text.utf8.count <= 16_384 else { throw RenderError.textDoesNotFit }
        let upperBound = max(1, maximumFont)
        var passes = 0
        func create(_ size: Double, centered: Bool = false) throws -> CTFrame {
            try Task.checkCancellation()
            passes += 1
            let font = CTFontCreateUIFontForLanguage(.system, size, nil) ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
            var wrap = CTLineBreakMode.byCharWrapping
            var align: CTTextAlignment = centered ? .center : .left
            let paragraph = withUnsafePointer(to: &wrap) { wrapPointer in
                withUnsafePointer(to: &align) { alignPointer in
                    let settings = [
                        CTParagraphStyleSetting(spec: .lineBreakMode, valueSize: MemoryLayout<CTLineBreakMode>.size, value: wrapPointer),
                        CTParagraphStyleSetting(spec: .alignment, valueSize: MemoryLayout<CTTextAlignment>.size, value: alignPointer)
                    ]
                    return CTParagraphStyleCreate(settings, settings.count)
                }
            }
            let string = NSAttributedString(string: text, attributes: [
                NSAttributedString.Key(kCTFontAttributeName as String): font,
                NSAttributedString.Key(kCTForegroundColorAttributeName as String): CGColor(gray: 0, alpha: 1),
                NSAttributedString.Key(kCTParagraphStyleAttributeName as String): paragraph
            ])
            let setter = CTFramesetterCreateWithAttributedString(string as CFAttributedString)
            return CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), CGPath(rect: rect, transform: nil), nil)
        }
        func fits(_ frame: CTFrame) -> Bool { CTFrameGetVisibleStringRange(frame).length == (text as NSString).length }
        var best = try create(1)
        guard fits(best) else { throw RenderError.textDoesNotFit }
        var low = 1.0
        var high = upperBound
        let largest = try create(high)
        if fits(largest) { best = largest; low = high }
        else {
            for _ in 0..<maximumSearchIterations {
                if high - low <= 0.25 { break }
                let midpoint = (low + high) / 2
                let candidate = try create(midpoint)
                if fits(candidate) { best = candidate; low = midpoint }
                else { high = midpoint }
            }
        }
        if CFArrayGetCount(CTFrameGetLines(best)) == 1 { best = try create(low, centered: true) }
        guard fits(best) else { throw RenderError.textDoesNotFit }
        return Self(frame: best, fontSize: low, shapingPasses: passes)
    }
}
