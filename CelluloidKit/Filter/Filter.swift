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

public struct Filters {

    public static func Sepia() -> Filter {
        return { image in
            let parameters = [kCIInputImageKey: image]
            guard let filter = CIFilter(name: "CISepiaTone", withInputParameters: parameters) else {
                fatalError()
            }
            guard let outputImage = filter.outputImage else {
                fatalError()
            }
            return outputImage
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
        return blur(5) >>> Sepia()
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
