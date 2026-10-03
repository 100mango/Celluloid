#!/usr/bin/env python3
"""Export at most one named synthetic diagnostic JPEG after XCTest completes."""
import base64, hashlib, json, pathlib, sqlite3, subprocess
result = pathlib.Path('TestResults-permission-limited.xcresult')
if result.is_dir():
    destination = pathlib.Path('.build/permission-diagnostic')
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(result), '--output-path', str(destination)], check=True)
    manifest = json.loads((destination / 'manifest.json').read_text())
    def records(value):
        if isinstance(value, dict):
            if 'exportedFileName' in value: yield value
            for child in value.values(): yield from records(child)
        elif isinstance(value, list):
            for child in value: yield from records(child)
    matches = [r for r in records(manifest) if 'celluloid-limited-picker-diagnostic' in ' '.join(v for v in r.values() if isinstance(v, str))]
    if not matches:
        print(json.dumps(manifest)[:18000])
        raise SystemExit('Named failure screenshot not found in exported manifest')
    path = (destination / matches[0]['exportedFileName']).resolve()
    assert path.is_relative_to(destination.resolve())
    data = path.read_bytes()
    assert data.startswith(b'\xff\xd8') and len(data) <= 500_000
    print('SYSTEM_LIMITED_SCREENSHOT_BEGIN:actual-system')
    print('SYSTEM_LIMITED_SCREENSHOT_META', json.dumps({'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}))
    encoded = base64.b64encode(data).decode()
    for i in range(0, len(encoded), 4096): print('SYSTEM_LIMITED_SCREENSHOT_CHUNK:' + encoded[i:i + 4096])
    print('SYSTEM_LIMITED_SCREENSHOT_END:actual-system')
# This is an ephemeral synthetic simulator, queried read-only and scoped to this
# app's Photos row. Raw values are diagnostic evidence, not a public API contract.
marker = pathlib.Path('/tmp/current-celluloid-simulator')
if marker.exists():
    device = marker.read_text().strip()
    db = pathlib.Path.home() / 'Library/Developer/CoreSimulator/Devices' / device / 'data/Library/TCC/TCC.db'
    if db.is_file():
        connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
        columns = {r[1] for r in connection.execute('PRAGMA table_info(access)')}
        wanted = [c for c in ['service', 'client', 'auth_value', 'auth_reason'] if c in columns]
        if 'service' in columns and 'client' in columns:
            rows = list(connection.execute('SELECT ' + ','.join(wanted) + ' FROM access WHERE client=? AND service=?', ('Mango.Celluloid', 'kTCCServicePhotos')))
            print('SYSTEM_PHOTOS_TCC_RAW', json.dumps({'columns': wanted, 'rows': rows}))
        connection.close()
