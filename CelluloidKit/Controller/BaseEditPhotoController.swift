//
//  BaseEditPhotoController.swift
//  Celluloid
//
//  Created by Mango on 16/5/18.
//  Copyright © 2016年 Mango. All rights reserved.
//

import UIKit
import SnapKit
import Photos

open class BaseEditPhotoController: UIViewController {
    
    private let exportService = PhotoExportService()
    private var activeExport: PhotoExportTask?
    private let previewPipeline = LegacyFilterPreviewPipeline()
    private var previewGeneration = UUID()
    public private(set) var isPreviewRendering = false
    #if DEBUG
    var activeExportForTesting: PhotoExportTask? { activeExport }
    #endif

    public func cancelExport() { exportService.cancel(); activeExport = nil }
    public private(set) var preservedAdjustmentData: PHAdjustmentData?
    public var isAdjustmentReadOnly: Bool { preservedAdjustmentData != nil }
    private lazy var readOnlyNotice: UILabel = {
        let label = UILabel()
        label.text = tr(.readOnly)
        label.font = .preferredFont(forTextStyle: .headline)
        label.adjustsFontForContentSizeCategory = true
        label.numberOfLines = 0
        label.textAlignment = .center
        label.backgroundColor = .systemBackground
        label.textColor = .label
        label.accessibilityIdentifier = "read-only-adjustment"
        label.accessibilityHint = tr(.unreadableEditsMessage)
        label.isHidden = true
        return label
    }()

    /// The caller supplies the current rendered preview for this exact input.
    /// Preserve opaque state without restoring a subset or producing new edits.
    public func preserveUnreadableAdjustment(_ data: PHAdjustmentData, currentImage: UIImage?) {
        cancelExport()
        preservedAdjustmentData = data
        toolBar.invalidateEditingSession()
        overlayView.reset()
        filterType = .Original
        sourceImage = currentImage
        toolBar.isHidden = true
        toolBar.accessibilityElementsHidden = true
        preview.isUserInteractionEnabled = false
        readOnlyNotice.isHidden = false
    }

    //MARK: Property
    open var input: PHContentEditingInput? {
        didSet {
            cancelExport()
            toolBar.invalidateEditingSession()
            preservedAdjustmentData = nil
            toolBar.isHidden = false
            toolBar.accessibilityElementsHidden = false
            preview.isUserInteractionEnabled = true
            readOnlyNotice.isHidden = true
            // A reused editor/Photos extension starts a separate editing session.
            filterType = .Original
            overlayView.reset()
            sourceImage = input?.displaySizeImage
        }
    }
    public var sourceImage: UIImage? {
        didSet {
            cancelExport()
            // Keep the exact Photos display image and its synchronous geometry.
            // Imported files must be prepared off-main before this boundary.
            // Never leave the previous asset visible while filtering a new one.
            preview.image = sourceImage
            updatePreviewImage()
        }
    }
    public let preview: UIImageView = {
        let preview = UIImageView()
        preview.contentMode = .scaleAspectFit
        preview.isUserInteractionEnabled = true
        return preview
    }()
    let toolBar =  EditPhotoToolBar()
    
    lazy var overlayView: ImageOverlayView = ImageOverlayView.makeViewOverlaysImageView(self.preview)
    
    var filterType = FilterType.Original {
        didSet { cancelExport(); updatePreviewImage() }
    }

    private func updatePreviewImage() {
        cancelPreview()
        // Opaque/read-only Photos adjustments must retain their exact current
        // display image. Original does not require any CI work at all.
        guard filterType != .Original, !isAdjustmentReadOnly else {
            preview.image = sourceImage
            overlayView.adjustFrame()
            viewIfLoaded?.setNeedsLayout()
            return
        }
        guard let sourceImage else {
            preview.image = nil
            overlayView.adjustFrame()
            return
        }
        let generation = previewGeneration
        isPreviewRendering = true
        // Preserve exact old reference-canvas aspect, including odd pixel sizes.
        // This Photos display-size image is already a preview; only move its
        // filtering off-main. New SwiftUI canvases may use bounded rasters.
        previewPipeline.render(source: sourceImage, filter: filterType, maximumDimension: nil) { [weak self] result in
            guard let self, self.previewGeneration == generation else { return }
            self.isPreviewRendering = false
            guard case .success(let image) = result else { return }
            self.preview.image = image
            self.overlayView.adjustFrame()
            self.viewIfLoaded?.setNeedsLayout()
        }
        overlayView.adjustFrame()
        viewIfLoaded?.setNeedsLayout()
    }

    /// End the preview session without changing immutable export snapshots.
    public func cancelPreview() {
        previewGeneration = UUID()
        isPreviewRendering = false
        previewPipeline.cancel()
    }

    deinit { previewPipeline.cancel() }

    //Computed property
    open var adjustmentData: AdjustmentData {
        viewIfLoaded?.layoutIfNeeded()
        overlayView.adjustFrame()
        var adjustmentData = AdjustmentData()
        adjustmentData.bubbles = overlayView.bubbleModels
        adjustmentData.stickers = overlayView.stickerModels
        adjustmentData.filterType = filterType
        adjustmentData.referenceCanvasSize = overlayView.referenceCanvasSize
        return adjustmentData
    }
    
    private var exportSource: PhotoExportSource {
        if let input {
            return .photosOriginal(url: input.fullSizeImageURL, orientation: input.fullSizeImageOrientation)
        }
        return .importedCopy(sourceImage)
    }

    /// Synchronous compatibility API. App and extension saving use exportPhoto.
    open var outputImage: UIImage? {
        guard !isAdjustmentReadOnly else { return nil }
        return PhotoExportService.synchronousOutput(snapshot: adjustmentData, source: exportSource,
                                                    isReadOnly: false)
    }

    @discardableResult
    public func exportPhoto(completion: @escaping (Result<PhotoExport, PhotoExportError>) -> Void) -> PhotoExportTask {
        cancelExport()
        let snapshot = isAdjustmentReadOnly ? AdjustmentData() : adjustmentData
        let task = exportService.export(snapshot: snapshot, source: exportSource,
                                        isReadOnly: isAdjustmentReadOnly, completion: completion)
        activeExport = task
        return task
    }

    #if DEBUG
    func diagnosticSpatialRender(rect: CGRect, globalBounds: Bool) -> UIImage? {
        PhotoExportService.diagnosticSpatialRender(snapshot: adjustmentData, source: exportSource,
                                                   rect: rect, globalBounds: globalBounds)
    }
    #endif

    //MARK: View Lift Cycle
    override open func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .blackBackgroundColor
        
        toolBar.delegate = self
        self.view.addSubview(preview)
        self.view.addSubview(toolBar)
        self.view.addSubview(readOnlyNotice)
        readOnlyNotice.snp.makeConstraints { make in
            make.leading.trailing.equalTo(view.safeAreaLayoutGuide).inset(16)
            make.bottom.equalTo(view.safeAreaLayoutGuide).inset(8)
            make.top.greaterThanOrEqualTo(view.safeAreaLayoutGuide).offset(8)
        }
        toolBar.setContentHuggingPriority(.required, for: .vertical)
        toolBar.setContentCompressionResistancePriority(.required, for: .vertical)
        toolBar.snp.makeConstraints { make in
            make.left.right.bottom.equalTo(view.safeAreaLayoutGuide)
        }
        preview.snp.makeConstraints { make in
            make.top.left.right.equalTo(view.safeAreaLayoutGuide)
            make.bottom.equalTo(toolBar.snp.top)
        }
    }
    
    override open func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        overlayView.adjustFrame()
    }
}


// MARK: - Public
public extension BaseEditPhotoController {
    func restoreFromData(_ data: AdjustmentData) {
        guard !isAdjustmentReadOnly else { return }
        filterType = data.filterType
        overlayView.restore(data)
    }
}

// MARK: - EditPhotoPanel Delegate
extension BaseEditPhotoController: EditPhotoToolBarDelegate {
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel) {
        guard !isAdjustmentReadOnly else { return }
        self.overlayView.addBubble(bubble)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel) {
        guard !isAdjustmentReadOnly else { return }
        self.overlayView.addSticker(sticker)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType) {
        guard !isAdjustmentReadOnly else { return }
        filterType = filter
    }
}
