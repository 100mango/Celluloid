//
//  EditBubbleViewController.swift
//  Celluloid
//
//  Created by Mango on 16/3/12.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit

public protocol EditBubbleViewControllerDelegate: AnyObject {
    func editBubbleViewController(_ editBubbleViewController: EditBubbleViewController, didEditedBubbleModel bubbleModel: BubbleModel)
    
}

open class EditBubbleViewController: UIViewController {
    
    //MARK: Property
    var bubbleModel: BubbleModel
    
    open weak var delegate: EditBubbleViewControllerDelegate?
    
    fileprivate lazy var textView: UITextView = {
        let textView = UITextView()
        textView.textAlignment = .center
        textView.text = self.bubbleModel.content
        textView.backgroundColor = .bubbleBackgroundColor
        textView.textColor = .black
        textView.tintColor = .black
        textView.font = .preferredFont(forTextStyle: .body)
        textView.adjustsFontForContentSizeCategory = true
        textView.accessibilityIdentifier = "bubble-text"
        return textView
    }()
    
    fileprivate lazy var rightBarButtonItem: UIBarButtonItem = {
        let rightBarButtonItem = UIBarButtonItem(title: tr(.done), style: .plain, target: self, action: #selector(done))

        rightBarButtonItem.accessibilityIdentifier = "bubble-text-done"
        return rightBarButtonItem
    }()
    
    //MARK: init
    public init(bubbleModel:BubbleModel){
        self.bubbleModel = bubbleModel
        super.init(nibName: nil, bundle: nil)
        self.view.backgroundColor = .white
        self.title = tr(.edit)
    }

    required public init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    //MARK: View life cycle
    open override func viewDidLoad() {
        super.viewDidLoad()
        self.view.addSubview(self.textView)
        self.textView.snp.makeConstraints { (make) -> Void in
            make.top.equalTo(self.view.safeAreaLayoutGuide.snp.top).offset(10)
            make.left.right.equalTo(view.safeAreaLayoutGuide).inset(10)
            make.bottom.equalTo(view.keyboardLayoutGuide.snp.top).offset(-10)
        }
        
        self.navigationItem.rightBarButtonItem = self.rightBarButtonItem
    }
}

//MARK: Action
private extension EditBubbleViewController {
    @objc func done(){
        self.bubbleModel.content = self.textView.text
        self.delegate?.editBubbleViewController(self, didEditedBubbleModel: self.bubbleModel)
        dismiss(animated: true, completion: nil)
    }
}
