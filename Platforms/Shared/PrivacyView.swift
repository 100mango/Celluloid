import SwiftUI

struct PrivacyView: View {
    @Environment(\.dismiss) private var dismiss
    private var policy: String {
        guard let url = Bundle.main.url(forResource: "PrivacyPolicy", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else {
            return NSLocalizedString("The offline privacy policy is unavailable.", comment: "Privacy error")
        }
        return text
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Privacy Policy").font(.title2.bold())
            ScrollView { Text(verbatim: policy).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
            HStack {
                Link("Open Privacy Policy", destination: URL(string: "https://100mango.github.io/app-privacy/")!)
                Spacer(); Button("Done") { dismiss() }
            }
        }.padding(24).frame(width: 560, height: 440)
    }
}
