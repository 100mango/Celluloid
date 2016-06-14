//
//  Assets.swift
//  Celluloid
//
//  Created by Mango on 16/2/29.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

let buddleIndentifier = "Mango.CelluloidKit"
let extensionBundle = NSBundle(identifier: buddleIndentifier)!

public extension UIImage {
    public enum Asset: String {
        
        //Bubble
        case Aside1 = "aside1"
        case Call1 = "call1"
        case Call2 = "call2"
        case Call3 = "call3"
        case Say1 = "say1"
        case Say2 = "say2"
        case Say3 = "say3"
        case Think1 = "think1"
        case Think2 = "think2"
        case Think3 = "think3"
        case Image_sticker_aside = "image_sticker_aside"
        case Image_sticker_call = "image_sticker_call"
        case Image_sticker_say = "image_sticker_say"
        case Image_sticker_think = "image_sticker_think"
        
        //Button
        case Btn_icon_back_normal = "btn_icon_back_normal"
        case Btn_icon_sticker_delete_normal = "btn_icon_sticker_delete_normal"
        case Btn_icon_sticker_delete_pressed = "btn_icon_sticker_delete_pressed"
        case Btn_icon_sticker_edit_normal = "btn_icon_sticker_edit_normal"
        case Btn_icon_sticker_edit_pressed = "btn_icon_sticker_edit_pressed"
        case Btn_icon_sticker_text_normal = "btn_icon_sticker_text_normal"
        case Btn_icon_sticker_text_pressed = "btn_icon_sticker_text_pressed"
        case Btn_icon_sticker_turn1_normal = "btn_icon_sticker_turn1_normal"
        case Btn_icon_sticker_turn1_pressed = "btn_icon_sticker_turn1_pressed"
        case Btn_icon_sticker_turn2_normal = "btn_icon_sticker_turn2_normal"
        case Btn_icon_sticker_turn2_pressed = "btn_icon_sticker_turn2_pressed"
        case BubbleButton = "bubbleButton"
        case FilterButton = "filterButton"
        case StickerButton = "stickerButton"
        
        //Filter
        case Image_icon_filter = "image_icon_filter"
        case CrystalFilter = "CrystalFilter"
        case OldPictureFilter = "OldPictureFilter"
        case OriginalFilter = "OriginalFilter"
        case PixellateFaceFilter = "PixellateFaceFilter"
        case PosterizeFilter = "PosterizeFilter"
        
        public var image: UIImage {
            return UIImage(asset: self)
        }
    }
    
    public convenience init!(asset: Asset) {
        let bundle = NSBundle(identifier: buddleIndentifier)
        self.init(named: asset.rawValue, inBundle: bundle, compatibleWithTraitCollection: nil)
    }
}
