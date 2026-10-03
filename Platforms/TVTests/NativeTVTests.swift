import XCTest
import UIKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidTV

final class NativeTVTests: XCTestCase {
    @MainActor func testNativeTVExecutableAndScene() {
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "appletvsimulator")
        XCTAssertFalse(UIApplication.shared.connectedScenes.isEmpty)
        print("TV_NATIVE_RUNTIME bundle=\(Bundle.main.bundleURL.path)")
    }
    func testRecoverableRecipeRoundtripAndStrictMetadataBudget() throws {
        var recipe = EditRecipe()
        let source = SourceImage(displayName: "Synthetic", pixelWidth: 1200, pixelHeight: 800)
        recipe.sources = [source]; recipe.canvasWidth = 1200; recipe.canvasHeight = 800
        recipe.overlays = [Overlay(bubble: .say1, text: "TV 世界")]
        let saved = TVSavedRecipe(recipe: recipe, photoIDs: [source.id: "synthetic-photos-identifier"], fingerprints: [source.id: String(repeating: "a", count: 64)])
        XCTAssertEqual(try TVSavedRecipe.decode(saved.encoded()), saved)
        XCTAssertLessThan(try saved.encoded().count, 256 * 1024)
        var invalid = saved; invalid.photoIDs.removeAll(); XCTAssertThrowsError(try invalid.encoded())
        invalid = saved; invalid.version = 2; XCTAssertThrowsError(try invalid.encoded())
        invalid = saved
        invalid.recipe.overlays = (0..<100).map { _ in Overlay(bubble: .say1, text: String(repeating: "a", count: 16_384)) }
        XCTAssertThrowsError(try invalid.encoded())
        XCTAssertThrowsError(try TVSavedRecipe.decode(Data(repeating: 0, count: TVSavedRecipe.maximumBytes + 1)))
    }
    @MainActor func testTVImageProofDetectsColorAndDimensionChanges() throws {
        func picture(_ red: CGFloat) throws -> Data {
            let context = try RasterCodec.bitmap(width: 120, height: 80)
            context.setFillColor(CGColor(srgbRed: red, green: 0, blue: 0, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
            return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
        }
        let a = try picture(1), b = try picture(0)
        XCTAssertEqual(try TVPhotoLibrary.normalizedProof(a), try TVPhotoLibrary.normalizedProof(a))
        XCTAssertNotEqual(try TVPhotoLibrary.normalizedProof(a), try TVPhotoLibrary.normalizedProof(b))
        XCTAssertThrowsError(try TVPhotoLibrary.normalizedProof(Data()))
    }
    @MainActor func testSameDimensionSourceReplacementKeepsCurrentCompositionIntact() async throws {
        func png(_ red: CGFloat) throws -> Data {
            let bitmap = try RasterCodec.bitmap(width: 12,height: 8)
            bitmap.setFillColor(CGColor(srgbRed: red,green: 0.3,blue: 0.7,alpha: 1));bitmap.fill(CGRect(x: 0,y: 0,width: 12,height: 8))
            return try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()),as:.png)
        }
        let suite = "Celluloid.TV.Test." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        let source = StubPhotoSource(bytes: try png(1))
        let model = TVEditorModel(defaults: defaults)
        await model.importPhotos(["same-asset-id"],library:source); model.keepRecipe()
        let previousRecipe = model.recipe, previousBytes = model.originals
        source.bytes = try png(0)
        XCTAssertEqual(try RasterCodec.metadata(source.bytes).pixelWidth,12)
        await model.reopen(library:source)
        XCTAssertEqual(model.recipe,previousRecipe);XCTAssertEqual(model.originals,previousBytes)
        XCTAssertEqual(model.error,TVPhotoError.changed.localizedDescription)
    }
    @MainActor func testLateTextCommitTargetsItsOriginalLayerAndPreservesTransformAndReopen() async throws {
        let suite = "Celluloid.TV.FieldMutation." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        bitmap.setFillColor(CGColor(srgbRed: 0.1, green: 0.5, blue: 0.8, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        let library = StubPhotoSource(bytes: try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png))
        for textFirst in [true, false] {
            let model = TVEditorModel(defaults: defaults)
            await model.importPhotos(["owned-synthetic-id"], library: library)
            let first = Overlay(bubble: .say1, text: "Hello"), other = Overlay(bubble: .call2, text: "Keep 世界")
            model.add(first); model.add(other)
            // Selection has already moved to the other bubble when the old
            // input control commits. Its captured identity must remain binding.
            if textFirst { model.editLayer(first.id) { $0.text = "Saved 世界" } }
            model.editLayer(first.id) { $0.rotation = 15; $0.centerX = 0.51 }
            if !textFirst { model.editLayer(first.id) { $0.text = "Saved 世界" } }
            XCTAssertEqual(model.recipe.overlays[0].text, "Saved 世界")
            XCTAssertEqual(model.recipe.overlays[0].rotation, 15)
            XCTAssertEqual(model.recipe.overlays[1], other)
            model.undo()
            XCTAssertEqual(model.recipe.overlays[0].text, textFirst ? "Saved 世界" : "Hello")
            XCTAssertEqual(model.recipe.overlays[0].rotation, textFirst ? 0 : 15)
            model.editLayer(first.id) { $0.text = "Saved 世界"; $0.rotation = 15; $0.centerX = 0.51 }
            let exact = model.recipe; model.keepRecipe()
            let reopened = TVEditorModel(defaults: defaults); await reopened.reopen(library: library)
            XCTAssertEqual(reopened.recipe, exact); XCTAssertEqual(reopened.originals, model.originals)
        }
    }
    @MainActor func testCapturedTVActionsUseLatestFieldsAndRejectReplacedOrDeletedTargets() async throws {
        let suite = "Celluloid.TV.Epoch." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        bitmap.setFillColor(CGColor(srgbRed: 0.1, green: 0.5, blue: 0.8, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        let library = StubPhotoSource(bytes: try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png))
        let model = TVEditorModel(defaults: defaults)
        await model.importPhotos(["source-a", "source-b", "source-c"], library: library)
        let layer = Overlay(bubble: .say1, text: "Saved 世界")
        model.add(layer)
        let epoch = model.editEpoch, sourceID = model.recipe.sources[0].id
        let lateText = { (text: String) in model.editLayer(layer.id, epoch: epoch) { $0.text = text } }
        // Invoke the exact same captured action twice, without creating new view props.
        let increase = { model.adjustLayer(layer.id, epoch: epoch, field: \.rotation, delta: 15, range: -180...180) }
        increase(); increase(); XCTAssertEqual(model.recipe.overlays[0].rotation, 30)
        let zoom = { model.adjustSource(sourceID, epoch: epoch, field: \.zoom, delta: 0.25, range: 1...5) }
        let later = { model.moveSource(sourceID, epoch: epoch, offset: 1) }
        later(); later(); zoom(); zoom()
        XCTAssertEqual(model.recipe.sources.last?.id, sourceID)
        XCTAssertEqual(model.recipe.sources.last?.crop.zoom, 1.5)
        XCTAssertEqual(model.recipe.sources.first?.crop.zoom, 1)
        // Reset/removal captured by UUID must still address the moved source.
        model.editSource(sourceID, epoch: epoch) { $0.crop = SourceCrop() }
        XCTAssertEqual(model.recipe.sources.last?.crop, SourceCrop())
        zoom(); let beforeRemoval = model.recipe
        model.removeSource(sourceID, epoch: epoch)
        XCTAssertFalse(model.recipe.sources.contains { $0.id == sourceID })
        let removedRecipe = model.recipe; zoom(); later()
        XCTAssertEqual(model.recipe, removedRecipe)
        model.undo(); XCTAssertEqual(model.recipe, beforeRemoval, "Missing-ID callbacks must not add history")
        // Clamp against the current field, retaining Unicode and unrelated geometry.
        for _ in 0..<20 { increase(); zoom() }
        XCTAssertEqual(model.recipe.overlays[0].rotation, 180)
        XCTAssertEqual(model.recipe.overlays[0].text, "Saved 世界")
        XCTAssertEqual(model.recipe.sources.last?.crop.zoom, 5)
        model.keepRecipe(); let kept = model.recipe, originals = model.originals
        await model.reopen(library: library)
        XCTAssertNotEqual(model.editEpoch, epoch); XCTAssertEqual(model.recipe, kept)
        XCTAssertFalse(model.canUndo)
        lateText("Stale 旧"); increase(); zoom(); later()
        model.deleteLayer(layer.id, epoch: epoch); model.selectLayer(layer.id, epoch: epoch)
        model.removeSource(sourceID, epoch: epoch)
        XCTAssertEqual(model.recipe, kept); XCTAssertEqual(model.originals, originals)
        XCTAssertNil(model.selectedLayer); XCTAssertFalse(model.canUndo)
        // A failed reopen does not replace the document or invalidate live controls.
        let liveEpoch = model.editEpoch
        let liveText = { (text: String) in model.editLayer(layer.id, epoch: liveEpoch) { $0.text = text } }
        library.bytes = Data([0, 1, 2]); await model.reopen(library: library)
        XCTAssertEqual(model.editEpoch, liveEpoch); XCTAssertEqual(model.recipe, kept)
        liveText("Current 当前"); XCTAssertEqual(model.recipe.overlays[0].text, "Current 当前")
        let beforeDelete = model.recipe
        model.deleteLayer(layer.id, epoch: liveEpoch)
        XCTAssertTrue(model.recipe.overlays.isEmpty)
        liveText("Deleted target must stay deleted")
        XCTAssertTrue(model.recipe.overlays.isEmpty)
        model.undo(); XCTAssertEqual(model.recipe, beforeDelete, "Deleted-target setter must not add an Undo entry")
        // A later import is also a new lifetime, without modifying saved UUIDs.
        library.bytes = try XCTUnwrap(originals[sourceID])
        await model.importPhotos(["new-source"], library: library)
        XCTAssertNotEqual(model.editEpoch, liveEpoch)
        let imported = model.recipe
        liveText("Old session"); model.removeSource(sourceID, epoch: liveEpoch)
        XCTAssertEqual(model.recipe, imported); XCTAssertFalse(model.canUndo)
    }
    @MainActor func testTwoThreeFourPhotoEditsKeepCropOrderLayersUndoAndReopen() async throws {
        let suite = "Celluloid.TV.Collage." + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite)); defer { defaults.removePersistentDomain(forName: suite) }
        var photos: [String: Data] = [:]
        for index in 0..<4 {
            let bitmap = try RasterCodec.bitmap(width: 96, height: 64)
            for x in 0..<96 {
                let value = CGFloat(x) / 95
                bitmap.setFillColor(CGColor(srgbRed: index % 2 == 0 ? value : 1-value, green: CGFloat(index)/4, blue: 0.2+value/2, alpha: 1))
                bitmap.fill(CGRect(x: x,y: 0,width: 1,height: 64))
            }
            photos["synthetic-source-\(index)"] = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()),as:.png)
        }
        for count in 2...4 {
            let library = CollagePhotoSource(photos: photos), model = TVEditorModel(defaults: defaults)
            let ids = (0..<count).map { "synthetic-source-\($0)" }
            await model.importPhotos(ids,library:library)
            XCTAssertNil(model.error); XCTAssertEqual(model.recipe.sources.count,count)
            let originalIDs = model.recipe.sources.map(\.id)
            model.change { recipe in
                for index in recipe.sources.indices { recipe.sources[index].crop.centerX = 0.2+Double(index)/10; recipe.sources[index].crop.centerY = 0.7; recipe.sources[index].crop.zoom = 2.5 }
                recipe.sources.swapAt(0,count-1)
            }
            let cropped = model.recipe.sources
            for template in try NativeResources.templates(count:count) {
                model.change { $0.collageTemplate = template.assetName }
                XCTAssertEqual(model.recipe.sources,cropped,"Changing template must preserve each source crop and order")
            }
            model.add(Overlay(sticker:try XCTUnwrap(StickerAsset.all.first)))
            model.add(Overlay(bubble:.say1,text:"TV 世界"))
            let beforeTransform = model.recipe
            model.editLayer { $0.rotation = 30; $0.mirrored = true; $0.centerX = 0.6; $0.fontSize = 0.035 }
            XCTAssertNotEqual(model.recipe,beforeTransform)
            model.undo(); XCTAssertEqual(model.recipe,beforeTransform)
            model.editLayer { $0.rotation = 15; $0.mirrored = true }
            let complete = model.recipe
            model.keepRecipe(); XCTAssertNil(model.error)
            let stored = try XCTUnwrap(defaults.data(forKey:TVEditorModel.savedKey))
            XCTAssertLessThanOrEqual(stored.count,TVSavedRecipe.maximumBytes)
            let record = try TVSavedRecipe.decode(stored)
            XCTAssertEqual(record.recipe,complete)
            XCTAssertEqual(record.photoIDs[originalIDs[0]],ids[0])
            let reopened = TVEditorModel(defaults:defaults)
            await reopened.reopen(library:library)
            XCTAssertNil(reopened.error); XCTAssertEqual(reopened.recipe,complete); XCTAssertEqual(reopened.originals,model.originals)
            await reopened.saveToPhotos(library:library)
            XCTAssertNil(reopened.error)
            let output = try XCTUnwrap(library.saved.last), metadata = try RasterCodec.metadata(output)
            XCTAssertEqual(metadata.pixelWidth,800); XCTAssertEqual(metadata.pixelHeight,800)
            let removed = reopened.recipe.sources[0].id
            var removal = reopened.recipe; removal.sources.removeFirst(); try TVEditorModel.configureCanvas(&removal)
            reopened.change { $0 = removal }
            XCTAssertFalse(reopened.recipe.sources.contains { $0.id == removed })
            reopened.undo(); XCTAssertEqual(reopened.recipe,complete)
            print("TV_NATIVE_MODEL_COLLAGE sources=\(count) allTemplates/crop/order/layers/multilingualText/undo/recipeReopen/export verified; injected data source, not Photos focus E2E")
        }
    }
    @MainActor private final class CollagePhotoSource: TVPhotoDataSource {
        let photos: [String: Data]
        var saved: [Data] = []
        init(photos: [String:Data]) { self.photos = photos }
        func currentImageData(_ id:String,limit:Int) async throws -> Data {
            guard let bytes = photos[id] else { throw TVPhotoError.missing }
            guard bytes.count <= limit else { throw RecipeError.resourceLimit }; return bytes
        }
        func saveVerifiedPNG(_ bytes:Data) async throws -> String {
            _ = try RasterCodec.metadata(bytes); saved.append(bytes); return "synthetic-saved-output"
        }
    }
    @MainActor private final class StubPhotoSource: TVPhotoDataSource {
        var bytes: Data
        init(bytes:Data) { self.bytes=bytes }
        func currentImageData(_ id:String,limit:Int) async throws -> Data { guard bytes.count<=limit else { throw RecipeError.resourceLimit };return bytes }
        func saveVerifiedPNG(_ bytes:Data) async throws -> String { throw TVPhotoError.unavailable }
    }
    func testResourceStreamRejectsOversizeAndCancelsRequest() async {
        let state = TVResourceRead(limit: 4)
        let cancelled = expectation(description: "PhotoKit request cancellation")
        state.setCancellation { cancelled.fulfill() }
        do {
            let _: Data = try await withCheckedThrowingContinuation { continuation in
                state.install(continuation); state.append(Data([1,2,3])); state.append(Data([4,5])); state.finish(nil)
            }
            XCTFail("Oversize stream must fail")
        } catch { }
        await fulfillment(of: [cancelled], timeout: 2)
        let pending = TVResourceRead(limit: 4)
        pending.cancel()
        do { let _: Data = try await withCheckedThrowingContinuation { pending.install($0) }; XCTFail("Canceled stream must fail") }
        catch is CancellationError { }
        catch { XCTFail("Expected cancellation") }
    }

}
