//
//  Filter.swift
//  Celluloid
//
//  Created by Mango on 16/3/30.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

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
