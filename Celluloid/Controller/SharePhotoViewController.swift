//
//  SharePhotoViewController.swift
//  Celluloid
//
//  Created by Mango on 16/5/27.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import CelluloidKit

class SharePhotoViewController: UIViewController {
    
    lazy var shareButton: UIButton = {
        let button = UIButton()
        button.setTitle(tr(.share), for: .normal)
        button.accessibilityIdentifier = "share-photo"
        button.titleLabel?.font = .preferredFont(forTextStyle: .body)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.titleLabel?.numberOfLines = 0
        button.titleLabel?.textAlignment = .center
        button.contentEdgeInsets = UIEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        button.addTarget(self, action: .share, for: .touchUpInside)
        button.layer.cornerRadius = 22
        button.layer.borderWidth = 1
        button.layer.borderColor = UIColor.white.cgColor
        button.backgroundColor = .clear
        button.setTitleColor(.white, for: .normal)
        return button
    }()
    
    lazy var doneButton: UIButton = {
        let button = UIButton()
        button.setTitle(tr(.done), for: .normal)
        button.accessibilityIdentifier = "share-done"
        button.titleLabel?.font = .preferredFont(forTextStyle: .body)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.titleLabel?.numberOfLines = 0
        button.titleLabel?.textAlignment = .center
        button.contentEdgeInsets = UIEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        button.addTarget(self, action: .done, for: .touchUpInside)
        button.layer.cornerRadius = 22
        button.layer.borderWidth = 1
        button.layer.borderColor = UIColor.white.cgColor
        button.backgroundColor = .clear
        button.setTitleColor(.white, for: .normal)
        return button
    }()
    
    let savedIcon = UIImageView(image: UIImage(named: "saved"))
    let savedLabel: UILabel = {
        let label = UILabel()
        label.text = tr(.saved)
        label.accessibilityIdentifier = "photo-saved"
        label.font = .preferredFont(forTextStyle: .title3)
        label.adjustsFontForContentSizeCategory = true
        label.numberOfLines = 0
        label.textAlignment = .center
        label.textColor = .white
        return label
    }()
    
    
    let image: UIImage

    init(image: UIImage) {
        self.image = image
        super.init(nibName: nil, bundle: nil)
        self.view.backgroundColor = .blackBackgroundColor
    }
    
    required init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    private let scrollView = UIScrollView()
    private let contentView = UIView()
    private lazy var actions: UIStackView = {
        let stack = UIStackView(arrangedSubviews: [shareButton, doneButton])
        stack.axis = .vertical
        stack.spacing = 12
        stack.distribution = .fillEqually
        return stack
    }()
    private lazy var contentStack: UIStackView = {
        let stack = UIStackView(arrangedSubviews: [savedIcon, savedLabel, actions])
        stack.axis = .vertical
        stack.alignment = .fill
        stack.spacing = 16
        return stack
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        navigationItem.hidesBackButton = true
        // A centered scrollable group keeps Done reachable even in compact landscape
        // and at accessibility text sizes, rather than positioning it below the screen.
        view.addSubview(scrollView)
        scrollView.snp.makeConstraints { $0.edges.equalTo(view.safeAreaLayoutGuide) }
        scrollView.addSubview(contentView)
        contentView.snp.makeConstraints { make in
            make.edges.equalTo(scrollView.contentLayoutGuide)
            make.width.equalTo(scrollView.frameLayoutGuide)
            make.height.greaterThanOrEqualTo(scrollView.frameLayoutGuide)
            make.height.equalTo(scrollView.frameLayoutGuide).priority(250)
        }
        contentView.addSubview(contentStack)
        contentStack.snp.makeConstraints { make in
            make.center.equalToSuperview()
            make.top.greaterThanOrEqualToSuperview().offset(16)
            make.bottom.lessThanOrEqualToSuperview().offset(-16)
            make.leading.greaterThanOrEqualToSuperview().offset(16)
            make.trailing.lessThanOrEqualToSuperview().offset(-16)
            make.width.lessThanOrEqualTo(360)
            make.width.equalToSuperview().offset(-32).priority(750)
        }
        savedIcon.contentMode = .scaleAspectFit
        savedIcon.snp.makeConstraints { $0.height.equalTo(48) }
        shareButton.snp.makeConstraints { $0.height.greaterThanOrEqualTo(44) }
        doneButton.snp.makeConstraints { $0.height.greaterThanOrEqualTo(44) }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let axis: NSLayoutConstraint.Axis = view.bounds.width > view.bounds.height ? .horizontal : .vertical
        if actions.axis != axis { actions.axis = axis }
    }

    
}

//MARK: Action
private extension Selector {
    static let share = #selector(SharePhotoViewController.share)
    static let done =  #selector(SharePhotoViewController.done)
}

extension SharePhotoViewController {
    
    @objc func share() {
        let activityViewController = UIActivityViewController(activityItems: [image], applicationActivities: nil)
        activityViewController.popoverPresentationController?.sourceView = self.shareButton
        activityViewController.popoverPresentationController?.sourceRect = self.shareButton.bounds
        present(activityViewController, animated: true, completion: nil)
    }
    
    @objc func done() {
        dismiss(animated: true, completion: nil)
    }
}
