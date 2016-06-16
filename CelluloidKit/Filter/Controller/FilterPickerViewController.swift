//
//  FilterPickerViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/17.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public protocol FilterPickerViewControllerDelegate: class {
    func filterPickerViewController(filterPickerViewController: FilterPickerViewController, didSelectFilter filter: FilterType)
}

public class FilterPickerViewController: BasePickerController {
    
    //MARK: Property
    public weak var delegate: FilterPickerViewControllerDelegate?
    
    //MARK: View life cycle
    public override func viewDidLoad() {
        super.viewDidLoad()
        
        self.navigationItem.title = tr(.Filter)
    }
    
}

//MARK: CollectionView Data Source

extension FilterPickerViewController {
    
    public override func collectionView(collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return FilterCellType.Count.rawValue
    }
    
    public override func collectionView(collectionView: UICollectionView, cellForItemAtIndexPath indexPath: NSIndexPath) -> UICollectionViewCell {
        return makeFilterCell(indexPath)
    }
    
}

private enum FilterCellType: Int {
    case Original
    case Sepia
    //case Chrome
    //case Fade
    //case Invert
    case Posterize
    //case Sketch
    //case Comic
    case Crystal
    case PixellateFace
    case Count
}

private extension FilterPickerViewController {
    
    func makeFilterCell(indexPath: NSIndexPath) ->  UICollectionViewCell {
        let cell = collectionView.dequeueReusableCellWithReuseIdentifier(UICollectionViewCell.defaultReuseIdentifier, forIndexPath: indexPath)
        cell.backgroundColor = .cellLightPurple
        cell.contentView.subviews.forEach {
            $0.removeFromSuperview()
        }
        
        let imageView = UIImageView()
        imageView.size = cell.size
        cell.contentView.addSubview(imageView)
        
        if let cellType = FilterCellType(rawValue: indexPath.row){
            switch cellType {
                
            case .Original:
                imageView.image = UIImage(asset: .OriginalFilter)
            case .Sepia:
                imageView.image = UIImage(asset: .OldPictureFilter)
            //case .Chrome:
            //    imageView.image = UIImage(asset: .Chrome)
            //case .Fade:
            //    imageView.image = UIImage(asset: .Instant)
            //case .Invert:
            //    imageView.image = UIImage(asset: .Invert)
            case .Posterize:
                imageView.image = UIImage(asset: .PosterizeFilter)
            case .PixellateFace:
                imageView.image = UIImage(asset: .PixellateFaceFilter)
            //case .Sketch,.Comic:
            //    imageView.image = UIImage(asset: .Posterize)
            case .Crystal:
                imageView.image = UIImage(asset: .CrystalFilter)
            case .Count:
                break
            }
        }
        return cell
    }
}


//MARK: CollectionView delegate

extension FilterPickerViewController {
    public func collectionView(collectionView: UICollectionView, didSelectItemAtIndexPath indexPath: NSIndexPath) {
        if let type = FilterCellType(rawValue: indexPath.row) {
            handleSelectFilter(type)
        }
    }
}

private extension FilterPickerViewController {
    func handleSelectFilter(type: FilterCellType) {
        
        switch type {
            
        case .Original:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Original)
        case .Sepia:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Sepia)
            /*
        case .Chrome:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Chrome)
        case .Fade:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Fade)
        case .Invert:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Invert)
            */
        case .Posterize:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Posterize)
            /*
        case .Sketch:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Sketch)
        case .Comic:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Comic)
             */
        case .PixellateFace:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .PixellateFace)
        case .Crystal:
            self.delegate?.filterPickerViewController(self, didSelectFilter: .Crystal)
        case .Count:
            break
        }
        
        dismissViewControllerAnimated(true, completion: nil)
    }
}

