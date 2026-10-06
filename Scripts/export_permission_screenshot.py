#!/usr/bin/env python3
"""Export at most two synthetic XCTest JPEGs; failure evidence takes priority."""
import base64, hashlib, json, pathlib, sqlite3, subprocess
from original_ios_process_guard import active,StagedDiagnosticCommands
diagnostic=StagedDiagnosticCommands('evidence-screens') if active() else None


def records(value):
    if isinstance(value, dict):
        if 'exportedFileName' in value:
            yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


candidates = []
for result in sorted(pathlib.Path('.').glob('TestResults*.xcresult'), key=lambda p: p.stat().st_mtime, reverse=True):
    destination = pathlib.Path('.build/ui-evidence') / result.stem
    destination.mkdir(parents=True, exist_ok=True)
    command=['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(result), '--output-path', str(destination)]
    exported=diagnostic.run(command) if diagnostic is not None else subprocess.run(command,capture_output=True,text=True,timeout=45)
    print('UI_ATTACHMENT_EXPORT', result.name, exported.returncode, exported.stdout[-1000:], exported.stderr[-1000:], flush=True)
    manifest_path = destination / 'manifest.json'
    if exported.returncode or not manifest_path.is_file():
        continue
    for record in records(json.loads(manifest_path.read_text())):
        fields = ' '.join(v for v in record.values() if isinstance(v, str))
        failure = 'celluloid-failure-' in fields or 'celluloid-limited-picker-diagnostic' in fields
        if not failure and 'celluloid-evidence-' not in fields:
            continue
        path = (destination / record['exportedFileName']).resolve()
        assert path.is_relative_to(destination.resolve())
        data = path.read_bytes()
        assert data.startswith(b'\xff\xd8') and len(data) <= 500_000
        priority = 0 if 'celluloid-limited-picker-diagnostic' in fields else 1 if failure else 2
        candidates.append((priority, result.name, fields, data))
# No test-stream base64: export after all tests/teardown, bounded to two images
# across all devices/results. Never upload arbitrary screenshots or attachments.
for index, (priority, result, fields, data) in enumerate(sorted(candidates, key=lambda c: c[0])[:2]):
    name = ('failure' if priority < 2 else 'evidence') + '-' + str(index + 1)
    print('SCREENSHOT_BEGIN:' + name)
    print('SCREENSHOT_META', json.dumps({'name': fields, 'result': result, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}))
    encoded = base64.b64encode(data).decode()
    for offset in range(0, len(encoded), 4096):
        print('SCREENSHOT_CHUNK:' + encoded[offset:offset + 4096])
    print('SCREENSHOT_END:' + name, flush=True)
print('UI_ATTACHMENT_NAMED_COUNT', len(candidates), 'EMITTED', min(2, len(candidates)), flush=True)
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

if diagnostic is not None:diagnostic.finish()
