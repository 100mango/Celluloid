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
    case PixellateFace
}

public struct Filters {
    
    public static func filter(type: FilterType) -> Filter {
        switch type {
        case .Sepia:
            return sepia()
        case .Chrome:
            return chrome()
        case .Fade:
            return fade()
        case .Invert:
            return invert()
        case .Posterize:
            return posterize()
        case .PixellateFace:
            return pixellateFace()
        default:
            return sepia()
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

    public static func sepia() -> Filter {
        return simpleFilter("CISepiaTone")
    }
    
    public static func chrome() -> Filter {
        return simpleFilter("CIPhotoEffectChrome")
    }
    
    public static func fade() -> Filter {
        return simpleFilter("CIPhotoEffectInstant")
    }
    
    public static func invert() -> Filter {
        return simpleFilter("CIColorInvert")
    }
    
    public static func posterize() -> Filter {
        return simpleFilter("CIColorPosterize")
    }
    
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
    
    public static func pixellateFace() -> Filter {
        return { image in
            
            let detector = CIDetector(ofType: CIDetectorTypeFace, context: context, options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
            let faces = detector.featuresInImage(image)
            guard faces.count > 0 else {
                return image
            }
            var maskImage: CIImage?
            faces.forEach{ face in
                let radius = min(face.bounds.width, face.bounds.height / 1.5)
                let parameters = ["inputRadius0": radius,
                    "inputRadius1": radius + 1,
                    "inputColor0": CIColor(red: 0, green: 1, blue: 0, alpha: 1),
                    "inputColor1": CIColor(red: 0, green: 0, blue: 0, alpha: 0),
                    kCIInputCenterKey: CIVector(x: face.bounds.midX, y: face.bounds.midY)]
                let radialGradient = CIFilter(name: "CIRadialGradient", withInputParameters: parameters)
                if let circleImage = radialGradient?.outputImage {
                    if let oldMaskImage = maskImage {
                        maskImage = sourceOver(circleImage)(oldMaskImage)
                    }else{
                        maskImage = circleImage
                    }
                }
            }
            guard let mask = maskImage else {
                return image
            }
            
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
        return blur(5) >>> sepia()
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
}
