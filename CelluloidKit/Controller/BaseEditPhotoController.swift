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
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        func finish(_ result: Result<PhotoExport, PhotoExportError>) {
            DispatchQueue.main.async {
                completion(task.isCancelled ? .failure(.cancelled) : result)
            }
        }
        func encode(_ image: UIImage) {
            Self.exportQueue.async {
                autoreleasepool {
                    guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                    #if DEBUG
                    PhotoExportDiagnostics.trace("jpeg-start", source: image.cgImage)
                    #endif
                    guard let jpeg = image.jpegData(compressionQuality: 1) else { finish(.failure(.encodingFailed)); return }
                    #if DEBUG
                    PhotoExportDiagnostics.trace("jpeg-finished", source: image.cgImage)
                    #endif
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
                #if DEBUG
                PhotoExportDiagnostics.trace("source-prepared-not-necessarily-decoded", source: image.cgImage)
                #endif
                if data.bubbles.isEmpty && data.stickers.isEmpty {
                    // No UIKit render or additional full-size backing surface.
                    encode(image)
                } else {
                    guard let models = Self.scaledOverlayModels(for: image.size, data: data),
                          let source = image.cgImage else { finish(.failure(.invalidState)); return }
                    let result = Self.compositeOffMain(source, size: image.size, models: models, format: format, task: task,
                        bounds: { model in
                            DispatchQueue.main.sync {
                                guard self != nil, !task.isCancelled else { return .failure(.cancelled) }
                                return Self.overlayBounds(model, size: image.size)
                            }
                        }, rasterize: { model, rect in
                            DispatchQueue.main.sync {
                                guard self != nil, !task.isCancelled else { return .failure(.cancelled) }
                                return Self.rasterizeOverlay(model, size: image.size, rect: rect)
                            }
                        })
                    switch result {
                    case .failure(let error): finish(.failure(error))
                    case .success(let output): encode(output)
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

    private struct OverlayRaster {
        let image: CGImage
        let rect: CGRect
    }

    private enum OverlayModel { case bubble(BubbleModel), sticker(StickerModel) }

    private nonisolated static func scaledOverlayModels(for size: CGSize, data: AdjustmentData) -> [OverlayModel]? {
        guard let canvas = data.referenceCanvasSize, AdjustmentData.isValidReferenceCanvas(canvas),
              size.width > 0, size.height > 0 else { return nil }
        let sx = size.width / canvas.width, sy = size.height / canvas.height
        guard sx.isFinite, sy.isFinite, sx > 0, sy > 0,
              data.bubbles.allSatisfy({ hasRenderableGeometry(center: CGPoint(x: $0.center.x * sx, y: $0.center.y * sy), bounds: $0.bounds, transform: $0.transform.scaledInCanvas(x: sx, y: sy)) }),
              data.stickers.allSatisfy({ hasRenderableGeometry(center: CGPoint(x: $0.center.x * sx, y: $0.center.y * sy), bounds: $0.bounds, transform: $0.transform.scaledInCanvas(x: sx, y: sy)) }) else { return nil }
        // Only immutable model metadata is buffered, never a list of full-size rasters.
        return data.bubbles.map { model in
            var scaled = model
            scaled.center = CGPoint(x: sx * model.center.x, y: sy * model.center.y)
            scaled.transform = model.transform.scaledInCanvas(x: sx, y: sy)
            return OverlayModel.bubble(scaled)
        } + data.stickers.map { model in
            var scaled = model
            scaled.center = CGPoint(x: sx * model.center.x, y: sy * model.center.y)
            scaled.transform = model.transform.scaledInCanvas(x: sx, y: sy)
            return OverlayModel.sticker(scaled)
        }
    }

    private static func withArtwork<T>(_ model: OverlayModel, size: CGSize, body: (UIView, AttachView) -> T) -> T {
        precondition(Thread.isMainThread)
        return autoreleasepool {
            let artwork: AttachView
            switch model {
            case .bubble(let model): artwork = BubbleView(bubbleModel: model)
            case .sticker(let model): artwork = StickerView(stickerModel: model)
            }
            let holder = UIView(frame: CGRect(origin: .zero, size: size))
            holder.isOpaque = false
            holder.backgroundColor = .clear
            holder.addSubview(artwork)
            holder.layoutIfNeeded(); artwork.layoutIfNeeded()
            return body(holder, artwork)
        }
    }

    private static func overlayBounds(_ model: OverlayModel, size: CGSize) -> Result<CGRect?, PhotoExportError> {
        withArtwork(model, size: size) { _, artwork in
            let rect = artwork.frame.insetBy(dx: -1, dy: -1).integral.intersection(CGRect(origin: .zero, size: size))
            return .success(rect.isNull || rect.isEmpty ? nil : rect)
        }
    }

    private static func rasterizeOverlay(_ model: OverlayModel, size: CGSize, rect: CGRect) -> Result<OverlayRaster, PhotoExportError> {
        withArtwork(model, size: size) { holder, _ in
            // Integer pixel tiles retain the same global affine phase and exact
            // typography. Reconstruction avoids retaining UIKit objects off-main.
            let format = UIGraphicsImageRendererFormat(); format.scale = 1
            let image = UIGraphicsImageRenderer(size: rect.size, format: format).image { context in
                context.cgContext.translateBy(x: -rect.minX, y: -rect.minY)
                holder.layer.render(in: context.cgContext)
            }
            guard let pixels = image.cgImage else { return .failure(.encodingFailed) }
            return .success(OverlayRaster(image: pixels, rect: rect))
        }
    }

    private nonisolated static func compositeOffMain(_ source: CGImage, size: CGSize, models: [OverlayModel],
            format: UIGraphicsImageRendererFormat, task: PhotoExportTask,
            bounds: (OverlayModel) -> Result<CGRect?, PhotoExportError>,
            rasterize: (OverlayModel, CGRect) -> Result<OverlayRaster, PhotoExportError>) -> Result<UIImage, PhotoExportError> {
        precondition(!Thread.isMainThread)
        guard !task.isCancelled else { return .failure(.cancelled) }
        // Determine the existing UIKit renderer's actual output bitmap policy.
        // Do not force standard range, discard alpha, or substitute a color space.
        let prototype = UIGraphicsImageRenderer(size: CGSize(width: 1, height: 1), format: format).image { rendered in
            rendered.cgContext.translateBy(x: 0, y: 1)
            rendered.cgContext.scaleBy(x: 1, y: -1)
            rendered.cgContext.draw(source, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        }
        guard !task.isCancelled else { return .failure(.cancelled) }
        guard let sample = prototype.cgImage, let colorSpace = sample.colorSpace,
              let context = CGContext(data: nil, width: source.width, height: source.height,
                bitsPerComponent: sample.bitsPerComponent, bytesPerRow: 0,
                space: colorSpace, bitmapInfo: sample.bitmapInfo.rawValue), context.data != nil else {
            return .failure(.encodingFailed)
        }
        // A concrete bitmap consumes each draw immediately. UIGraphics may record
        // deferred commands and retain every image even if the Swift array is gone.
        context.clear(CGRect(origin: .zero, size: size))
        context.translateBy(x: 0, y: size.height)
        context.scaleBy(x: 1, y: -1)
        #if DEBUG
        task.recordCompositionStorage(context.bytesPerRow * context.height)
        PhotoExportDiagnostics.trace("streaming-bitmap-created", source: sample, context: context, format: format)
        #endif
        func draw(_ image: CGImage, in rect: CGRect) {
            context.saveGState()
            context.translateBy(x: rect.minX, y: rect.maxY)
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(origin: .zero, size: rect.size))
            context.restoreGState()
        }
        guard !task.isCancelled else { return .failure(.cancelled) }
        draw(source, in: CGRect(origin: .zero, size: size))
        for model in models {
            guard !task.isCancelled else { return .failure(.cancelled) }
            let region: CGRect
            switch bounds(model) {
            case .failure(let error): return .failure(error)
            case .success(nil): continue
            case .success(let rect?): region = rect
            }
            // Independent of decoration count and photo size, keep only one
            // <=1024x1024 full-resolution raster beside the composition bitmap.
            let edge: CGFloat = 1024
            var y = region.minY
            while y < region.maxY {
                var x = region.minX
                while x < region.maxX {
                    guard !task.isCancelled else { return .failure(.cancelled) }
                    let rect = CGRect(x: x, y: y, width: min(edge, region.maxX - x), height: min(edge, region.maxY - y))
                    let result: Result<Void, PhotoExportError> = autoreleasepool {
                        switch rasterize(model, rect) {
                        case .failure(let error): return .failure(error)
                        case .success(let raster):
                            #if DEBUG
                            let bytes = raster.image.bytesPerRow * raster.image.height
                            task.beginRasterStorage(bytes, width: raster.image.width, height: raster.image.height)
                            defer { task.endRasterStorage(bytes) }
                            #endif
                            guard !task.isCancelled else { return .failure(.cancelled) }
                            draw(raster.image, in: raster.rect)
                            #if DEBUG
                            task.recordConsumedRaster()
                            #endif
                            return .success(())
                        }
                    }
                    if case .failure(let error) = result { return .failure(error) }
                    x += rect.width
                }
                y += min(edge, region.maxY - y)
            }
            #if DEBUG
            task.recordCompletedOverlay()
            #endif
        }
        guard !task.isCancelled else { return .failure(.cancelled) }
        guard let image = context.makeImage() else { return .failure(.encodingFailed) }
        return .success(UIImage(cgImage: image, scale: 1, orientation: .up))
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
        
        toolBar.delegate = self
        self.view.addSubview(preview)
        self.view.addSubview(toolBar)
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
