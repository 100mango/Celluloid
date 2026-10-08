import SwiftUI

/// A native spatial window. Imported images are the source; no passthrough-camera claim.
@main struct CelluloidVisionApp: App {
    var body: some Scene {
        DocumentGroup(newDocument: NativeDocument()) { configuration in
            EditorView(document: configuration.$document)
        }.defaultSize(width: 1100, height: 760)
    }
}
