#!/usr/bin/env python3
"""Linux-safe structural validation only. This never substitutes for Xcode tests."""
from pathlib import Path
import hashlib,json,plistlib,subprocess,shutil,tempfile,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
resources=root/'Packages/CelluloidRendering/Sources/CelluloidRendering/Resources'
manifest=json.loads((resources/'resource-provenance.json').read_text())
assert len(manifest)==33
for entry in manifest:
    original=(root/entry['source']).read_bytes()
    copied=(resources/(entry['asset']+'.png')).read_bytes()
    assert original==copied and hashlib.sha256(original).hexdigest()==entry['sha256']
legacy=json.loads((resources/'legacy-bubble-resource-provenance.json').read_text())
assert {entry['asset'] for entry in legacy}=={name+'@2x' for name in ['aside1','call1','call2','call3','say1','say2','say3','think1','think2','think3']}
assert len(legacy)==10
for entry in legacy:
    original=(root/entry['source']).read_bytes()
    copied=(resources/(entry['asset']+'.png')).read_bytes()
    assert original==copied and hashlib.sha256(original).hexdigest()==entry['sha256']
assert (root/'LICENSE.txt').read_bytes()==(resources/'LICENSE.txt').read_bytes()
assert (root/'Celluloid/collage.json').read_bytes()==(resources/'collage.json').read_bytes()
assert (root/'CelluloidKit/bubble.json').read_bytes()==(resources/'bubble.json').read_bytes()
for path in [*(root/'Platforms').rglob('*.plist'), *(root/'Platforms').rglob('*.xcprivacy')]:
    plistlib.loads(path.read_bytes())
for path in (root/'CelluloidNative.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'):
    ET.parse(path)
generated=[root/'CelluloidNative.xcodeproj/project.pbxproj', *sorted((root/'CelluloidNative.xcodeproj/xcshareddata/xcschemes').glob('*')), *sorted((root/'Platforms').rglob('Info.plist'))]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in generated}
subprocess.run(['python3',str(root/'Scripts/generate_native_project.py')],check=True)
assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in generated}
# IDs must depend on repository-relative paths, not Linux/macOS checkout locations.
with tempfile.TemporaryDirectory(prefix='celluloid-project-') as temp:
    other=Path(temp); (other/'Scripts').mkdir()
    shutil.copyfile(root/'Scripts/generate_native_project.py',other/'Scripts/generate_native_project.py')
    shutil.copytree(root/'Platforms',other/'Platforms')
    subprocess.run(['python3',str(other/'Scripts/generate_native_project.py')],check=True)
    for path in generated:
        assert path.read_bytes()==(other/path.relative_to(root)).read_bytes(),path

assert not subprocess.check_output(['git','diff','--name-only','--','Celluloid','CelluloidKit','CelluloidPhotoExtension','Celluloid.xcodeproj','CelluloidTests','CelluloidUITests'],cwd=root).strip()
print(json.dumps({'status':'passed','checks':['33 canonical and 10 legacy2x artwork files byte-identical','25 original collage templates retained','original bubble text areas retained','license byte-identical','generated plists and schemes parse','project generator deterministic across checkout roots','existing iOS production and tests unchanged'],'swift_compilation':'not_run','apple_runtime':'not_run'},indent=2))
