import XCTest
import SwiftUI
import UIKit
@testable import CelluloidKit

@MainActor
final class SwiftUIOriginalDesignTests: XCTestCase {
    private func image() -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: CGSize(width: 300, height: 200), format: format).image { context in
            UIColor.white.setFill(); context.fill(CGRect(x: 0, y: 0, width: 300, height: 200))
        }
    }
    private func mount(_ session: CelluloidEditingSession) -> CelluloidCanvasSurface {
        let canvas = session.canvas
        canvas.frame = CGRect(x: 0, y: 0, width: 300, height: 200)
        canvas.didChange = { [weak session] recipe, selected, token, revision in
            session?.acceptCanvasSnapshot(recipe, selected: selected, session: token, revision: revision)
        }
        refresh(canvas, session: session)
        return canvas
    }
    private func refresh(_ canvas: CelluloidCanvasSurface, session: CelluloidEditingSession) {
        canvas.update(image: session.previewImage, recipe: session.adjustment, revision: session.revision,
                      logicalImageSize: session.sourceImage?.size, session: session.sessionIdentity, editable: session.canEdit,
                      scene: session.canvasIdentity)
        canvas.layoutIfNeeded()
    }
    private func bubble(in canvas: CelluloidCanvasSurface) throws -> BubbleView {
        let overlay = try XCTUnwrap(canvas.imageView.subviews.first as? ImageOverlayView)
        return try XCTUnwrap(overlay.subviews.compactMap { $0 as? BubbleView }.first)
    }
    func testNewArtworkRetainsOriginalDefaultPosition() {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[0]); session.addSticker(StickerModel.stickers[0])
        XCTAssertEqual(session.adjustment.bubbles[0].center, CGPoint(x: 100, y: 100))
        XCTAssertEqual(session.adjustment.stickers[0].center, CGPoint(x: 100, y: 100))
    }
    func testNativeCanvasControlsAndAffineChangesUpdateOwningRecipe() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[4])
        let canvas = mount(session), bubble = try bubble(in: canvas)
        XCTAssertTrue(canvas.imageView.isUserInteractionEnabled)
        XCTAssertFalse(canvas.isAccessibilityElement)
        XCTAssertTrue(bubble.imageView.isAccessibilityElement)
        XCTAssertEqual(bubble.imageView.accessibilityIdentifier, "attachment-image")
        bubble.tap()
        XCTAssertFalse(bubble.hideButtonEnable)
        XCTAssertFalse(bubble.deleteButton.isHidden)
        XCTAssertFalse(bubble.resizeButton.isHidden)
        XCTAssertTrue(bubble.resizeButton.gestureRecognizers?.contains(where: { $0 is UIPanGestureRecognizer }) == true)
        let affine = CGAffineTransform(a: 0.8, b: 0.2, c: -0.3, d: 0.9, tx: 3, ty: -2)
        bubble.transform = affine
        bubble.center = CGPoint(x: 124, y: 83)
        bubble.bounds = CGRect(x: 0, y: 0, width: 110, height: 92)
        let persisted = try AdjustmentData.decode(session.adjustment.encode())
        XCTAssertEqual(persisted.bubbles[0].transform, affine)
        XCTAssertEqual(persisted.bubbles[0].center, bubble.center)
        XCTAssertEqual(persisted.bubbles[0].bounds, bubble.bounds)
    }
    func testAddingAndEditingPreserveOriginalLiveStackingAndHitOrder() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addSticker(StickerModel.stickers[0])
        let canvas = mount(session)
        session.addBubble(BubbleModel.bubbles[0]); refresh(canvas, session: session)
        let overlay = try XCTUnwrap(canvas.imageView.subviews.first as? ImageOverlayView)
        let top = try XCTUnwrap(overlay.subviews.last as? BubbleView)
        XCTAssertEqual(top.center, CGPoint(x: 100, y: 100))
        let hit = overlay.hitTest(top.center, with: nil)
        XCTAssertTrue(hit === top || hit?.isDescendant(of: top) == true)
        session.selectFilter(.Sepia); refresh(canvas, session: session)
        XCTAssertTrue(overlay.subviews.last is BubbleView, "Filtering must not swap overlapping live hit targets")
        session.updateText("Caption", layer: .bubble(0), session: session.sessionIdentity)
        refresh(canvas, session: session)
        XCTAssertTrue(overlay.subviews.last is BubbleView, "Caption editing must preserve live order")
        session.addSticker(StickerModel.stickers[1]); refresh(canvas, session: session)
        XCTAssertTrue(overlay.subviews.last is StickerView, "New artwork must append on top")
        let canonical = session.adjustment
        session.restore(canonical); refresh(canvas, session: session)
        XCTAssertTrue(overlay.subviews.first is BubbleView, "A true archive restoration retains original grouped semantics")
        XCTAssertEqual(session.adjustment.stickers.count, 2)
    }
    func testDismantledCanvasRestoresInteractionOnRemount() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[0])
        let canvas = mount(session)
        CelluloidEditorCanvas.dismantleUIView(canvas, coordinator: ())
        XCTAssertFalse(canvas.isUserInteractionEnabled)
        XCTAssertNil(canvas.didChange)
        _ = mount(session)
        XCTAssertTrue(canvas.isUserInteractionEnabled)
        XCTAssertTrue(canvas.imageView.isUserInteractionEnabled)
        let restored = try bubble(in: canvas)
        restored.tap()
        XCTAssertFalse(restored.hideButtonEnable)
        restored.center.x += 10
        XCTAssertEqual(session.adjustment.bubbles.first?.center, restored.center)
    }
    func testCaptionRequestUsesSwiftUIRouteAndKeepsCompleteAccessibleText() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        var model = BubbleModel.bubbles[4]; model.content = "Original caption 世界"
        session.addBubble(model)
        let canvas = mount(session), bubble = try bubble(in: canvas)
        var requested: (CelluloidEditingSession.Layer, String, UUID)?
        canvas.didRequestText = { requested = ($0, $1, $2) }
        bubble.editText()
        XCTAssertEqual(requested?.0, .bubble(0))
        XCTAssertEqual(requested?.1, model.content)
        XCTAssertEqual(requested?.2, session.sessionIdentity)
        XCTAssertEqual(bubble.imageView.accessibilityValue, model.content)
    }
    func testDeleteCannotExportShrinkingGhostBeforeAnimationCompletes() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[0])
        let canvas = mount(session), bubble = try bubble(in: canvas)
        bubble.removeSelf()
        // The original delete animation remains visible, but the recipe already
        // excludes that layer if the user immediately presses Done.
        XCTAssertTrue(session.adjustment.bubbles.isEmpty)
        XCTAssertTrue(canvas.snapshot(session: session.sessionIdentity, revision: session.revision)?.recipe.bubbles.isEmpty == true)
    }
    func testOldNativeCallbackCannotMutateReplacementInput() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[0])
        let canvas = mount(session), oldBubble = try bubble(in: canvas)
        session.startCopy(image: image())
        oldBubble.center.x += 20
        XCTAssertTrue(session.adjustment.bubbles.isEmpty)
        XCTAssertNil(session.selectedLayer)
    }
    func testHostedSessionReleasesAfterViewTeardown() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let window = UIWindow(windowScene: scene)
        defer { window.rootViewController = nil; window.isHidden = true }
        weak var weakSession: CelluloidEditingSession?
        weak var weakHost: UIHostingController<CelluloidEditorContent>?
        weak var weakCanvas: CelluloidCanvasSurface?
        weak var weakPresentation: CelluloidEditorPresentation?
        // Drain UIKit/SwiftUI temporary Objective-C objects before diagnosing a
        // retain cycle. Keep the actual window alive throughout the release test.
        try autoreleasepool {
            var session: CelluloidEditingSession? = CelluloidEditingSession()
            session?.startCopy(image: image())
            var presentation: CelluloidEditorPresentation? = CelluloidEditorPresentation()
            weakSession = session; weakPresentation = presentation; weakCanvas = session?.canvas
            var host: UIHostingController<CelluloidEditorContent>? = UIHostingController(rootView:
                CelluloidEditorContent(session: try XCTUnwrap(session), presentation: try XCTUnwrap(presentation)))
            weakHost = host
            window.rootViewController = host; window.makeKeyAndVisible()
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                host?.view.layoutIfNeeded()
                return session?.adjustment.referenceCanvasSize != nil && session?.previewIsLoading == false
            }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed)
            XCTAssertTrue(host?.view.window === window)
            // Exercise real hosting teardown. Do not clear native callbacks,
            // call dismantle directly, or cancel the session to force release.
            window.rootViewController = nil; window.isHidden = true
            host = nil; presentation = nil; session = nil
        }
        let released = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in weakSession == nil }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [released], timeout: 5), .completed,
                       "Canvas presentation callbacks must not retain the owning SwiftUI session")
        XCTAssertNil(weakHost, "The hosting controller must be released after removal from the live window")
        XCTAssertNil(weakPresentation, "The routing state must not be retained by a native callback")
        XCTAssertNil(weakCanvas, "The released session must not leave its canvas alive")
    }
    func testLegacyNoCanvasRecipeUsesOriginalEditorLayoutOracle() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        for size in [CGSize(width: 375, height: 667), CGSize(width: 667, height: 375),
                     CGSize(width: 768, height: 1024), CGSize(width: 1024, height: 768)] {
            try autoreleasepool {
                let source = image()
                var legacy = AdjustmentData()
                var model = BubbleModel.bubbles[4]; model.content = "Legacy canvas"
                model.transform = CGAffineTransform(a: 0.8, b: 0.2, c: -0.2, d: 0.8, tx: 3, ty: -2)
                legacy.bubbles = [model]
                XCTAssertNil(legacy.referenceCanvasSize)
                let oracle = BaseEditPhotoController()
                let session = CelluloidEditingSession()
                let host = UIHostingController(rootView: CelluloidEditorContent(session: session))
                let container = UIViewController()
                let window = UIWindow(windowScene: scene)
                window.frame = CGRect(origin: .zero, size: size)
                window.rootViewController = container
                container.loadViewIfNeeded()
                for child in [oracle as UIViewController, host] {
                    container.addChild(child)
                    child.view.frame = container.view.bounds
                    child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
                    container.view.addSubview(child.view)
                    child.didMove(toParent: container)
                }
                window.makeKeyAndVisible()
                window.frame = CGRect(origin: .zero, size: size)
                container.view.frame = window.bounds
                for child in [oracle as UIViewController, host] { child.view.frame = container.view.bounds }
                XCTAssertEqual(container.view.bounds.size, size)
                defer {
                    for child in [oracle as UIViewController, host] {
                        child.willMove(toParent: nil)
                        child.view.removeFromSuperview(); child.removeFromParent()
                    }
                    window.rootViewController = nil; window.isHidden = true
                }
                // Both implementations receive the same mounted window, frame
                // and safe area before either adopts legacy absolute coordinates.
                container.view.layoutIfNeeded()
                oracle.view.layoutIfNeeded(); host.view.layoutIfNeeded()
                XCTAssertTrue(oracle.view.window === window)
                XCTAssertTrue(host.view.window === window)
                XCTAssertEqual(oracle.view.bounds, host.view.bounds)
                XCTAssertEqual(oracle.view.safeAreaInsets, host.view.safeAreaInsets)
                oracle.sourceImage = source; oracle.restoreFromData(legacy); oracle.view.layoutIfNeeded()
                let expected = oracle.adjustmentData
                session.startCopy(image: source); session.restore(legacy)
                let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                    container.view.setNeedsLayout(); container.view.layoutIfNeeded()
                    host.view.setNeedsLayout(); host.view.layoutIfNeeded()
                    return session.adjustment.referenceCanvasSize != nil && !session.previewIsLoading
                }, object: nil)
                XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed)
                XCTAssertEqual(session.adjustment.referenceCanvasSize, expected.referenceCanvasSize,
                               "Original toolbar allocation must precede legacy absolute-coordinate restoration")
                XCTAssertEqual(session.adjustment.bubbles[0].center, expected.bubbles[0].center)
                XCTAssertEqual(session.adjustment.bubbles[0].transform, expected.bubbles[0].transform)
                // Keep the immutable original-photo export pixel oracle as a native
                // gate, not a source-only assertion about the new SwiftUI layout.
                let expectedImage = try XCTUnwrap(oracle.outputImage)
                let actualImage = try XCTUnwrap(session.outputImageForTesting)
                XCTAssertEqual(actualImage.pngData(), expectedImage.pngData())
            }
        }
    }
}
