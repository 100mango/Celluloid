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
    #if DEBUG
    var activeExportForTesting: PhotoExportTask? { activeExport }
    #endif

    public func cancelExport() { activeExport?.cancel(); activeExport = nil }
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
        guard !isAdjustmentReadOnly else { return nil }
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
        guard !isAdjustmentReadOnly else {
            DispatchQueue.main.async { completion(.failure(task.isCancelled ? .cancelled : .invalidState)) }
            return task
        }
        let data = adjustmentData
        let url = input?.fullSizeImageURL
        let orientation = input?.fullSizeImageOrientation
        let fallback = input == nil ? sourceImage : nil
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        #if DEBUG
        let fullCanvasControl = getenv("CELLULOID_EXPORT_FULL_CANVAS_CONTROL").map { String(cString: $0) }
        let cropSource = getenv("CELLULOID_EXPORT_WARMING_ONLY_CONTROL") == nil
        #else
        let cropSource = true
        #endif
        func finish(_ result: Result<PhotoExport, PhotoExportError>) {
            DispatchQueue.main.async {
                completion(task.isCancelled ? .failure(.cancelled) : result)
            }
        }
        func encode(_ image: UIImage, archive: Data) {
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
                    finish(.success(PhotoExport(image: image, jpegData: jpeg, adjustmentData: archive)))
                }
            }
        }
        Self.exportQueue.async { [weak self] in
            autoreleasepool {
                guard !task.isCancelled else { finish(.failure(.cancelled)); return }
                // Validate/archive the immutable edit before original-image
                // decoding, compositing or JPEG allocation. Refuse the whole
                // snapshot without truncating the live editor's models/text.
                let archive: Data
                do { archive = try data.encode() }
                catch AdjustmentDataError.resourceLimit(_) { finish(.failure(.adjustmentTooComplex)); return }
                catch { finish(.failure(.invalidState)); return }
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
                    encode(image, archive: archive)
                } else {
                    guard let models = Self.scaledOverlayModels(for: image.size, data: data),
                          let source = image.cgImage else { finish(.failure(.invalidState)); return }
                    #if DEBUG
                    if let mode = fullCanvasControl {
                        // Experimental control: original global layer coordinates,
                        // warmed off-main, with one full-canvas UIKit surface.
                        guard let warmed = Self.materializedImage(source) else { finish(.failure(.encodingFailed)); return }
                        defer { withExtendedLifetime(warmed.pixels) {} }
                        let control: Result<OverlayRaster, PhotoExportError> = DispatchQueue.main.sync {
                            guard self != nil, !task.isCancelled else { return .failure(.cancelled) }
                            return Self.rasterizeScene(warmed.image, size: image.size, models: models,
                                rect: CGRect(origin: .zero, size: image.size), format: format, directSource: mode == "direct")
                        }
                        switch control {
                        case .failure(let error): finish(.failure(error))
                        case .success(let tile): encode(UIImage(cgImage: tile.image, scale: 1, orientation: .up), archive: archive)
                        }
                        return
                    }
                    #endif
                    let result = Self.compositeOffMain(source, size: image.size, models: models, task: task, cropSource: cropSource) { decoded, rect in
                        DispatchQueue.main.sync {
                            guard self != nil, !task.isCancelled else { return .failure(.cancelled) }
                            return Self.rasterizeScene(decoded, size: image.size, models: models, rect: rect, format: format, directSource: true, sourceRect: cropSource ? rect : nil)
                        }
                    }
                    switch result {
                    case .failure(let error): finish(.failure(error))
                    case .success(let output): encode(output, archive: archive)
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

    private static func rasterizeScene(_ source: CGImage, size: CGSize, models: [OverlayModel], rect: CGRect,
                                       format: UIGraphicsImageRendererFormat, globalBounds: Bool = false, directSource: Bool = false, sourceRect: CGRect? = nil) -> Result<OverlayRaster, PhotoExportError> {
        precondition(Thread.isMainThread)
        return autoreleasepool {
            // Render the complete original layer stack in each final-output tile.
            // Quantizing each decoration separately changes overlapping alpha/HDR.
            let holder: UIView = directSource ? UIView() : UIImageView(image: UIImage(cgImage: source, scale: 1, orientation: .up))
            holder.frame = CGRect(origin: .zero, size: size)
            for model in models {
                switch model {
                case .bubble(let value): holder.addSubview(BubbleView(bubbleModel: value))
                case .sticker(let value): holder.addSubview(StickerView(stickerModel: value))
                }
            }
            holder.layoutIfNeeded(); holder.subviews.forEach { $0.layoutIfNeeded() }
            let renderer = globalBounds ? UIGraphicsImageRenderer(bounds: rect, format: format) : UIGraphicsImageRenderer(size: rect.size, format: format)
            let image = renderer.image { context in
                if !globalBounds { context.cgContext.translateBy(x: -rect.minX, y: -rect.minY) }
                if directSource {
                    context.cgContext.saveGState()
                    context.cgContext.translateBy(x: 0, y: size.height)
                    context.cgContext.scaleBy(x: 1, y: -1)
                    let region = sourceRect ?? CGRect(origin: .zero, size: size)
                    context.cgContext.draw(source, in: CGRect(x: region.minX, y: size.height - region.maxY,
                                                              width: region.width, height: region.height))
                    context.cgContext.restoreGState()
                }
                holder.layer.render(in: context.cgContext)
            }
            guard let pixels = image.cgImage else { return .failure(.encodingFailed) }
            return .success(OverlayRaster(image: pixels, rect: rect))
        }
    }

    #if DEBUG
    // Bounded synthetic failure diagnostics; never used by the shipping save path.
    func diagnosticSpatialRender(rect: CGRect, globalBounds: Bool) -> UIImage? {
        precondition(Thread.isMainThread)
        let data = adjustmentData
        guard let image = Self.prepareFullSizeImage(url: input?.fullSizeImageURL,
                orientation: input?.fullSizeImageOrientation, fallback: input == nil ? sourceImage : nil, filter: data.filterType),
              let source = image.cgImage, let models = Self.scaledOverlayModels(for: image.size, data: data) else { return nil }
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        switch Self.rasterizeScene(source, size: image.size, models: models, rect: rect, format: format, globalBounds: globalBounds) {
        case .failure: return nil
        case .success(let tile): return UIImage(cgImage: tile.image, scale: 1, orientation: .up)
        }
    }
    #endif

    private nonisolated static func materializedImage(_ source: CGImage) -> (image: CGImage, pixels: CFData)? {
        // Warm native pixels on the export queue, but retain the original CGImage.
        // Reconstructing from bitmap fields can discard supplemental image/HDR
        // metadata. Pixel warming does not prove every platform decode is eager.
        let (required, overflow) = source.bytesPerRow.multipliedReportingOverflow(by: source.height)
        guard !overflow, let pixels = source.dataProvider?.data, CFDataGetLength(pixels) >= required else { return nil }
        return (source, pixels)
    }

    private nonisolated static func compositeOffMain(_ source: CGImage, size: CGSize, models: [OverlayModel], task: PhotoExportTask, cropSource: Bool,
            rasterize: (CGImage, CGRect) -> Result<OverlayRaster, PhotoExportError>) -> Result<UIImage, PhotoExportError> {
        precondition(!Thread.isMainThread)
        guard !task.isCancelled else { return .failure(.cancelled) }
        // Warm on this queue, then release the temporary provider copy before
        // allocating the destination. Keep the original image and its metadata.
        guard let decoded = autoreleasepool(invoking: { materializedImage(source)?.image }) else { return .failure(.encodingFailed) }
        guard !task.isCancelled else { return .failure(.cancelled) }
        #if DEBUG
        PhotoExportDiagnostics.trace("source-warmed-copy-released", source: decoded)
        #endif
        var destination: CGContext?
        // Keep the original vertical drawing coordinates: UIKit text coverage
        // can differ when its canvas is split horizontally, even away from seams.
        // A fixed pixel budget bounds each full-height strip independently of
        // decoration count. Exceptionally tall images need at least one column;
        // they retain full resolution rather than being rejected/downsampled.
        let pixelBudget = max(1024 * 1024, source.height)
        let maximumWidth = max(1, pixelBudget / source.height)
        let gutter = maximumWidth >= 5 ? 2 : 0
        let edge = max(1, maximumWidth - 2 * gutter)
        let y = 0
        var x = 0
        while x < source.width {
            guard !task.isCancelled else { return .failure(.cancelled) }
            let width = min(edge, source.width - x), height = source.height
            let rect = CGRect(x: x, y: y, width: width, height: height)
            // Record a small surrounding region, then copy only the interior.
            // This keeps antialiasing/image sampling away from tile clip edges.
            let expanded = rect.insetBy(dx: -CGFloat(gutter), dy: 0)
                .intersection(CGRect(origin: .zero, size: size))
            let result: Result<Void, PhotoExportError> = autoreleasepool {
                // A native crop retains the original image; only the source
                // region that contributes to this strip is drawn, at 1:1 pixels.
                let cropped: CGImage? = cropSource ? decoded.cropping(to: expanded) : decoded
                guard let portion = cropped else { return .failure(.encodingFailed) }
                switch rasterize(portion, expanded) {
                case .failure(let error): return .failure(error)
                case .success(let raster):
                    let tile = raster.image
                    let offsetX = x - Int(raster.rect.minX), offsetY = y - Int(raster.rect.minY)
                    guard offsetX >= 0, offsetY >= 0,
                          offsetX + width <= tile.width, offsetY + height <= tile.height,
                          let space = tile.colorSpace, let pixels = tile.dataProvider?.data,
                          let bytes = CFDataGetBytePtr(pixels), tile.bitsPerPixel > 0, tile.bitsPerPixel % 8 == 0,
                          tile.bytesPerRow >= tile.width * (tile.bitsPerPixel / 8),
                          CFDataGetLength(pixels) >= tile.bytesPerRow * tile.height else { return .failure(.encodingFailed) }
                    // The actual first finished UIKit tile determines bitmap
                    // policy, including extended range. Later tiles must match.
                    if destination == nil {
                        destination = CGContext(data: nil, width: source.width, height: source.height,
                            bitsPerComponent: tile.bitsPerComponent, bytesPerRow: 0,
                            space: space, bitmapInfo: tile.bitmapInfo.rawValue)
                        destination?.clear(CGRect(origin: .zero, size: size))
                        #if DEBUG
                        if let context = destination {
                            task.recordCompositionStorage(context.bytesPerRow * context.height)
                            PhotoExportDiagnostics.trace("spatial-bitmap-created", source: tile, context: context)
                        }
                        #endif
                    }
                    guard let context = destination, let target = context.data,
                          context.bitsPerComponent == tile.bitsPerComponent, context.bitsPerPixel == tile.bitsPerPixel,
                          context.bitmapInfo == tile.bitmapInfo, let destinationSpace = context.colorSpace,
                          CFEqual(destinationSpace, space) else { return .failure(.encodingFailed) }
                    #if DEBUG
                    // Conservatively count both native tile and provider copy.
                    let storage = tile.bytesPerRow * tile.height + CFDataGetLength(pixels)
                    task.beginRasterStorage(storage, width: tile.width, height: tile.height)
                    defer { task.endRasterStorage(storage) }
                    #endif
                    guard !task.isCancelled else { return .failure(.cancelled) }
                    let bytesPerPixel = tile.bitsPerPixel / 8
                    for row in 0..<height {
                        // Native CGImage rows are copied without another blend,
                        // color conversion or premultiplication/quantization.
                        target.advanced(by: (y + row) * context.bytesPerRow + x * bytesPerPixel)
                            .copyMemory(from: bytes.advanced(by: (offsetY + row) * tile.bytesPerRow + offsetX * bytesPerPixel), byteCount: width * bytesPerPixel)
                    }
                    #if DEBUG
                    task.recordConsumedRaster()
                    #endif
                    return .success(())
                }
            }
            if case .failure(let error) = result { return .failure(error) }
            x += width
        }
        guard !task.isCancelled else { return .failure(.cancelled) }
        guard let image = destination?.makeImage() else { return .failure(.encodingFailed) }
        #if DEBUG
        for _ in models { task.recordCompletedOverlay() }
        #endif
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
