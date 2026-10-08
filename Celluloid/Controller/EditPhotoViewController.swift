import UIKit
import SnapKit
import CelluloidKit
import Photos

final class EditPhotoViewController: BaseEditPhotoController {
    let model: PhotoModel
    private var requestID: PHContentEditingInputRequestID?
    private var saving = false
    private lazy var doneButton = UIBarButtonItem(title: tr(.done), style: .done, target: self, action: #selector(done))
    private let activity = UIActivityIndicatorView(style: .large)

    init(model: PhotoModel) { self.model = model; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    deinit { if let id = requestID { model.asset.cancelContentEditingInputRequest(id) } }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = tr(.beautify)
        navigationItem.leftBarButtonItem = UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(cancel))
        doneButton.accessibilityIdentifier = "editor-done"
        doneButton.isEnabled = false
        navigationItem.rightBarButtonItem = doneButton
        view.addSubview(activity)
        activity.snp.makeConstraints { $0.center.equalToSuperview() }
        activity.startAnimating()
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = true
        options.canHandleAdjustmentData = { data in
            AdjustmentData.supportIdentifier(data.formatIdentifier, version: data.formatVersion) && (try? AdjustmentData.decode(data.data)) != nil
        }
        requestID = model.asset.requestContentEditingInput(with: options) { [weak self] input, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.requestID = nil
                self.activity.stopAnimating()
                guard let input = input, input.displaySizeImage != nil else {
                    self.showError(NSLocalizedString("The photo could not be loaded. Check your connection and Photos access, then try again.", comment: "Photo load failure"))
                    return
                }
                self.input = input
                if let archived = input.adjustmentData, let data = try? AdjustmentData.decode(archived.data) { self.restoreFromData(data) }
                self.doneButton.isEnabled = true
            }
        }
    }
    @objc private func cancel() { guard !saving else { return }; dismiss(animated: true) }
    @objc private func done() {
        guard !saving, let input = input else { return }
        saving = true
        doneButton.isEnabled = false
        navigationItem.leftBarButtonItem?.isEnabled = false
        view.isUserInteractionEnabled = false
        activity.startAnimating()
        exportPhoto { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure:
                self.finishSaving()
                self.showError(NSLocalizedString("The edited image could not be rendered.", comment: "Render failed"))
            case .success(let exported):
                let output = PHContentEditingOutput(contentEditingInput: input)
                output.adjustmentData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
                    formatVersion: AdjustmentData.formatVersion, data: exported.adjustmentData)
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        try exported.jpegData.write(to: output.renderedContentURL, options: .atomic)
                        PHPhotoLibrary.shared().performChanges({
                            PHAssetChangeRequest(for: self.model.asset).contentEditingOutput = output
                        }) { [weak self] success, error in
                            DispatchQueue.main.async {
                                guard let self = self else { return }
                                self.finishSaving()
                                if success {
                                    self.navigationController?.pushViewController(SharePhotoViewController(image: exported.image), animated: true)
                                } else {
                                    self.showError(error?.localizedDescription ?? NSLocalizedString("The photo could not be saved. Your original photo is unchanged.", comment: "Save failed"))
                                }
                            }
                        }
                    } catch {
                        DispatchQueue.main.async { self.finishSaving(); self.showError(error.localizedDescription) }
                    }
                }
            }
        }
    }
    private func finishSaving() {
        saving = false
        doneButton.isEnabled = true
        navigationItem.leftBarButtonItem?.isEnabled = true
        view.isUserInteractionEnabled = true
        activity.stopAnimating()
    }
    private func showError(_ message: String) {
        let alert = UIAlertController(title: NSLocalizedString("Unable to Edit Photo", comment: "Editing error"), message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: tr(.done), style: .default))
        present(alert, animated: true)
    }
}

private enum PhotoEditingError: LocalizedError {
    case renderFailed
    var errorDescription: String? { NSLocalizedString("The edited image could not be rendered.", comment: "Render failed") }
}
