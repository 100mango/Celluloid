#!/usr/bin/env python3
"""Log unsigned archive code-bundle metadata before any separate signing workflow."""
from pathlib import Path
import json, plistlib, subprocess, sys
archive = Path(sys.argv[1])
assert archive.is_dir(), f'Archive missing: {archive}'
records = []
for plist in sorted(archive.rglob('Info.plist')):
    bundle = plist.parent
    if bundle.suffix not in {'.app', '.appex', '.framework'}:
        continue
    info = plistlib.loads(plist.read_bytes())
    executable = bundle / info['CFBundleExecutable']
    assert executable.is_file(), f'Code bundle has no executable: {bundle}'
    records.append({
        'path': str(bundle.relative_to(archive)),
        'bundle_id': info.get('CFBundleIdentifier'),
        'short_version': info.get('CFBundleShortVersionString'),
        'build_version': info.get('CFBundleVersion'),
        'executable': info['CFBundleExecutable'],
        'architectures': subprocess.check_output(['xcrun', 'lipo', '-archs', str(executable)], text=True).strip().split(),
        'linked_libraries': subprocess.check_output(['xcrun', 'otool', '-L', str(executable)], text=True).splitlines()[1:]
    })
assert any(item['bundle_id'] == 'Mango.Celluloid' for item in records)
assert any(item['bundle_id'] == 'Mango.Celluloid.CelluloidPhotoExtension' for item in records)
assert any(item['bundle_id'] == 'Mango.CelluloidKit' for item in records)
print('ARCHIVE_INVENTORY_BEGIN')
print(json.dumps(records, indent=2))
print('ARCHIVE_INVENTORY_END')
