#!/usr/bin/env python3
"""Local source contracts only. These do not compile Swift or prove pixel/latency parity."""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / 'Scripts/fixtures/async-image-pipeline-baseline.json').read_text())

def read(path):
    return (ROOT / path).read_text()

def body(text, name):
    match = re.search(r'\bfunc\s+' + re.escape(name) + r'\s*\(', text)
    if not match:
        raise AssertionError('Missing Swift function: ' + name)
    start = text.index('{', match.end())
    depth, index = 1, start + 1
    while depth:
        depth += (text[index] == '{') - (text[index] == '}')
        index += 1
    return text[start:index]

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class AsyncImagePipelineContractTests(unittest.TestCase):
    def test_export_helper_bodies_are_exact_released_code(self):
        service = read('CelluloidKit/Controller/PhotoExportService.swift')
        for name, expected in BASELINE['export_method_body_sha256'].items():
            with self.subTest(name=name):
                self.assertEqual(digest(body(service, name)), expected)

    def test_shipped_filter_math_is_unchanged(self):
        source = read('CelluloidKit/Filter/Filter.swift')
        for name, expected in BASELINE['filter_method_body_sha256'].items():
            with self.subTest(name=name):
                self.assertEqual(digest(body(source, name)), expected)
        self.assertIn('simpleFilter("CIPhotoEffectInstant")', source)

    def test_adjustment_layers_and_native_renderer_are_unchanged(self):
        for path, expected in BASELINE['unchanged_file_sha256'].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)

    def test_worker_is_bounded_and_checks_cancellation_at_delivery(self):
        source = read('Packages/CelluloidCore/Sources/CelluloidDomain/LatestImageWork.swift')
        self.assertIn('private var pending: Job?', source)
        self.assertNotIn('[Job]', source)
        self.assertIn('latest?.cancel()', source)
        self.assertIn('imageWorkExecutor.async { self.drain() }', source)
        self.assertIn('dispatchPrecondition(condition: .notOnQueue(.main))', source)
        self.assertIn('completion(token.isCancelled ? .failure(CancellationError()) : result)', source)
        self.assertIn('withTaskCancellationHandler', source)
        self.assertNotIn('DispatchQueue.main.sync', source)

    def test_filtering_precedes_final_preview_resize(self):
        source = read('CelluloidKit/Filter/Filter.swift')
        self.assertLess(source.index('let graph = Filters.filter(request.filter)(input)'), source.index('graph.transformed(by: transform)'))
        self.assertLess(source.index('graph.transformed(by: transform)'), source.index('context.createCGImage(sampled'))
        base = read('CelluloidKit/Controller/BaseEditPhotoController.swift')
        preview = body(base, 'updatePreviewImage')
        self.assertNotIn('.filteredImage(', preview)
        self.assertNotIn('createCGImage', preview)
        self.assertIn('self.previewGeneration == generation', preview)
        self.assertIn('filterType != .Original, !isAdjustmentReadOnly', preview)

    def test_input_loader_preserves_originals_and_bounds_stream_and_thumbnail(self):
        source = read('Packages/CelluloidRendering/Sources/CelluloidRendering/RasterSourceLoader.swift')
        self.assertIn('originalBytes: bytes', source)
        self.assertIn('name: request.name, id: request.id', source)
        self.assertIn('RasterCodec.maxSourceBytes - count', source)
        self.assertIn('kCGImageSourceCreateThumbnailWithTransform: true', source)
        self.assertIn('kCGImageSourceShouldCacheImmediately: true', source)
        self.assertNotIn('RasterCodec.encode(', source)
        self.assertNotIn('Filters.filter(', source)

    def test_renderer_context_is_initialized_after_actor_hop(self):
        source = read('Packages/CelluloidRendering/Sources/CelluloidRendering/RenderQueue.swift')
        self.assertIn('private var storedRenderer: RecipeRenderer?', source)
        self.assertNotIn('private let renderer = RecipeRenderer()', source)

    def test_export_service_has_no_screen_and_no_photos_display_fallback(self):
        source = read('CelluloidKit/Controller/PhotoExportService.swift')
        self.assertIn('case .photosOriginal(let url, let orientation): return (url, orientation, nil)', source)
        self.assertIn('guard !isReadOnly else', source)
        self.assertNotIn('UIViewController', source)
        self.assertNotIn('preview.image', source)
        self.assertNotIn('displaySizeImage', source)
        self.assertIn('deinit { activeExport?.cancel() }', source)

    def test_ios_floor_is_not_raised_by_packages(self):
        for package in ['CelluloidCore', 'CelluloidRendering']:
            self.assertIn('.iOS(.v15)', read(f'Packages/{package}/Package.swift'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
