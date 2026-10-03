import UIKit
import Photos
import PhotosUI
import CelluloidKit

/// Keeps selection tied to PHAsset so non-destructive edits remain reversible in Photos.
final class PhotoPickerViewController: UICollectionViewController, PHPhotoLibraryChangeObserver {
    private let maximumSelection: Int
    private let completion: ([PHAsset]) -> Void
    private var assets = PHFetchResult<PHAsset>()
    private var selected: [PHAsset] = []
    private let message = UILabel()
    private var observing = false
    private lazy var settingsButton: UIButton = {
        let button = UIButton(type: .system)
        button.setTitle(NSLocalizedString("Open Settings", comment: "Photos permission recovery"), for: .normal)
        button.titleLabel?.font = .preferredFont(forTextStyle: .body)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.accessibilityIdentifier = "photos-settings"
        button.addTarget(self, action: #selector(openSettings), for: .touchUpInside)
        button.isHidden = true
        return button
    }()

    init(maximumSelection: Int, completion: @escaping ([PHAsset]) -> Void) {
        self.maximumSelection = maximumSelection
        self.completion = completion
        let layout = UICollectionViewFlowLayout()
        layout.minimumInteritemSpacing = 4
        layout.minimumLineSpacing = 4
        super.init(collectionViewLayout: layout)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    deinit {
        NotificationCenter.default.removeObserver(self)
        if observing { PHPhotoLibrary.shared().unregisterChangeObserver(self) }
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = tr(.beautify)
        collectionView.backgroundColor = .systemBackground
        collectionView.register(PhotoCell.self, forCellWithReuseIdentifier: "photo")
        navigationItem.leftBarButtonItem = UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(cancel))
        navigationItem.rightBarButtonItem = UIBarButtonItem(title: tr(.done), style: .done, target: self, action: #selector(finish))
        navigationItem.rightBarButtonItem?.accessibilityIdentifier = "picker-done"
        navigationItem.rightBarButtonItem?.isEnabled = false
        message.numberOfLines = 0
        message.textAlignment = .center
        message.accessibilityIdentifier = "photos-state"
        message.font = .preferredFont(forTextStyle: .body)
        message.adjustsFontForContentSizeCategory = true
        message.textColor = .label
        // UICollectionView's background spans underneath navigation/toolbar bars.
        // Put the scrollable status inside its safe area so large/empty messages
        // cannot be technically present but visually covered by navigation chrome.
        let background = UIView()
        let state = UIScrollView()
        state.contentInsetAdjustmentBehavior = .never
        state.translatesAutoresizingMaskIntoConstraints = false
        background.addSubview(state)
        NSLayoutConstraint.activate([
            state.topAnchor.constraint(equalTo: background.safeAreaLayoutGuide.topAnchor),
            state.bottomAnchor.constraint(equalTo: background.safeAreaLayoutGuide.bottomAnchor),
            state.leadingAnchor.constraint(equalTo: background.safeAreaLayoutGuide.leadingAnchor),
            state.trailingAnchor.constraint(equalTo: background.safeAreaLayoutGuide.trailingAnchor)
        ])
        let stateStack = UIStackView(arrangedSubviews: [message, settingsButton])
        stateStack.axis = .vertical
        stateStack.spacing = 16
        state.addSubview(stateStack)
        stateStack.translatesAutoresizingMaskIntoConstraints = false
        let minimumSettingsHeight = settingsButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 44)
        minimumSettingsHeight.priority = .defaultHigh
        minimumSettingsHeight.isActive = true
        NSLayoutConstraint.activate([
            stateStack.topAnchor.constraint(equalTo: state.contentLayoutGuide.topAnchor, constant: 24),
            stateStack.bottomAnchor.constraint(equalTo: state.contentLayoutGuide.bottomAnchor, constant: -24),
            stateStack.leadingAnchor.constraint(equalTo: state.frameLayoutGuide.leadingAnchor, constant: 24),
            stateStack.trailingAnchor.constraint(equalTo: state.frameLayoutGuide.trailingAnchor, constant: -24),
            stateStack.leadingAnchor.constraint(equalTo: state.contentLayoutGuide.leadingAnchor, constant: 24),
            stateStack.trailingAnchor.constraint(equalTo: state.contentLayoutGuide.trailingAnchor, constant: -24)
        ])
        collectionView.backgroundView = background
        NotificationCenter.default.addObserver(self, selector: #selector(refreshAuthorization),
            name: UIScene.didActivateNotification, object: nil)
        refreshAuthorization()
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let columns = max(2, Int(view.bounds.width / 140))
        let side = (view.safeAreaLayoutGuide.layoutFrame.width - CGFloat(columns - 1) * 4) / CGFloat(columns)
        (collectionViewLayout as? UICollectionViewFlowLayout)?.itemSize = CGSize(width: side, height: side)
    }
    @objc private func refreshAuthorization() {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--photos-denied") { update(status: .denied); return }
        if ProcessInfo.processInfo.arguments.contains("--photos-limited-empty") { update(status: .limited, forceEmpty: true); return }
        #endif
        let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if status == .notDetermined {
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { [weak self] status in
                DispatchQueue.main.async { self?.update(status: status) }
            }
        } else { update(status: status) }
    }
    private func update(status: PHAuthorizationStatus, forceEmpty: Bool = false) {
        guard status == .authorized || status == .limited else {
            assets = PHFetchResult<PHAsset>()
            selected.removeAll()
            settingsButton.isHidden = false
            toolbarItems = []
            navigationController?.setToolbarHidden(true, animated: false)
            navigationItem.rightBarButtonItem?.isEnabled = false
            navigationItem.leftBarButtonItems = [UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(cancel))]
            collectionView.reloadData()
            message.text = NSLocalizedString("Photos access is unavailable. Allow access in Settings to edit your library.", comment: "Photos denied")
            return
        }
        navigationItem.leftBarButtonItems = [UIBarButtonItem(title: tr(.cancel), style: .plain, target: self, action: #selector(cancel))]
        settingsButton.isHidden = true
        toolbarItems = []
        navigationController?.setToolbarHidden(true, animated: false)
        if status == .limited {
            let manage = UIBarButtonItem(title: NSLocalizedString("Manage Photos", comment: "Limited photo selection"), style: .plain, target: self, action: #selector(managePhotos))
            manage.accessibilityIdentifier = "manage-photos"
            // Keep Cancel alone in the compact navigation bar. Two leading text
            // actions can overlap the title or lose activation points on SE landscape.
            toolbarItems = [UIBarButtonItem(barButtonSystemItem: .flexibleSpace, target: nil, action: nil), manage,
                            UIBarButtonItem(barButtonSystemItem: .flexibleSpace, target: nil, action: nil)]
            navigationController?.setToolbarHidden(false, animated: false)
        }
        if !forceEmpty {
            let options = PHFetchOptions()
            options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
            assets = PHAsset.fetchAssets(with: .image, options: options)
        }
        var accessible = Set<String>()
        assets.enumerateObjects { asset, _, _ in accessible.insert(asset.localIdentifier) }
        selected.removeAll { !accessible.contains($0.localIdentifier) }
        navigationItem.rightBarButtonItem?.isEnabled = !selected.isEmpty
        message.text = assets.count == 0 ? NSLocalizedString("No photos are available. Add photos or update your selection.", comment: "Empty library") : nil
        collectionView.reloadData()
        if !observing && !forceEmpty {
            PHPhotoLibrary.shared().register(self)
            observing = true
        }
    }
    func photoLibraryDidChange(_ changeInstance: PHChange) {
        DispatchQueue.main.async { [weak self] in self?.refreshAuthorization() }
    }
    @objc private func openSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
    @objc private func managePhotos() { PHPhotoLibrary.shared().presentLimitedLibraryPicker(from: self) }
    @objc private func cancel() { dismiss(animated: true) }
    @objc private func finish() {
        // Recheck access and prune selection immediately before returning PHAssets;
        // an external permission/library change can race a queued change callback.
        refreshAuthorization()
        guard !selected.isEmpty else { return }
        let result = selected
        dismiss(animated: true) { self.completion(result) }
    }
    override func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int { assets.count }
    override func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "photo", for: indexPath) as! PhotoCell
        let asset = assets.object(at: indexPath.item)
        cell.representedIdentifier = asset.localIdentifier
        cell.accessibilityIdentifier = "photo-\(indexPath.item)"
        cell.accessibilityLabel = "Photo \(indexPath.item + 1)"
        cell.isAccessibilityElement = true
        cell.accessibilityTraits = .button
        cell.layer.borderWidth = selected.contains(where: { $0.localIdentifier == asset.localIdentifier }) ? 4 : 0
        cell.layer.borderColor = UIColor.systemBlue.cgColor
        let options = PHImageRequestOptions()
        options.isNetworkAccessAllowed = true
        PHImageManager.default().requestImage(for: asset, targetSize: CGSize(width: 300, height: 300), contentMode: .aspectFill, options: options) { [weak cell] image, _ in
            DispatchQueue.main.async {
                guard cell?.representedIdentifier == asset.localIdentifier else { return }
                cell?.imageView.image = image
            }
        }
        return cell
    }
    override func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        let asset = assets.object(at: indexPath.item)
        if let index = selected.firstIndex(where: { $0.localIdentifier == asset.localIdentifier }) { selected.remove(at: index) }
        else if selected.count < maximumSelection { selected.append(asset) }
        navigationItem.rightBarButtonItem?.isEnabled = !selected.isEmpty
        collectionView.reloadItems(at: [indexPath])
    }
}

private final class PhotoCell: UICollectionViewCell {
    let imageView = UIImageView()
    var representedIdentifier: String?
    override init(frame: CGRect) {
        super.init(frame: frame)
        imageView.contentMode = .scaleAspectFill
        imageView.clipsToBounds = true
        contentView.addSubview(imageView)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    override func layoutSubviews() { super.layoutSubviews(); imageView.frame = contentView.bounds }
    override func prepareForReuse() { super.prepareForReuse(); representedIdentifier = nil; imageView.image = nil }
}
