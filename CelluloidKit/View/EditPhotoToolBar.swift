//
//  EditPhotoToolBar.swift
//  Celluloid
//
//  Created by Mango on 16/5/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import MZFormSheetPresentationController

public protocol EditPhotoToolBarDelegate: class {
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel)
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel)
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType)
}

open class EditPhotoToolBar: UIView {
    
    open weak var delegate: EditPhotoToolBarDelegate?
    
    fileprivate lazy var stackView: UIStackView = {
        let stackView = UIStackView()
        stackView.axis = .horizontal
        stackView.spacing = 0
        stackView.distribution = .fillEqually
        stackView.alignment = .center
        
        return stackView
    }()
    
    fileprivate lazy var filterButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .FilterButton), title: tr(.filter))
        item.addTarget(self, action: .touchFilterButton, for: .touchUpInside)
        return item
    }()
    
    fileprivate lazy var bubleButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .BubbleButton), title: tr(.bubble))
        item.addTarget(self, action: .touchBubbleButton, for: .touchUpInside)
        return item
    }()
    
    fileprivate lazy var stickerButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .StickerButton), title: tr(.sticker))
        item.addTarget(self, action: .touchStickerButton, for: .touchUpInside)
        return item
    }()
    
    fileprivate lazy var buttons: [EditPhotoToolBarItem] = [self.filterButton,self.bubleButton,self.stickerButton]
    
    //MARK: init
    fileprivate func commonInit() {
        self.backgroundColor = .alphaBlackColor
        
        self.addSubview(stackView)
        stackView.snp.makeConstraints  { (make) in
            make.edges.equalTo(stackView.superview!)
        }
        buttons.forEach { button in
            stackView.addArrangedSubview(button)
            button.snp.makeConstraints ({ (make) in
                make.height.equalTo(button.superview!)
            })
        }
        
    }
    
    public override init(frame: CGRect) {
        super.init(frame: frame)
        commonInit()
    }
    
    public required init?(coder aDecoder: NSCoder) {
        super.init(coder: aDecoder)
        commonInit()
    }
    
    //MARK: layout
    open override func layoutSubviews() {
    }
}

//MARK: Action
private extension Selector {
    static let touchFilterButton = #selector(EditPhotoToolBar.touchFilterButton)
    static let touchBubbleButton = #selector(EditPhotoToolBar.touchBubbleButton)
    static let touchStickerButton = #selector(EditPhotoToolBar.touchStickerButton)
}

private extension EditPhotoToolBar {
    @objc func touchFilterButton() {
        buttons.forEach { button in
            if button != filterButton {
                button.resetState()
            }
        }
        
        let filterPicker = FilterPickerViewController()
        filterPicker.delegate = self
        presentViewControllerFromSheet(filterPicker)
    }
    
    @objc func touchBubbleButton() {
        buttons.forEach { button in
            if button != bubleButton {
                button.resetState()
            }
        }
        
        let bubblePicker = BubblePickerViewController()
        bubblePicker.delegate = self
        presentViewControllerFromSheet(bubblePicker)
    }
    
    @objc func touchStickerButton() {
        buttons.forEach { button in
            if button != stickerButton {
                button.resetState()
            }
        }
        
        let stickerPicker = StickerPickerViewController()
        stickerPicker.delegate = self
        presentViewControllerFromSheet(stickerPicker)
    }
    
    func presentViewControllerFromSheet(_ vc: UIViewController) {
        let navigationVC = UINavigationController(rootViewController: vc)
        let formSheetController = MZFormSheetPresentationViewController(contentViewController: navigationVC)
        formSheetController.presentationController?.shouldUseMotionEffect = true
        formSheetController.presentationController?.shouldCenterVertically = true
        self.parentViewController?.present(formSheetController, animated: true, completion: nil)
    }
}

//MARK: BubblePickerViewControllerDelegate
extension EditPhotoToolBar: BubblePickerViewControllerDelegate {
    public func bubblePickerViewController(_ bubblePickerViewController: BubblePickerViewController, didSelectBubble bubble: BubbleModel) {
        self.delegate?.editPhotoToolBar(self, didSelectBubble: bubble)
    }
}

//MARK: StickerPickerViewControllerDelegate
extension EditPhotoToolBar: StickerPickerViewControllerDelegate {
    public func stickerPickerViewController(_ stickerPickerViewController: StickerPickerViewController, didSelectSticker sticker: StickerModel) {
        self.delegate?.editPhotoToolBar(self, didSelectSticker: sticker)
    }
}

//MARK: FilterPickerViewControllerDelegate
extension EditPhotoToolBar: FilterPickerViewControllerDelegate {
    public func filterPickerViewController(_ filterPickerViewController: FilterPickerViewController, didSelectFilter filter: FilterType) {
        self.delegate?.editPhotoToolBar(self, didSelectFilter: filter)
    }
}

//MARK: EditPhotoToolBarItem
private class EditPhotoToolBarItem: UIControl {
    
    let imageWidth = 22
    
    lazy var imageView: UIImageView = {
        let imageView = UIImageView()
        imageView.tintColor = .alphaWhiteColor
        imageView.snp.makeConstraints ({ (make) in
            make.size.equalTo(self.imageWidth)
        })
        return imageView
    }()
    
    lazy var label: UILabel = {
        let label = UILabel()
        label.font = UIFont.systemFont(ofSize: 12)
        label.textColor = .alphaWhiteColor
        label.textAlignment = .center
        return label
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageView,self.label])
        stackView.alignment = .center
        stackView.spacing = 1
        stackView.axis = .vertical
        return stackView
    }()
    
    let line: UIView = {
        let line = UIView()
        line.isHidden = true
        line.backgroundColor = .white
        return line
    }()
    
    lazy var button: UIButton = {
        let button = UIButton()
        button.addTarget(self, action: #selector(EditPhotoToolBarItem.touchUpInside), for: .touchUpInside)
        return button
    }()
    
    func resetState() {
        imageView.tintColor = .alphaWhiteColor
        label.textColor = .alphaWhiteColor
        line.isHidden = true
    }
    
    //MARK: init
    init(image: UIImage, title: String) {
        
        super.init(frame: CGRect.zero)
        
        imageView.image = image
        label.text = title
        
        self.addSubview(stackView)
        stackView.snp.makeConstraints  { (make) in
            make.center.equalTo(stackView.superview!)
        }
        
        self.addSubview(line)
        line.snp.makeConstraints  { (make) in
            make.height.equalTo(2)
            make.width.equalTo(self.imageWidth)
            make.centerX.bottom.equalTo(line.superview!)
        }
        
        self.addSubview(button)
        button.snp.makeConstraints  { (make) in
            make.edges.equalTo(button.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: Action 
    @objc func touchUpInside() {
        self.sendActions(for: .touchUpInside)
        imageView.tintColor = .white
        label.textColor = .white
        line.isHidden = false
    }
    
}
