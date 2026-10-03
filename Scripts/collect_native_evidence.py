#!/usr/bin/env python3
"""Export only bounded synthetic evidence: <=3.5 MB/job, <=17.5 MB/5-platform run, no xcresults."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,tempfile
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
TEMP=Path(os.environ['RUNNER_TEMP']).resolve()
OUT=TEMP/'celluloid-bounded-evidence'
MAX_FILE=5_000_000
MAX_TOTAL=3_500_000
PLATFORM=os.environ.get("CELLULOID_EVIDENCE_PLATFORM", "local")
if PLATFORM not in {"local", "mac", "tv", "watch", "phone", "vision"}:raise ValueError("Unknown evidence platform")
RESERVE=100_000
OUT.mkdir(exist_ok=True)
if any(OUT.iterdir()): raise RuntimeError('Evidence destination must be empty')
manifest={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
          'limits':{'per_file_bytes':MAX_FILE,'total_bytes':MAX_TOTAL,'retention_days':1},
          'platform':PLATFORM,'whole_run_limit_bytes':20_000_000,'files':[],'omissions':[],'scope':'Synthetic native test summaries, log tails and selected screenshots only; no xcresult bundles'}
size=0

def retain_bytes(name,data,source):
    global size
    name=Path(name).name
    if len(data)>MAX_FILE or size+len(data)>MAX_TOTAL-RESERVE:
        manifest['omissions'].append({'name':name,'reason':'evidence byte cap','bytes':len(data)})
        return False
    (OUT/name).write_bytes(data);size+=len(data)
    manifest['files'].append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source':source})
    return True

def retain_file(name,path,source):
    count=path.stat().st_size
    if count>MAX_FILE or size+count>MAX_TOTAL-RESERVE:
        manifest['omissions'].append({'name':name,'reason':'evidence byte cap','bytes':count});return False
    return retain_bytes(name,path.read_bytes(),source)

# Retain the small compatibility handoff before optional logs/screenshots consume space.
if PLATFORM=='mac' and (TEMP/'mac.log').is_file():
    from native_fixture_handoff import from_log
    try:
        retain_bytes('mac-filter-fixtures.json',from_log(TEMP/'mac.log',os.environ['GITHUB_SHA']),'newly authored synthetic archives from exact-head Mac tests')
    except (ValueError,KeyError) as error:
        manifest['omissions'].append({'name':'mac-filter-fixtures.json','reason':str(error)})

logs=['mac-release.log','tv-release.log','watch-release.log','vision-release.log','domain.log','rendering.log','mac.log','mac-ui.log','sandbox-build.log','sandbox-app-build.log','sandbox.log','mac-photos-build.log','vision-build.log','vision-runtime.log','vision-runtime-tests.log','tv-build.log','tv-runtime.log','tv-runtime-tests.log','tv-filter-oracle.log','tv-composition-oracle.log','watch-build.log','watch-runtime.log','watch-runtime-tests.log','phone-build.log','phone-runtime.log','phone-runtime-tests.log','phone-output-oracle.log','phone-release.log']
markers=re.compile(r'(Test Case .* (passed|failed)|Executed \d+ tests|error:|NATIVE_[A-Z_]+|VISION_NATIVE_|VISION_TEXT_|VISION_FILES_|VISION_EXPORT_|VISION_DOCUMENT_|TV_NATIVE_|TV_PHOTOS_|TV_FOCUS_|WATCH_NATIVE_|PHONE_COMPANION_|IMAGE_FORMAT_|LEGACY_FILTER_PIXELS|FACE_MASK_CONTROLLED|FACE_DETECTOR_ACTUAL|MAC_NEW_FILTER_UIKIT_ROUNDTRIP|MAC_FILTER_ONLY_FIXTURE|MAC_BAKED_BASE_|MAC_LEGACY_CANDIDATE)')
for name in logs:
    path=TEMP/name
    if not path.is_file():continue
    with path.open('rb') as handle:
        handle.seek(max(0,path.stat().st_size-200_000))
        retain_bytes(name+'.tail.txt',handle.read(200_000),name+' (last200000 bytes)')
    selected=deque(maxlen=1500)
    with path.open('rb') as handle:
        while part:=handle.readline(256_000):
            line=part.decode('utf8','replace')
            if markers.search(line):selected.append(line[:2000].rstrip())
    retain_bytes(name+'.summary.txt',('\n'.join(selected)+'\n').encode(),name+' (test/error markers)')
for name in ['native-icon-provenance-runtime.json','mac-release-packaging.json','tv-release-packaging.json','watch-release-packaging.json','vision-release-packaging.json','vision-runtime-evidence.json','tv-runtime-evidence.json','tv-text-input-probe.json','watch-runtime-evidence.json','phone-runtime-evidence.json','phone-harness-release.json','sandbox-entitlements.plist','sandbox-debug-entitlements.plist','sandbox-debug-actual.plist','sandbox-entitlements-after.plist']:
    path=TEMP/name
    if path.is_file():retain_file(name,path,name)

bundles=['CelluloidMac.xcresult','CelluloidMacUI.xcresult','CelluloidSandbox.xcresult','CelluloidVision.xcresult','CelluloidTV.xcresult','CelluloidWatch.xcresult','CelluloidPhoneCompanion.xcresult']
for name in bundles:
    bundle=TEMP/name
    if not bundle.is_dir():continue
    try:
        result=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',str(bundle)],capture_output=True,timeout=45)
        if result.returncode==0:retain_bytes(name+'.summary.json',result.stdout,name+' structured summary')
        else:manifest['omissions'].append({'name':name,'reason':'summary exporter exit'+str(result.returncode)})
    except subprocess.TimeoutExpired:manifest['omissions'].append({'name':name,'reason':'summary exporter timeout'})
    if name=='CelluloidMac.xcresult':continue
    with tempfile.TemporaryDirectory(prefix='celluloid-attachments-',dir=TEMP) as folder:
        folder=Path(folder)
        try:
            result=subprocess.run(['xcrun','xcresulttool','export','attachments','--path',str(bundle),'--output-path',str(folder)],capture_output=True,timeout=60)
        except subprocess.TimeoutExpired:
            manifest['omissions'].append({'name':name,'reason':'attachment exporter timeout'});continue
        if result.returncode or not (folder/'manifest.json').is_file():
            manifest['omissions'].append({'name':name,'reason':'attachment exporter unavailable'});continue
        records=json.loads((folder/'manifest.json').read_text())
        candidates=[]
        for record in records:
            for item in record.get('attachments',[]):
                path=(folder/item.get('exportedFileName','')).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file() or path.is_symlink():continue
                with path.open('rb') as handle:magic=handle.read(8)
                extension='.png' if magic.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if magic.startswith(b'\xff\xd8\xff') else None
                if extension is None:continue
                human=item.get('suggestedHumanReadableName','screenshot')
                priority=0 if 'failure' in human.lower() else 1 if human.startswith(('native-', 'vision-', 'tv-', 'watch-')) else 2 if item.get('isAssociatedWithFailure') else 3
                candidates.append((priority,human,path,extension))
        # Audit failures can attach the same full screen dozens of times. Keep
        # named workflow checkpoints first and deduplicate exact screenshot bytes,
        # preserving useful evidence within the unchanged outbound size limits.
        seen=set(); retained=0
        for _,human,path,extension in sorted(candidates,key=lambda x:(x[0],x[1])):
            if retained>=8:break
            if path.stat().st_size>MAX_FILE:
                manifest['omissions'].append({'name':human,'reason':'evidence byte cap','bytes':path.stat().st_size});continue
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:continue
            seen.add(digest)
            safe=re.sub(r'[^A-Za-z0-9_-]+','-',human)[:100]
            if retain_file(f'{name.removesuffix(".xcresult")}-{retained}-{safe}{extension}',path,name+' selected screenshot'):retained+=1

for name in [f'native-{platform}-launch.{extension}' for platform in ['vision','tv','watch','phone'] for extension in ['png','jpg']]:
    path=TEMP/name
    if path.is_file():retain_file(path.name,path,'simctl native launch screenshot')
manifest['retained_bytes_before_manifest']=size
payload=(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode()
if len(payload)>RESERVE:raise RuntimeError('Evidence manifest exceeded its reserved budget')
(OUT/'manifest.json').write_bytes(payload)
files=list(OUT.iterdir())
assert all(p.is_file() and not p.is_symlink() and p.stat().st_size<=MAX_FILE for p in files)
assert sum(p.stat().st_size for p in files)<=MAX_TOTAL
assert not any(p.suffix in ['.xcresult','.zip','.mp4'] for p in files)
print(json.dumps({'directory':str(OUT),'files':len(files),'bytes':sum(p.stat().st_size for p in files),'max_file_bytes':max(p.stat().st_size for p in files),'retention_days':1}))
