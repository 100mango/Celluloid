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
    
    private nonisolated static let exportQueue = DispatchQueue(label: "Mango.Celluloid.full-resolution-export", qos: .userInitiated)
    private var activeExport: PhotoExportTask?

    public func cancelExport() { activeExport?.cancel(); activeExport = nil }

    //MARK: Property
    open var input: PHContentEditingInput? {
        didSet {
            cancelExport()
            // A reused editor/Photos extension starts a separate editing session.
            filterType = .Original
            overlayView.reset()
            sourceImage = input?.displaySizeImage
        }
    }
    public var sourceImage: UIImage? {
        didSet { cancelExport(); updatePreviewImage() }
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
        preview.image = filterType == .Original ? sourceImage : sourceImage?.filteredImage(Filters.filter(filterType))
        overlayView.adjustFrame()
        viewIfLoaded?.setNeedsLayout()
    }

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
    
    /// Synchronous compatibility API for callers already on the UI thread.
    /// App and extension saving use exportPhoto to move decode/filter/JPEG off-main.
    open var outputImage: UIImage? {
        let data = adjustmentData
        guard let image = Self.prepareFullSizeImage(url: input?.fullSizeImageURL,
                orientation: input?.fullSizeImageOrientation, fallback: input == nil ? sourceImage : nil, filter: data.filterType) else { return nil }
        return composite(image, data: data)
    }

    @discardableResult
    public func exportPhoto(completion: @escaping (Result<PhotoExport, PhotoExportError>) -> Void) -> PhotoExportTask {
        precondition(Thread.isMainThread)
        cancelExport()
        let task = PhotoExportTask()
        activeExport = task
        let data = adjustmentData
        let url = input?.fullSizeImageURL
        let orientation = input?.fullSizeImageOrientation
        let fallback = input == nil ? sourceImage : nil
        func finish(_ result: Result<PhotoExport, PhotoExportError>) {
            DispatchQueue.main.async {
                completion(task.isCancelled ? .failure(.cancelled) : result)
            }
        }
        func encode(_ image: UIImage) {
            Self.exportQueue.async {
                autoreleasepool {
                    guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                    guard let jpeg = image.jpegData(compressionQuality: 1) else { finish(.failure(.encodingFailed)); return }
                    guard let archive = try? data.encode() else { finish(.failure(.invalidState)); return }
                    finish(.success(PhotoExport(image: image, jpegData: jpeg, adjustmentData: archive)))
                }
            }
        }
        Self.exportQueue.async { [weak self] in
            autoreleasepool {
                guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                guard let image = Self.prepareFullSizeImage(url: url, orientation: orientation, fallback: fallback, filter: data.filterType) else {
                    finish(.failure(.missingImage)); return
                }
                guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                if data.bubbles.isEmpty && data.stickers.isEmpty {
                    // No UIKit render or additional full-size backing surface.
                    encode(image)
                } else {
                    DispatchQueue.main.async { [weak self] in
                        autoreleasepool {
                            guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                            guard let self = self, let output = self.composite(image, data: data) else {
                                finish(.failure(.missingImage)); return
                            }
                            encode(output)
                        }
                    }
                }
            }
        }
        return task
    }

    private func composite(_ fullSizeImage: UIImage, data: AdjustmentData) -> UIImage? {
        precondition(Thread.isMainThread)
        if data.bubbles.isEmpty && data.stickers.isEmpty { return fullSizeImage }
        guard let canvas = data.referenceCanvasSize, AdjustmentData.isValidReferenceCanvas(canvas),
              fullSizeImage.size.width > 0, fullSizeImage.size.height > 0 else { return nil }
        let sx = fullSizeImage.size.width / canvas.width
        let sy = fullSizeImage.size.height / canvas.height
        guard sx.isFinite, sy.isFinite, sx > 0, sy > 0,
              data.bubbles.allSatisfy({ hasRenderableGeometry(center: CGPoint(x: $0.center.x * sx, y: $0.center.y * sy), bounds: $0.bounds, transform: $0.transform.scaledInCanvas(x: sx, y: sy)) }),
              data.stickers.allSatisfy({ hasRenderableGeometry(center: CGPoint(x: $0.center.x * sx, y: $0.center.y * sy), bounds: $0.bounds, transform: $0.transform.scaledInCanvas(x: sx, y: sy)) }) else { return nil }
        return autoreleasepool {
            let fullSizeImageView = UIImageView(image: fullSizeImage)
            fullSizeImageView.size = fullSizeImage.size
            let scaleX = fullSizeImage.size.width / canvas.width
            let scaleY = fullSizeImage.size.height / canvas.height
            for model in data.bubbles {
                var scaled = model
                scaled.center = CGPoint(x: scaleX * model.center.x, y: scaleY * model.center.y)
                scaled.transform = model.transform.scaledInCanvas(x: scaleX, y: scaleY)
                fullSizeImageView.addSubview(BubbleView(bubbleModel: scaled))
            }
            for model in data.stickers {
                var scaled = model
                scaled.center = CGPoint(x: scaleX * model.center.x, y: scaleY * model.center.y)
                scaled.transform = model.transform.scaledInCanvas(x: scaleX, y: scaleY)
                fullSizeImageView.addSubview(StickerView(stickerModel: scaled))
            }
            return fullSizeImageView.render()
        }
    }

    private nonisolated static func prepareFullSizeImage(url: URL?, orientation: Int32?, fallback: UIImage?, filter: FilterType) -> UIImage? {
        let image: UIImage
        let exif: Int32
        if let url = url {
            guard let loaded = UIImage(contentsOfFile: url.path) else { return nil }
            image = loaded
            exif = orientation ?? 1
        } else if let fallback = fallback {
            image = fallback
            switch fallback.imageOrientation {
            case .up: exif = 1
            case .upMirrored: exif = 2
            case .down: exif = 3
            case .downMirrored: exif = 4
            case .leftMirrored: exif = 5
            case .right: exif = 6
            case .rightMirrored: exif = 7
            case .left: exif = 8
            @unknown default: exif = 1
            }
        } else { return nil }
        guard image.size.width > 0, image.size.height > 0 else { return nil }
        if exif == 1 && filter == .Original, let backing = image.cgImage {
            return UIImage(cgImage: backing, scale: 1, orientation: .up)
        }
        // Fuse orientation and filtering into one Core Image render rather than
        // retaining separate normalized and filtered full-resolution surfaces.
        let rendered = image.filteredImage(exif, filter: Filters.filter(filter))
        guard let pixels = rendered.cgImage else { return nil }
        return UIImage(cgImage: pixels, scale: 1, orientation: .up)
    }

    //MARK: View Lift Cycle
    override open func viewDidLoad() {
        super.viewDidLoad()
        self.view.backgroundColor = .blackBackgroundColor
        
        self.view.addSubview(preview)
        preview.snp.makeConstraints { (make) in
            make.edges.equalTo(view.safeAreaLayoutGuide).inset(UIEdgeInsets(top: 0, left: 0, bottom: 49, right: 0))
        }
        
        toolBar.delegate = self
        self.view.addSubview(toolBar)
        toolBar.snp.makeConstraints  { (make) in
            make.height.equalTo(49)
            make.left.right.bottom.equalTo(view.safeAreaLayoutGuide)
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
        filterType = data.filterType
        overlayView.restore(data)
    }
}

// MARK: - EditPhotoPanel Delegate
extension BaseEditPhotoController: EditPhotoToolBarDelegate {
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectBubble bubble: BubbleModel) {
        self.overlayView.addBubble(bubble)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectSticker sticker: StickerModel) {
        self.overlayView.addSticker(sticker)
    }
    
    public func editPhotoToolBar(_ editPhotoToolBar: EditPhotoToolBar, didSelectFilter filter: FilterType) {
        filterType = filter
    }
}
