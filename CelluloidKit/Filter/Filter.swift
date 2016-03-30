//
//  Filter.swift
//  Celluloid
//
//  Created by Mango on 16/3/30.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import CoreImage

public typealias Filter = CIImage -> CIImage
private let context = CIContext()

public struct Filters {
    public static  func Sepia() -> Filter {
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
}



extension UIImage {
    public func filteredImage(filter: Filter) -> UIImage {
        let inputImage = self.CIImage ?? CoreImage.CIImage(CGImage: self.CGImage!)
        let outputImage = filter(inputImage)
        let cgImage = context.createCGImage(outputImage, fromRect: inputImage.extent)
        return UIImage(CGImage: cgImage)
    }
}
