import SwiftUI

@main struct CelluloidMacApp: App {
    var body: some Scene {
        DocumentGroup(newDocument: NativeDocument()) { configuration in
            #if DEBUG
            if NativeAuditControl.enabled { NativeAuditControl().frame(minWidth: 640, minHeight: 480) }
            else { EditorView(document: configuration.$document) }
            #else
            EditorView(document: configuration.$document)
            #endif
        }
        .commands { CommandGroup(replacing: .help) { Link("Privacy Policy", destination: URL(string: "https://100mango.github.io/app-privacy/")!); Link("Celluloid Source & License", destination: URL(string: "https://github.com/100mango/Celluloid")!) } }
    }
}
