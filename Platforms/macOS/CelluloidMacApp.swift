import SwiftUI

@main struct CelluloidMacApp: App {
    var body: some Scene {
        DocumentGroup(newDocument: NativeDocument()) { configuration in
            EditorView(document: configuration.$document)
        }
        .commands { CommandGroup(replacing: .help) { Link("Privacy Policy", destination: URL(string: "https://100mango.github.io/app-privacy/")!); Link("Celluloid Source & License", destination: URL(string: "https://github.com/100mango/Celluloid")!) } }
    }
}
