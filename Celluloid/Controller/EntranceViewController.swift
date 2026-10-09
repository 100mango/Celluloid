//
//  EntranceViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SwiftUI
import SnapKit
import CelluloidKit
import Photos

enum AppLinks {
    static let privacyPolicyURL = URL(string: "https://100mango.github.io/app-privacy/")!
}

class EntranceViewController: UIViewController {
    private var horizontalLayout: Bool?
    private var footerHeight: CGFloat = 44
    private lazy var footer: UIStackView = {
        let buttons = [privacyPolicyButton]
        let stack = UIStackView(arrangedSubviews: buttons)
        stack.axis = .horizontal; stack.alignment = .fill; stack.distribution = .fillEqually; stack.spacing = 8
        return stack
    }()
    lazy var privacyPolicyButton: UIButton = {
        let button = UIButton(type: .system)
        button.setTitle(NSLocalizedString("Privacy Policy", comment: "Privacy policy link"), for: .normal)
        button.titleLabel?.font = .preferredFont(forTextStyle: .footnote)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.titleLabel?.numberOfLines = 0
        button.titleLabel?.textAlignment = .center
        button.tintColor = .alphaWhiteColor
        button.accessibilityIdentifier = "privacy-policy"
        button.accessibilityHint = NSLocalizedString("Shows the privacy policy offline.", comment: "Privacy entry accessibility hint")
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
        view.addSubview(footer)
        footer.snp.makeConstraints { make in
            make.leading.trailing.equalTo(view.safeAreaLayoutGuide).inset(16)
            make.bottom.equalTo(view.safeAreaLayoutGuide).offset(-4)
            make.height.equalTo(footerHeight)
        }
        self.view.addSubview(stackView)
        stackView.snp.makeConstraints { (make) in
            make.top.leading.trailing.equalTo(view.safeAreaLayoutGuide)
            make.bottom.equalTo(footer.snp.top).offset(-4)
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
        let buttons = footer.arrangedSubviews.compactMap { $0 as? UIButton }
        let footerWidth = max(1, (view.safeAreaLayoutGuide.layoutFrame.width - 32 - footer.spacing * CGFloat(max(0, buttons.count - 1))) / CGFloat(max(1, buttons.count)))
        let textHeight = buttons.map { $0.titleLabel?.sizeThatFits(CGSize(width: footerWidth, height: .greatestFiniteMagnitude)).height ?? 0 }.max() ?? 0
        let preferredHeight = max(44, textHeight + 16)
        if preferredHeight != footerHeight {
            footerHeight = preferredHeight
            footer.snp.updateConstraints { $0.height.equalTo(footerHeight) }
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
        let navigation = UINavigationController(rootViewController: PrivacyPolicyViewController())
        navigation.modalPresentationStyle = .fullScreen
        present(navigation, animated: true)
    }

}

/// Reading the bundled policy never opens a website. Only the separate button
/// invokes the browser opener, which can be captured without networking in tests.
final class PrivacyPolicyViewController: UIViewController {
    let bodyTextView = UITextView()
    let externalBrowserButton = UIButton(type: .system)
    private let openURL: @MainActor (URL) -> Void
    private var browserButtonHeight: NSLayoutConstraint?

    init(openURL: @escaping @MainActor (URL) -> Void = {
        UIApplication.shared.open($0, options: [:], completionHandler: nil)
    }) {
        self.openURL = openURL
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = NSLocalizedString("Privacy Policy", comment: "Privacy screen title")
        view.backgroundColor = .systemBackground
        let close = UIBarButtonItem(title: NSLocalizedString("Close", comment: "Close privacy screen"),
                                    style: .done, target: self, action: #selector(closePolicy))
        close.accessibilityIdentifier = "privacy-policy-close"
        navigationItem.rightBarButtonItem = close

        bodyTextView.text = NSLocalizedString("privacy-policy.offline-body", comment: "Bundled original iOS privacy policy")
        bodyTextView.font = .preferredFont(forTextStyle: .body)
        bodyTextView.adjustsFontForContentSizeCategory = true
        bodyTextView.textColor = .label
        bodyTextView.backgroundColor = .clear
        bodyTextView.isEditable = false
        bodyTextView.isSelectable = true
        bodyTextView.isScrollEnabled = true
        bodyTextView.alwaysBounceVertical = true
        bodyTextView.dataDetectorTypes = []
        bodyTextView.textContainerInset = UIEdgeInsets(top: 12, left: 0, bottom: 12, right: 0)
        bodyTextView.textContainer.lineFragmentPadding = 0
        bodyTextView.accessibilityIdentifier = "privacy-policy-body"

        externalBrowserButton.setTitle(NSLocalizedString("Open in External Browser", comment: "Explicit external privacy website action"), for: .normal)
        externalBrowserButton.titleLabel?.font = .preferredFont(forTextStyle: .body)
        externalBrowserButton.titleLabel?.adjustsFontForContentSizeCategory = true
        externalBrowserButton.titleLabel?.numberOfLines = 0
        externalBrowserButton.titleLabel?.textAlignment = .center
        externalBrowserButton.contentEdgeInsets = UIEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        externalBrowserButton.accessibilityIdentifier = "privacy-policy-external-browser"
        externalBrowserButton.accessibilityHint = NSLocalizedString("Opens GitHub Pages, which logs your IP address.", comment: "External browser privacy hint")
        externalBrowserButton.addTarget(self, action: #selector(openExternalPolicy), for: .touchUpInside)

        for control in [bodyTextView, externalBrowserButton] as [UIView] {
            control.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(control)
        }
        let buttonHeight = externalBrowserButton.heightAnchor.constraint(equalToConstant: 44)
        browserButtonHeight = buttonHeight
        NSLayoutConstraint.activate([
            bodyTextView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            bodyTextView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 20),
            bodyTextView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -20),
            bodyTextView.bottomAnchor.constraint(equalTo: externalBrowserButton.topAnchor, constant: -8),
            externalBrowserButton.leadingAnchor.constraint(equalTo: bodyTextView.leadingAnchor),
            externalBrowserButton.trailingAnchor.constraint(equalTo: bodyTextView.trailingAnchor),
            externalBrowserButton.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -12),
            buttonHeight
        ])
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let textWidth = max(1, externalBrowserButton.bounds.width - 24)
        let textHeight = externalBrowserButton.titleLabel?.sizeThatFits(CGSize(width: textWidth, height: .greatestFiniteMagnitude)).height ?? 0
        let height = max(44, ceil(textHeight) + 24)
        if browserButtonHeight?.constant != height { browserButtonHeight?.constant = height }
    }

    @objc private func openExternalPolicy() {
        openURL(AppLinks.privacyPolicyURL)
    }

    @objc private func closePolicy() {
        dismiss(animated: true)
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
        // Compatibility entry for existing callers/tests. The shipping scene
        // owns PhoneRootView; neither route instantiates the old full-library grid.
        let flow = UIHostingController(rootView: PhotoSelectionFlowView(maximumSelection: maximum))
        flow.modalPresentationStyle = .fullScreen
        present(flow, animated: true)
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


