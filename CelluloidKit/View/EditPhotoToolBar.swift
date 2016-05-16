//
//  EditPhotoToolBar.swift
//  Celluloid
//
//  Created by Mango on 16/5/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit

public
class EditPhotoToolBar: UIView {
    
    private lazy var stackView: UIStackView = {
        let stackView = UIStackView()
        stackView.axis = .Horizontal
        stackView.spacing = 0
        stackView.distribution = .FillEqually
        stackView.alignment = .Center
        
        return stackView
    }()
    
    private lazy var filterButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .FilterButton), title: tr(.Filter))
        item.addTarget(self, action: .touchFilterButton, forControlEvents: .TouchUpInside)
        return item
    }()
    
    private lazy var bubleButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .BubbleButton), title: tr(.Bubble))
        item.addTarget(self, action: .touchBubbleButton, forControlEvents: .TouchUpInside)
        return item
    }()
    
    private lazy var stickerButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .StickerButton), title: tr(.Sticker))
        item.addTarget(self, action: .touchStickerButton, forControlEvents: .TouchUpInside)
        return item
    }()
    
    private lazy var buttons: [EditPhotoToolBarItem] = [self.filterButton,self.bubleButton,self.stickerButton]
    
    //MARK: init
    private func commonInit() {
        self.backgroundColor = .alphaBlackColor
        
        self.addSubview(stackView)
        stackView.snp_makeConstraints { (make) in
            make.edges.equalTo(stackView.superview!)
        }
        buttons.forEach { button in
            stackView.addArrangedSubview(button)
            button.snp_makeConstraints(closure: { (make) in
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
    public override func layoutSubviews() {
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
    }
    
    @objc func touchBubbleButton() {
        buttons.forEach { button in
            if button != bubleButton {
                button.resetState()
            }
        }
    }
    
    @objc func touchStickerButton() {
        buttons.forEach { button in
            if button != stickerButton {
                button.resetState()
            }
        }
    }
}


//MARK: EditPhotoToolBarItem
private class EditPhotoToolBarItem: UIControl {
    
    let imageWidth = 22
    
    lazy var imageView: UIImageView = {
        let imageView = UIImageView()
        imageView.tintColor = .alphaWhiteColor
        imageView.snp_makeConstraints(closure: { (make) in
            make.size.equalTo(self.imageWidth)
        })
        return imageView
    }()
    
    lazy var label: UILabel = {
        let label = UILabel()
        label.font = UIFont.systemFontOfSize(12)
        label.textColor = .alphaWhiteColor
        label.textAlignment = .Center
        return label
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageView,self.label])
        stackView.alignment = .Center
        stackView.spacing = 1
        stackView.axis = .Vertical
        return stackView
    }()
    
    let line: UIView = {
        let line = UIView()
        line.hidden = true
        line.backgroundColor = .whiteColor()
        return line
    }()
    
    lazy var button: UIButton = {
        let button = UIButton()
        button.addTarget(self, action: #selector(EditPhotoToolBarItem.touchUpInside), forControlEvents: .TouchUpInside)
        return button
    }()
    
    func resetState() {
        imageView.tintColor = .alphaWhiteColor
        label.textColor = .alphaWhiteColor
        line.hidden = true
    }
    
    //MARK: init
    init(image: UIImage, title: String) {
        
        super.init(frame: CGRect.zero)
        
        imageView.image = image
        label.text = title
        
        self.addSubview(stackView)
        stackView.snp_makeConstraints { (make) in
            make.center.equalTo(stackView.superview!)
        }
        
        self.addSubview(line)
        line.snp_makeConstraints { (make) in
            make.height.equalTo(2)
            make.width.equalTo(self.imageWidth)
            make.centerX.bottom.equalTo(line.superview!)
        }
        
        self.addSubview(button)
        button.snp_makeConstraints { (make) in
            make.edges.equalTo(button.superview!)
        }
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: Action 
    @objc func touchUpInside() {
        self.sendActionsForControlEvents(.TouchUpInside)
        imageView.tintColor = .whiteColor()
        label.textColor = .whiteColor()
        line.hidden = false
    }
    
}
