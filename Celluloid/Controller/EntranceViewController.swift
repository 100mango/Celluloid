//
//  EntranceViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import CelluloidKit
import Photos
import SafariServices

enum AppLinks {
    static let privacyPolicyURL = URL(string: "https://100mango.github.io/app-privacy/")!
}

class EntranceViewController: UIViewController {
    private var horizontalLayout: Bool?
    private var footerHeight: CGFloat = 44
    lazy var privacyPolicyButton: UIButton = {
        let button = UIButton(type: .system)
        button.setTitle(NSLocalizedString("Privacy Policy", comment: "Privacy policy link"), for: .normal)
        button.titleLabel?.font = .preferredFont(forTextStyle: .footnote)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.titleLabel?.numberOfLines = 0
        button.titleLabel?.textAlignment = .center
        button.tintColor = .alphaWhiteColor
        button.accessibilityIdentifier = "privacy-policy"
        button.accessibilityHint = NSLocalizedString("Opens the app privacy policy.", comment: "Privacy link accessibility hint")
        button.addTarget(self, action: #selector(showPrivacyPolicy), for: .touchUpInside)
        return button
    }()

    
    lazy var editPhotoButton: IconButton = {
        let button = IconButton(image: UIImage(named: "EditPhotoEntranceButton")!, title: tr(.beautify))
        button.accessibilityIdentifier = "edit-photo"
        button.accessibilityLabel = tr(.beautify)
        button.addTarget(self, action: .editPhoto, for: .touchUpInside)
        return button
    }()
    
    lazy var makeCollageButton: IconButton = {
        let button = IconButton(image: UIImage(named: "CollageEntranceButton")!, title: tr(.collage))
        button.accessibilityIdentifier = "make-collage"
        button.accessibilityLabel = tr(.collage)
        button.addTarget(self, action: .makeCollage, for: .touchUpInside)
        return button
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.editPhotoButton,self.makeCollageButton])
        
        stackView.alignment = .fill
        stackView.spacing = 0
        stackView.axis = .vertical
        stackView.distribution = .fillEqually
        
        return stackView
    }()
    
    lazy var line: UIView = {
        let line = UIView()
        line.backgroundColor = .alphaWhiteColor
        return line
    }()
    
    //View Life Cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .black
        view.addSubview(privacyPolicyButton)
        privacyPolicyButton.snp.makeConstraints { make in
            make.leading.trailing.equalTo(view.safeAreaLayoutGuide).inset(16)
            make.bottom.equalTo(view.safeAreaLayoutGuide).offset(-4)
            make.height.equalTo(footerHeight)
        }
        self.view.addSubview(stackView)
        stackView.snp.makeConstraints { (make) in
            make.top.leading.trailing.equalTo(view.safeAreaLayoutGuide)
            make.bottom.equalTo(privacyPolicyButton.snp.top).offset(-4)
        }
        
        self.view.addSubview(line)
        line.snp.makeConstraints  { (make) in
            make.width.equalTo(245)
            make.height.equalTo(1)
            make.center.equalTo(stackView)
        }
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        // A lower-bound-only footer could absorb all free space because IconButton
        // intentionally has no intrinsic size. Keep a definite, Dynamic-Type-aware
        // footer so the two primary choices always receive the remaining area.
        let footerWidth = max(1, view.safeAreaLayoutGuide.layoutFrame.width - 32)
        let textHeight = privacyPolicyButton.titleLabel?.sizeThatFits(CGSize(width: footerWidth, height: .greatestFiniteMagnitude)).height ?? 0
        let preferredHeight = max(44, textHeight + 16)
        if preferredHeight != footerHeight {
            footerHeight = preferredHeight
            privacyPolicyButton.snp.updateConstraints { $0.height.equalTo(footerHeight) }
        }
        let horizontal = view.bounds.width > view.bounds.height
        guard horizontal != horizontalLayout else { return }
        horizontalLayout = horizontal
        stackView.axis = horizontal ? .horizontal : .vertical
        line.snp.remakeConstraints { make in
            make.center.equalTo(stackView)
            if horizontal { make.width.equalTo(1); make.height.equalTo(stackView).multipliedBy(0.65) }
            else { make.height.equalTo(1); make.width.equalTo(stackView).multipliedBy(0.65) }
        }
    }

    @objc private func showPrivacyPolicy() {
        let policy = SFSafariViewController(url: AppLinks.privacyPolicyURL)
        policy.dismissButtonStyle = .close
        present(policy, animated: true)
    }

}

//MARK: Action
private extension Selector {
    static let editPhoto = #selector(EntranceViewController.editPhoto)
    static let makeCollage = #selector(EntranceViewController.makeCollage)
}


private extension EntranceViewController {
    @objc func editPhoto() { presentPhotoPicker(maximum: 1) }
    @objc func makeCollage() { presentPhotoPicker(maximum: 4) }

    func presentPhotoPicker(maximum: Int) {
        let picker = PhotoPickerViewController(maximumSelection: maximum) { [weak self] assets in
            guard let self = self, !assets.isEmpty else { return }
            let editor: UIViewController
            if assets.count == 1 {
                editor = EditPhotoViewController(model: PhotoModel(asset: assets[0]))
            } else {
                editor = CollageViewController(assets: assets)
            }
            let navigation = UINavigationController(rootViewController: editor)
            navigation.modalPresentationStyle = .fullScreen
            self.present(navigation, animated: true)
        }
        let navigation = UINavigationController(rootViewController: picker)
        navigation.modalPresentationStyle = .fullScreen
        present(navigation, animated: true)
    }
}


class IconButton: UIControl {
    
    let imageWidth = 62.5
    
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
        label.font = .preferredFont(forTextStyle: .body)
        label.adjustsFontForContentSizeCategory = true
        label.numberOfLines = 0
        label.textColor = .white
        label.textAlignment = .center
        return label
    }()
    
    lazy var stackView: UIStackView = {
        let stackView = UIStackView(arrangedSubviews: [self.imageView,self.label])
        stackView.alignment = .center
        stackView.spacing = 35
        stackView.axis = .vertical
        return stackView
    }()
    
    lazy var button: UIButton = {
        let button = UIButton()
        button.addTarget(self, action: #selector(IconButton.touchUpInside), for: .touchUpInside)
        return button
    }()
    
    func resetState() {
        imageView.tintColor = .alphaWhiteColor
        label.textColor = .alphaWhiteColor
    }
    
    //MARK: init
    init(image: UIImage, title: String) {
        
        super.init(frame: CGRect.zero)
        
        imageView.image = image
        label.text = title
        
        self.addSubview(stackView)
        stackView.snp.makeConstraints  { (make) in
            make.center.equalTo(stackView.superview!)
            make.leading.greaterThanOrEqualToSuperview().offset(12)
            make.trailing.lessThanOrEqualToSuperview().offset(-12)
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
    }
    
}


