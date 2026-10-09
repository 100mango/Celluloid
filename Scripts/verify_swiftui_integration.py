#!/usr/bin/env python3
"""Portable topology checks only. This is not Swift compilation or native UI proof."""
from pathlib import Path
import contextlib, io, json, plistlib, runpy

ROOT = Path(__file__).resolve().parents[1]
checked = []

def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checked.append(label)

def project(generator, project):
    generated = list((ROOT / project).rglob('*'))
    generated += list((ROOT / 'Platforms').glob('*/Info.plist')) if 'native' in generator else list((ROOT / 'Celluloid.xcworkspace').glob('contents.xcworkspacedata'))
    before = {p: p.read_bytes() for p in generated if p.is_file()}
    with contextlib.redirect_stdout(io.StringIO()):
        scope = runpy.run_path(str(ROOT / 'Scripts' / generator))
    check(all(p.read_bytes() == data for p, data in before.items()), generator + ' is reproducible')
    return scope['objects']

def target(objects, name):
    return next(v for v in objects.values() if v['isa'] == 'PBXNativeTarget' and v['name'] == name)

def sources(objects, name):
    value = target(objects, name)
    phase = next(objects[p] for p in value['buildPhases'] if objects[p]['isa'] == 'PBXSourcesBuildPhase')
    return [objects[objects[b]['fileRef']]['path'] for b in phase['files']]

def settings(objects, name):
    configs = objects[target(objects, name)['buildConfigurationList']]['buildConfigurations']
    return [(objects[c]['name'], objects[c]['buildSettings']) for c in configs]

def main():
    ios = project('generate_project.py', 'Celluloid.xcodeproj')
    native = project('generate_native_project.py', 'CelluloidNative.xcodeproj')
    required = {
        'Celluloid': ['Celluloid/SwiftUI/PhoneRootView.swift', 'Celluloid/SwiftUI/SystemPhotoPicker.swift', 'Celluloid/SwiftUI/PickerEntryDiagnostics.swift', 'Celluloid/SwiftUI/PhotoSelectionSession.swift', 'Celluloid/SwiftUI/CelluloidEditorView.swift', 'Celluloid/SwiftUI/CelluloidCollageEditorView.swift', 'Celluloid/SwiftUI/CelluloidSavedPhotoView.swift'],
        'CelluloidKit': ['CelluloidKit/SwiftUI/CelluloidEditingSession.swift', 'CelluloidKit/SwiftUI/CelluloidEditorContent.swift', 'CelluloidKit/SwiftUI/CelluloidEditorCanvas.swift', 'CelluloidKit/SwiftUI/CelluloidEditorSheets.swift'],
        'CelluloidTests': ['CelluloidTests/PhotoSelectionIdentityTests.swift', 'CelluloidTests/PhotoSelectionSessionTests.swift', 'CelluloidTests/SwiftUIEditorTestSupport.swift', 'CelluloidTests/PhoneEntryDesignTests.swift', 'CelluloidTests/SwiftUIOriginalDesignTests.swift', 'CelluloidPhotoExtension/PhotoEditingViewController.swift', 'CelluloidPhotoExtension/PhotosOutputWrite.swift'],
        'CelluloidUITests': ['CelluloidUITests/PhoneEntryDesignUITests.swift'],
        'CelluloidPhotoExtension': ['CelluloidPhotoExtension/PhotoEditingViewController.swift', 'CelluloidPhotoExtension/PhotosOutputWrite.swift'],
    }
    for name, expected in required.items():
        actual = sources(ios, name)
        check(len(actual) == len(set(actual)), name + ' has no duplicate source membership')
        for path in expected:
            check(path in actual and (ROOT / path).is_file(), name + ': ' + path)
    kit = target(ios, 'CelluloidKit')
    dependencies = [ios[p]['productName'] for p in kit['packageProductDependencies']]
    check(dependencies.count('CelluloidDomain') == 1, 'CelluloidKit links exactly one CelluloidDomain product')
    check(any(p.get('relativePath') == 'Packages/CelluloidCore' for p in ios.values()), 'Core package path is local')
    matrix = {}
    for objects, mapping in [(ios, {'Celluloid': ('IPHONEOS_DEPLOYMENT_TARGET', '15.0'), 'CelluloidKit': ('IPHONEOS_DEPLOYMENT_TARGET', '15.0'), 'CelluloidPhotoExtension': ('IPHONEOS_DEPLOYMENT_TARGET', '15.0'), 'CelluloidTests': ('IPHONEOS_DEPLOYMENT_TARGET', '17.0'), 'CelluloidUITests': ('IPHONEOS_DEPLOYMENT_TARGET', '17.0')}), (native, {'CelluloidMac': ('MACOSX_DEPLOYMENT_TARGET', '13.0'), 'CelluloidMacPhotosExtension': ('MACOSX_DEPLOYMENT_TARGET', '13.0'), 'CelluloidMacPhotosExtensionTests': ('MACOSX_DEPLOYMENT_TARGET', '13.0'), 'CelluloidMacTests': ('MACOSX_DEPLOYMENT_TARGET', '14.0'), 'CelluloidMacUITests': ('MACOSX_DEPLOYMENT_TARGET', '14.0'), 'CelluloidWatch': ('WATCHOS_DEPLOYMENT_TARGET', '9.0'), 'CelluloidTV': ('TVOS_DEPLOYMENT_TARGET', '17.0'), 'CelluloidVision': ('XROS_DEPLOYMENT_TARGET', '1.0'), 'CelluloidPhoneCompanion': ('IPHONEOS_DEPLOYMENT_TARGET', '15.0')})]:
        for name, (key, minimum) in mapping.items():
            matrix[name] = {config: values.get(key) for config, values in settings(objects, name)}
            check(all(value == minimum for value in matrix[name].values()), name + ' preserves minimum ' + minimum)
    for objects in [ios, native]:
        for value in objects.values():
            if value['isa'] == 'PBXFileReference' and value.get('sourceTree') == '<group>':
                check((ROOT / value['path']).exists(), 'Reference exists: ' + value['path'])
    info = plistlib.loads((ROOT / 'Platforms/macOS/Info.plist').read_bytes())
    check(info.get('LSApplicationCategoryType') == 'public.app-category.utilities', 'Mac Utilities category survives regeneration')
    print(json.dumps({'status': 'portable-topology-pass', 'checks': len(checked), 'deployment_minimums': matrix, 'native_compilation': 'not-run', 'native_tests': 'not-run'}, indent=2))

if __name__ == '__main__':
    main()
