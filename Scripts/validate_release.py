#!/usr/bin/env python3
"""Validate release metadata and icon encoding without third-party packages."""
from pathlib import Path
import json, plistlib, struct, hashlib
root = Path(__file__).resolve().parents[1]
app = plistlib.loads((root / 'Celluloid/Info.plist').read_bytes())
extension = plistlib.loads((root / 'CelluloidPhotoExtension/Info.plist').read_bytes())
for key in ['CFBundleShortVersionString', 'CFBundleVersion']:
    assert app[key] == extension[key] and app[key], f'App/extension mismatch: {key}'
assert app['UIRequiredDeviceCapabilities'] == ['arm64']
assert app['UIApplicationSceneManifest']['UISceneConfigurations']['UIWindowSceneSessionRoleApplication']
assert app['NSPhotoLibraryUsageDescription'] and app['NSPhotoLibraryAddUsageDescription']
catalog = root / 'Celluloid/Assets.xcassets/AppIcon.appiconset'
entries = json.loads((catalog / 'Contents.json').read_text())['images']
assert any(item['idiom'] == 'ios-marketing' and item['size'] == '1024x1024' for item in entries)
for item in entries:
    path = catalog / item['filename']
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f'Not PNG: {path.name}'
    width, height, _, color_type = struct.unpack('>IIBB', data[16:26])
    pixels = round(float(item['size'].split('x')[0]) * float(item['scale'].rstrip('x')))
    assert (width, height) == (pixels, pixels), f'Wrong icon size: {path.name}'
    assert color_type == 2, f'Icon must be opaque RGB: {path.name}'
    offset = 8
    while offset < len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        assert data[offset + 4:offset + 8] != b'tRNS', f'Icon transparency: {path.name}'
        offset += length + 12
print(f'Validated Celluloid {app["CFBundleShortVersionString"]} build {app["CFBundleVersion"]}: scene lifecycle, Photos usage descriptions, and {len(entries)} opaque icon slots')

# Exact MIT notice from the pinned official SnapKit revision must ship with the shared framework.
notice = root / 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt'
assert hashlib.sha256(notice.read_bytes()).hexdigest() == '7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b'
assert 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt' in (root / 'Celluloid.xcodeproj/project.pbxproj').read_text()
print('Validated pinned SnapKit MIT notice source and project membership')
