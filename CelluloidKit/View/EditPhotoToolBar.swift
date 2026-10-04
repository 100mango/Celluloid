//
//  EditPhotoToolBar.swift
//  Celluloid
//
//  Created by Mango on 16/5/13.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit

public protocol EditPhotoToolBarDelegate: AnyObject {
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel)
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel)
    
    func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType)
}

open class EditPhotoToolBar: UIView {
    
    open weak var delegate: EditPhotoToolBarDelegate?

    private var editingGeneration = UUID()
    private weak var activePicker: UIViewController?
    private var activePickerGeneration: UUID?

    /// A picker belongs to the input/session that created it. Dismiss only that
    /// owned panel; delayed callbacks cannot be rebound to the next input.
    func invalidateEditingSession() {
        editingGeneration = UUID()
        if let panel = activePicker?.navigationController, panel.presentingViewController != nil {
            panel.dismiss(animated: false)
        }
        activePicker = nil
        activePickerGeneration = nil
        buttons.forEach { $0.resetState() }
    }
    private func register(_ picker: UIViewController) {
        activePicker = picker
        activePickerGeneration = editingGeneration
    }
    private func consumeSelection(from picker: UIViewController) -> Bool {
        guard activePicker === picker, activePickerGeneration == editingGeneration else { return false }
        activePicker = nil
        activePickerGeneration = nil
        return true
    }
    func makeFilterPicker() -> FilterPickerViewController {
        let picker = FilterPickerViewController(); picker.delegate = self; register(picker); return picker
    }
    func makeBubblePicker() -> BubblePickerViewController {
        let picker = BubblePickerViewController(); picker.delegate = self; register(picker); return picker
    }
    func makeStickerPicker() -> StickerPickerViewController {
        let picker = StickerPickerViewController(); picker.delegate = self; register(picker); return picker
    }

    
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
        item.accessibilityIdentifier = "tool-filter"
        item.accessibilityLabel = tr(.filter)
        item.addTarget(self, action: .touchFilterButton, for: .touchUpInside)
        return item
    }()
    
    fileprivate lazy var bubleButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .BubbleButton), title: tr(.bubble))
        item.accessibilityIdentifier = "tool-bubble"
        item.accessibilityLabel = tr(.bubble)
        item.addTarget(self, action: .touchBubbleButton, for: .touchUpInside)
        return item
    }()
    
    fileprivate lazy var stickerButton: EditPhotoToolBarItem = {
        let item = EditPhotoToolBarItem(image: UIImage(asset: .StickerButton), title: tr(.sticker))
        item.accessibilityIdentifier = "tool-sticker"
        item.accessibilityLabel = tr(.sticker)
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
    
    // The labels are part of app chrome, not exported artwork. Their full
    // Dynamic Type height must participate in the editor's preview layout.
    var titleLabels: [UILabel] { buttons.map { $0.label } }
    var itemControls: [UIControl] { buttons }
    private var previousLayoutWidth: CGFloat = 0

    open override var intrinsicContentSize: CGSize {
        let itemWidth = max(1, bounds.width / CGFloat(buttons.count) - 12)
        let titleHeight = buttons.map {
            $0.label.sizeThatFits(CGSize(width: itemWidth, height: .greatestFiniteMagnitude)).height
        }.max() ?? 0
        return CGSize(width: UIView.noIntrinsicMetric, height: max(49, ceil(titleHeight) + 22 + 1 + 8))
    }

    open override func layoutSubviews() {
        super.layoutSubviews()
        if previousLayoutWidth != bounds.width {
            previousLayoutWidth = bounds.width
            invalidateIntrinsicContentSize()
        }
    }

    open override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {
        super.traitCollectionDidChange(previousTraitCollection)
        guard previousTraitCollection?.preferredContentSizeCategory != traitCollection.preferredContentSizeCategory else { return }
        buttons.forEach { $0.label.font = .preferredFont(forTextStyle: .caption1, compatibleWith: traitCollection) }
        invalidateIntrinsicContentSize()
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
        
        let filterPicker = makeFilterPicker()
        presentViewControllerFromSheet(filterPicker)
    }
    
    @objc func touchBubbleButton() {
        buttons.forEach { button in
            if button != bubleButton {
                button.resetState()
            }
        }
        
        let bubblePicker = makeBubblePicker()
        presentViewControllerFromSheet(bubblePicker)
    }
    
    @objc func touchStickerButton() {
        buttons.forEach { button in
            if button != stickerButton {
                button.resetState()
            }
        }
        
        let stickerPicker = makeStickerPicker()
        presentViewControllerFromSheet(stickerPicker)
    }
    
    func presentViewControllerFromSheet(_ vc: UIViewController) {
        let navigationVC = UINavigationController(rootViewController: vc)
        navigationVC.modalPresentationStyle = .formSheet
        navigationVC.sheetPresentationController?.detents = [.medium(), .large()]
        navigationVC.sheetPresentationController?.prefersGrabberVisible = true
        self.parentViewController?.present(navigationVC, animated: true)
    }
}

//MARK: BubblePickerViewControllerDelegate
extension EditPhotoToolBar: BubblePickerViewControllerDelegate {
    public func bubblePickerViewController(_ bubblePickerViewController: BubblePickerViewController, didSelectBubble bubble: BubbleModel) {
        guard consumeSelection(from: bubblePickerViewController) else { return }
        self.delegate?.editPhotoToolBar(self, didSelectBubble: bubble)
    }
}

//MARK: StickerPickerViewControllerDelegate
extension EditPhotoToolBar: StickerPickerViewControllerDelegate {
    public func stickerPickerViewController(_ stickerPickerViewController: StickerPickerViewController, didSelectSticker sticker: StickerModel) {
        guard consumeSelection(from: stickerPickerViewController) else { return }
        self.delegate?.editPhotoToolBar(self, didSelectSticker: sticker)
    }
}

//MARK: FilterPickerViewControllerDelegate
extension EditPhotoToolBar: FilterPickerViewControllerDelegate {
    public func filterPickerViewController(_ filterPickerViewController: FilterPickerViewController, didSelectFilter filter: FilterType) {
        guard consumeSelection(from: filterPickerViewController) else { return }
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
        label.font = .preferredFont(forTextStyle: .caption1)
        label.adjustsFontForContentSizeCategory = true
        label.numberOfLines = 0
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
            make.centerY.equalTo(stackView.superview!)
            make.leading.trailing.equalTo(stackView.superview!).inset(6)
            make.top.greaterThanOrEqualTo(stackView.superview!).offset(4)
            make.bottom.lessThanOrEqualTo(stackView.superview!).offset(-4)
        }
        label.snp.makeConstraints { make in
            make.width.equalTo(stackView)
        }
        
        self.addSubview(line)
        line.snp.makeConstraints  { (make) in
            make.height.equalTo(2)
            make.width.equalTo(self.imageWidth)
            make.centerX.bottom.equalTo(line.superview!)
        }
        
        isAccessibilityElement = true
        accessibilityTraits = .button
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
