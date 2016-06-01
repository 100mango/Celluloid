//
//  Filter.swift
//  Celluloid
//
//  Created by Mango on 16/3/30.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import ImageIO

public typealias Filter = CIImage -> CIImage

infix operator >>> { associativity left }
func >>> (filter1: Filter, filter2: Filter) -> Filter {
    return { image in filter2(filter1(image)) }
}

public enum FilterType: String {
    case Original
    case Sepia
    case Chrome
    case Fade
    case Invert
    case Posterize
    case Sketch
    case Comic
    case Crystal
    case PixellateFace
}

public struct Filters {
    
    public static func filter(type: FilterType) -> Filter {
        switch type {
        case .Sepia, .Original:
            return sepia
        case .Chrome:
            return chrome
        case .Fade:
            return fade
        case .Invert:
            return invert
        case .Posterize:
            return posterize
        case .Sketch:
            return sketch
        case .Comic:
            return comic
        case .Crystal:
            return crystal
        case .PixellateFace:
            return pixellateFace()
        }
    }
    
    private static func simpleFilter(name: String) -> Filter {
        return { image in
            let parameters = [kCIInputImageKey: image]
            guard let filter = CIFilter(name: name, withInputParameters: parameters) else {
                fatalError("no filter")
            }
            guard let outputImage = filter.outputImage else {
                fatalError("no output image")
            }
            return outputImage
        }
    }

    public static let sepia = Filters.simpleFilter("CISepiaTone")
    
    public static let chrome = Filters.simpleFilter("CIPhotoEffectChrome")
    
    public static let fade = Filters.simpleFilter("CIPhotoEffectInstant")
    
    public static let invert = Filters.simpleFilter("CIColorInvert")
    
    public static let posterize = Filters.simpleFilter("CIColorPosterize")
    
    public static let sketch = Filters.simpleFilter("CILineOverlay")
    
    public static let comic =  Filters.simpleFilter("CIComicEffect")
    
    public static let crystal = Filters.simpleFilter("CICrystallize")
    
    public static func pixellate() -> Filter {
        return { image in
            let parameters = [
                kCIInputImageKey: image,
                "inputScale": max(image.extent.width, image.extent.height)/60
            ]
            guard let filter = CIFilter(name: "CIPixellate", withInputParameters: parameters) else {
                fatalError("filter not found")
            }
            guard let outputImgae = filter.outputImage else { fatalError() }
            return outputImgae
        }
    }
    
    public static func sourceOver(inputImage: CIImage) -> Filter {
        return { image in
            let parameters = [
                kCIInputImageKey: inputImage,
                kCIInputBackgroundImageKey: image
            ]
            guard let filter = CIFilter(name: "CISourceOverCompositing", withInputParameters: parameters) else {
                fatalError("filter not found")
            }
            guard let outputImgae = filter.outputImage else { fatalError() }
            return outputImgae
        }
    }
    
    static func makeRadialGradientCImage(inputRadius0 inputRadius0: CGFloat,
                               inputRadius1: CGFloat,
                               inputColor0: CIColor,
                               inputColor1: CIColor,
                               inputCenter: CIVector) -> CIImage? {
        let parameters = ["inputRadius0": inputRadius0,
                          "inputRadius1": inputRadius1,
                          "inputColor0": inputColor0,
                          "inputColor1": inputColor1,
                          kCIInputCenterKey: inputCenter]
        let radialGradient = CIFilter(name: "CIRadialGradient", withInputParameters: parameters)
        return radialGradient?.outputImage
    }
    
    public static func pixellateFace() -> Filter {
        return { image in
            
            let detector = CIDetector(ofType: CIDetectorTypeFace, context: context, options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
            let faces = detector.featuresInImage(image)
            guard faces.count > 0 else {
                return image
            }
            
            let mask = faces.flatMap({ face in
                
                let radius = min(face.bounds.width, face.bounds.height / 1.5)
                return self.makeRadialGradientCImage(inputRadius0: radius,
                    inputRadius1:radius + 1,
                    inputColor0: CIColor(red: 0, green: 1, blue: 0, alpha: 1),
                    inputColor1: CIColor(red: 0, green: 0, blue: 0, alpha: 0),
                    inputCenter: CIVector(x: face.bounds.midX, y: face.bounds.midY))

            }).reduce(CIImage(), combine: { sourceOver($0)($1) })
            
            let pixellatedImage = pixellate()(image)
            
            if let blendImage = CIFilter(name: "CIBlendWithMask", withInputParameters: [
                kCIInputImageKey: pixellatedImage,
                kCIInputBackgroundImageKey: image,
                kCIInputMaskImageKey: mask
                ])?.outputImage {
                return blendImage
            }else{
                fatalError("no output image")
            }
        }
    }
    
    public static func blur(radius: Double) -> Filter {
        return { image in
            let parameters = [
                kCIInputRadiusKey: radius,
                kCIInputImageKey: image
            ]
            guard let filter = CIFilter(name: "CIGaussianBlur",
                                        withInputParameters: parameters) else { fatalError() }
            guard let outputImage = filter.outputImage else { fatalError() }
            return outputImage
        }
    }
    
    public static func blurAndSepia() -> Filter {
        return blur(5) >>> sepia
    }
}


private let context = CIContext()
extension UIImage {
    
    public func filteredImage(filter: Filter) -> UIImage {
        let inputImage = self.CIImage ?? CoreImage.CIImage(CGImage: self.CGImage!)
        let outputImage = filter(inputImage)
        let cgImage = context.createCGImage(outputImage, fromRect: inputImage.extent)
        return UIImage(CGImage: cgImage)
    }
    
    public func filteredImage(orientation: Int32, filter: Filter) -> UIImage {
        var inputImage = self.CIImage ?? CoreImage.CIImage(CGImage: self.CGImage!)
        inputImage = inputImage.imageByApplyingOrientation(orientation)
        let outputImage = filter(inputImage)
        let cgImage = context.createCGImage(outputImage, fromRect: inputImage.extent)
        return UIImage(CGImage: cgImage)
    }
}
