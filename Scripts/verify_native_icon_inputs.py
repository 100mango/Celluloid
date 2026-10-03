#!/usr/bin/env python3
"""Verify the build-derived, ignored icon bytes still match the pinned derivation report."""
import hashlib,json,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report=json.loads((Path(os.environ['RUNNER_TEMP'])/'native-icon-provenance-runtime.json').read_text())
assert report['source_commit']==os.environ['GITHUB_SHA']
assert hashlib.sha256((root/report['source_path']).read_bytes()).hexdigest()==report['source_sha256']=='f4f7ca4326be0a7f017339545367ecfbe1fdae58da36cd3368305b056ce7c614'
expected=set()
for platform in ['watchOS','visionOS','tvOS']:
 for catalog in (root/'Platforms'/platform/'Assets.xcassets').rglob('Contents.json'):
  for row in json.loads(catalog.read_text()).get('images',[]):
   if 'filename' in row:expected.add((catalog.parent/row['filename']).relative_to(root).as_posix())
assert len(report['files'])==11 and {row['path'] for row in report['files']}==expected
for row in report['files']:
 file=(root/row['path']).resolve();assert file.is_relative_to(root) and not file.is_symlink()
 data=file.read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
 assert data[:8]==b'\x89PNG\r\n\x1a\n'
 assert int.from_bytes(data[16:20],'big')==row['width'] and int.from_bytes(data[20:24],'big')==row['height']
print('NATIVE_ICON_INPUTS_VERIFIED all11 generated files match exact-head derivation hashes and dimensions')
