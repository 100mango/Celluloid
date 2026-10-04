import UIKit
import SwiftUI

/// Ordinary UIKit navigation into the shared, local Watch result store.
/// The containing phone app retains its original photo editor and Photos consent flow.
@MainActor final class PhoneCompanionEntryController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        let close: () -> Void = { [weak self] in self?.dismiss(animated: true) }
        let root = NavigationView {
            PhoneCompanionResultsView(model: .shared)
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done", action: close).accessibilityIdentifier("companion.close")
                    }
                }
        }.navigationViewStyle(.stack)
        let content = UIHostingController(rootView: root)
        addChild(content); view.addSubview(content.view)
        content.view.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            content.view.topAnchor.constraint(equalTo: view.topAnchor),
            content.view.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            content.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            content.view.trailingAnchor.constraint(equalTo: view.trailingAnchor)
        ])
        content.didMove(toParent: self)
    }
}
