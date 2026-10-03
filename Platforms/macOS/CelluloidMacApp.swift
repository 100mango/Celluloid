import SwiftUI

@main struct CelluloidMacApp: App {
    var body: some Scene {
        DocumentGroup(newDocument: NativeDocument()) { configuration in
            EditorView(document: configuration.$document)
        }
        .commands { CommandGroup(replacing: .help) { Link("Celluloid Source & License", destination: URL(string: "https://github.com/100mango/Celluloid")!) } }
    }
}
