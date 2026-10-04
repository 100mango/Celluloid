#!/usr/bin/env python3
"""Export bounded synthetic evidence under the fixed eleven-job 20 MB allocation; no xcresults."""
from pathlib import Path
import base64,hashlib,json,os,re,shutil,subprocess,tempfile
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
TEMP=Path(os.environ['RUNNER_TEMP']).resolve()
OUT=TEMP/'celluloid-bounded-evidence'
from combined_evidence_budget import BUDGETS,WHOLE_RUN,MAX_FILE
PLATFORM=os.environ.get("CELLULOID_EVIDENCE_PLATFORM", "local")
if PLATFORM not in {"local", *BUDGETS}:raise ValueError("Unknown evidence platform")
MAX_TOTAL=BUDGETS.get(PLATFORM,3_500_000)
RESERVE=100_000
OUT.mkdir(exist_ok=True)
if any(OUT.iterdir()): raise RuntimeError('Evidence destination must be empty')
manifest={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
          'limits':{'per_file_bytes':MAX_FILE,'total_bytes':MAX_TOTAL,'retention_days':1},
          'platform':PLATFORM,'whole_run_limit_bytes':WHOLE_RUN,'whole_run_allocation':BUDGETS,'files':[],'omissions':[],'scope':'Synthetic native test summaries, log tails and selected screenshots only; no xcresult bundles'}
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

# Required source/package/consumer receipts precede optional logs and screenshots.
# A missing receipt stays an explicit omission; its producing verification step is red.
required=['combined-source-before.json','combined-source-after.json']
if PLATFORM=='preflight':required+=['combined-preflight.json','preflight-phone-embedded-watch.json','preflight-phone-embedded-watch-release.json']
if PLATFORM=='mac':required+=['mac-required-tests.json','sandbox-extension-entitlements-before.plist','sandbox-extension-entitlements.plist']
if PLATFORM=='phone':required+=['phone-embedded-watch.json','phone-embedded-watch-release.json','phone-required-tests.json']
if PLATFORM in {'compact-phone','large-phone','small-ipad','large-ipad'}:required+=['uikit-layer-staging.json','uikit-required-tests.json']
if PLATFORM=='archive':required+=['archive-embedded-watch.json']
for name in required:
    path=TEMP/name
    if path.is_file():
        if not retain_file(name,path,'required combined source/package/consumer receipt'):raise RuntimeError('Required receipt exceeded bounded allocation: '+name)
    else:manifest['omissions'].append({'name':name,'reason':'required producer did not emit receipt; its verification step must pass separately'})
if PLATFORM=='preflight':
    diagnostics=[]
    for path in sorted(TEMP.glob('preflight-*.log'))[:24]:
        issues=[];tail=deque(maxlen=4)
        with path.open('r',encoding='utf8',errors='replace') as stream:
            for line in stream:
                tail.append(line[:800].rstrip())
                if re.search(r'error:|fatal error|strip .*-(?:D|S)|BUILD (?:FAILED|SUCCEEDED)',line):
                    if len(issues)<8:issues.append(line[:1200].rstrip())
        diagnostics.append({'log':path.name,'issues':issues,'tail':list(tail)})
    if not retain_bytes('preflight-diagnostics.json',(json.dumps(diagnostics,indent=2)+'\n').encode(),'bounded all-stage compiler/copy-operation diagnostics'):raise RuntimeError('Prerequisite diagnostics exceeded reserved allocation')
# Preserve complete scoped evidence lines even when later logs exhaust optional space.
critical=[]
for path in [TEMP/'phone-runtime-tests.log',TEMP/'units.log']:
    if not path.is_file():continue
    with path.open('rb') as handle:
        for part in iter(lambda:handle.readline(256_000),b''):
            line=part.decode('utf8','replace').strip()
            if line.startswith(('MAC_LAYER_UIKIT_COMPOSITOR ', 'SHIPPING_COMPANION_')):
                if len(line)>4000 or len(critical)>=100:raise RuntimeError('Unexpected critical marker volume')
                critical.append({'log':path.name,'line':line})
if critical and not retain_bytes('shipping-consumer-markers.json',(json.dumps(critical,indent=2)+'\n').encode(),'exact required shipping/consumer log markers'):raise RuntimeError('Required markers exceeded bounded allocation')

# The original UIKit exporter already chooses at most two <=500 KB synthetic
# JPEGs. Decode only its complete SHA-bound envelope, before optional log tails.
screens=TEMP/'uikit-screens.log'
if screens.is_file():
    pending=None;retained=0
    with screens.open('r',encoding='utf8',errors='replace') as handle:
        for line in handle:
            line=line.strip()
            if line.startswith('SCREENSHOT_BEGIN:'):pending={'name':line.split(':',1)[1],'chunks':[],'bytes':0}
            elif pending is not None and line.startswith('SCREENSHOT_META '):pending['meta']=json.loads(line.split(' ',1)[1])
            elif pending is not None and line.startswith('SCREENSHOT_CHUNK:'):
                chunk=line.split(':',1)[1];pending['bytes']+=len(chunk)
                if pending['bytes']>700_000:raise RuntimeError('UIKit screenshot envelope exceeded bound')
                pending['chunks'].append(chunk)
            elif pending is not None and line=='SCREENSHOT_END:'+pending['name']:
                data=base64.b64decode(''.join(pending['chunks']),validate=True);meta=pending['meta']
                if not data.startswith(b'\xff\xd8') or len(data)>500_000 or len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=meta['sha256'] or retained>=2:raise RuntimeError('Invalid bounded UIKit screenshot receipt')
                retain_bytes('uikit-selected-'+str(retained)+'.jpg',data,'original UIKit exporter: '+meta['result'])
                retained+=1;pending=None
    if pending is not None:manifest['omissions'].append({'name':'uikit-screenshot','reason':'incomplete original exporter envelope'})

# Retain the small compatibility handoff before optional logs/screenshots consume space.
if PLATFORM=='mac' and (TEMP/'mac.log').is_file():
    from native_fixture_handoff import from_log
    try:
        retain_bytes('mac-filter-fixtures.json',from_log(TEMP/'mac.log',os.environ['GITHUB_SHA']),'newly authored synthetic archives from exact-head Mac tests')
    except (ValueError,KeyError) as error:
        manifest['omissions'].append({'name':'mac-filter-fixtures.json','reason':str(error)})
    from native_fixture_handoff import layer_from_log,LAYER_FILE
    try:
        retain_bytes(LAYER_FILE,layer_from_log(TEMP/'mac.log',os.environ['GITHUB_SHA']),'manufactured legacy layer archive and independently consumed synthetic source/rendered PNG; exact-head Mac tests')
    except (ValueError,KeyError) as error:
        manifest['omissions'].append({'name':LAYER_FILE,'reason':str(error)})

logs=['mac-release.log','tv-release.log','watch-release.log','vision-release.log','domain.log','rendering.log','mac.log','mac-ui.log','sandbox-build.log','sandbox-app-build.log','sandbox.log','mac-photos-build.log','vision-build.log','vision-runtime.log','vision-runtime-tests.log','tv-build.log','tv-runtime.log','tv-runtime-tests.log','tv-filter-oracle.log','tv-composition-oracle.log','watch-build.log','watch-runtime.log','watch-runtime-tests.log','phone-build.log','phone-runtime.log','phone-runtime-tests.log','phone-output-oracle.log','phone-release.log']
markers=re.compile(r'(Test Case .* (passed|failed)|Executed \d+ tests|error:|NATIVE_[A-Z_]+|VISION_NATIVE_|VISION_TEXT_|VISION_FILES_|VISION_EXPORT_|VISION_DOCUMENT_|TV_NATIVE_|TV_PHOTOS_|TV_FOCUS_|WATCH_NATIVE_|WATCH_ENDPOINT_|PHONE_COMPANION_|IMAGE_FORMAT_|LEGACY_FILTER_PIXELS|FACE_MASK_CONTROLLED|FACE_DETECTOR_ACTUAL|MAC_LAYER_UIKIT_COMPOSITOR|SHIPPING_COMPANION_[A-Z_]+|REQUIRED_INTEROPERABILITY|COMBINED_SOURCE|MAC_NEW_FILTER_UIKIT_ROUNDTRIP|MAC_FILTER_ONLY_FIXTURE|MAC_BAKED_BASE_|MAC_LEGACY_CANDIDATE)')
logs += ['uikit-screens.log','uikit-diagnostics.log','archive-inventory.log']
if PLATFORM in {'compact-phone','large-phone','small-ipad','large-ipad'}:
    logs += [p.name for p in sorted(TEMP.glob('bootstrap-*.log'))][:8]
logs += [f'watch-{profile}-runtime-tests.log' for profile in ['small','large']]
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
if PLATFORM in {'compact-phone','large-phone','small-ipad','large-ipad','archive'}:
    for name in ['release-build.log','build.log','units.log','preflight.log','ui.log','dark.log','preservation.log','archive.log']:
        path=TEMP/name
        if not path.is_file():continue
        with path.open('rb') as handle:
            handle.seek(max(0,path.stat().st_size-80_000))
            retain_bytes('uikit-'+name+'.tail.txt',handle.read(80_000),name+' (last80000 bytes)')
        selected=deque(maxlen=600)
        with path.open('rb') as handle:
            for part in iter(lambda:handle.readline(256_000),b''):
                line=part.decode('utf8','replace')
                if markers.search(line):selected.append(line[:2000].rstrip())
        retain_bytes('uikit-'+name+'.summary.txt',('\n'.join(selected)+'\n').encode(),name+' (test/error markers)')
for name in [name+'.timing.json' for name in logs]:
    path=TEMP/name
    if path.is_file():retain_file(name,path,'bounded process/startup/suite/teardown timing')
for name in ['native-icon-provenance-runtime.json','mac-release-packaging.json','tv-release-packaging.json','watch-release-packaging.json','vision-release-packaging.json','vision-runtime-evidence.json','tv-runtime-evidence.json','tv-text-input-probe.json','watch-runtime-evidence.json','watch-small-runtime-evidence.json','watch-large-runtime-evidence.json','phone-runtime-evidence.json','phone-harness-release.json','sandbox-entitlements.plist','sandbox-debug-entitlements.plist','sandbox-debug-actual.plist','sandbox-entitlements-after.plist','sandbox-extension-entitlements.plist']:
    path=TEMP/name
    if path.is_file() and not (OUT/name).exists():retain_file(name,path,name)

bundles=['CelluloidMac.xcresult','CelluloidMacUI.xcresult','CelluloidSandbox.xcresult','CelluloidVision.xcresult','CelluloidTV.xcresult','CelluloidWatch.xcresult','CelluloidWatchSmall.xcresult','CelluloidWatchLarge.xcresult','CelluloidPhoneCompanion.xcresult']
if PLATFORM in {'compact-phone','large-phone','small-ipad','large-ipad'}:
    bundles += [p.name for p in sorted(ROOT.glob('TestResults*.xcresult'))]
for name in bundles:
    bundle=(ROOT if name.startswith('TestResults') else TEMP)/name
    if not bundle.is_dir():continue
    try:
        result=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',str(bundle)],capture_output=True,timeout=45)
        if result.returncode==0:retain_bytes(name+'.summary.json',result.stdout,name+' structured summary')
        else:manifest['omissions'].append({'name':name,'reason':'summary exporter exit'+str(result.returncode)})
    except subprocess.TimeoutExpired:manifest['omissions'].append({'name':name,'reason':'summary exporter timeout'})
    if name=='CelluloidMac.xcresult' or name.startswith('TestResults'):continue
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

for name in [f'native-{platform}-launch.{extension}' for platform in ['vision','tv','watch','phone'] for extension in ['png','jpg']] + [f'watch{suffix}-launch.jpg' for suffix in ['', '-small', '-large']]:
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
