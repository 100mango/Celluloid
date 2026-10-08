#!/usr/bin/env python3
"""Create opaque, unmasked catalog renditions of the existing Apple-served artwork.
Requires Pillow for this optional maintenance command; not used by the app or CI build.
"""
from pathlib import Path
import json
from PIL import Image
root = Path(__file__).resolve().parents[1]
catalog = root / 'Celluloid/Assets.xcassets/AppIcon.appiconset'
source = Image.open(catalog / 'Icon-Marketing.png').convert('RGB')
assert source.size == (1024, 1024)
contents = json.loads((catalog / 'Contents.json').read_text())
for item in contents['images']:
    points = float(item['size'].split('x')[0])
    scale = float(item['scale'].replace('x', ''))
    pixels = round(points * scale)
    if 'filename' not in item:
        item['filename'] = f'Icon-{points:g}@{scale:g}x.png'
    destination = catalog / item['filename']
    if destination.name != 'Icon-Marketing.png':
        source.resize((pixels, pixels), Image.Resampling.LANCZOS).save(destination)
    output = Image.open(destination)
    assert output.mode == 'RGB' and output.size == (pixels, pixels)
(catalog / 'Contents.json').write_text(json.dumps(contents, indent=2) + '\n')
