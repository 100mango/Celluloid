import SwiftUI

/// Unsigned validation host only. The shipping UIKit app owns the final integration.
@main struct PhoneCompanionValidationApp: App {
    var body: some Scene {
        WindowGroup {
            NavigationView { PhoneCompanionResultsView(model: .shared) }
                .onAppear { PhoneCompanionController.shared.activate() }
        }
    }
}
