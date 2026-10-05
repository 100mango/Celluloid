"""Versioned, immutable per-runtime controls; historical cross-runtime deltas remain diagnostics."""
from pathlib import Path
import base64, hashlib, json, re
ROOT=Path(__file__).resolve().parents[1]
CONTROL_PATH=ROOT/'Scripts/fixtures/platform-rendering-controls.json'
CONTROL_SHA='7b03cc5efba3a4bfdf40f1be5e33ff67d94eb6166d9659f2f8acc114540cb7b1'
CONTROL_SOURCE='52bf7a9c04e2d91880ca4e8fd3418cd94d32bb7e'
PREFIX='MAC_PLATFORM_RENDERING_CONTRACT '
RUNTIME_BUILD='24A434'
BANDS={'bubble-artwork':1990,'all-artwork':2053}

def require(value,message):
    if not value:raise ValueError(message)

def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate contract key: '+key);result[key]=value
    return result

def sha(data):return hashlib.sha256(data).hexdigest()

def control_bytes():
    require(CONTROL_PATH.is_file() and not CONTROL_PATH.is_symlink(),'Missing immutable controls')
    raw=CONTROL_PATH.read_bytes();require(len(raw)<=200_000 and sha(raw)==CONTROL_SHA,'Immutable control packet changed')
    data=json.loads(raw,object_pairs_hook=unique)
    require(data['schema']=='Celluloid.PlatformControls.1' and data['sourceSHA']==CONTROL_SOURCE,'Wrong control provenance')
    require(data['runtimeVersion']=='27.0' and data['runtimeBuild']==RUNTIME_BUILD and data['architecture']=='arm64','Wrong frozen runtime')
    require(set(data['profiles'])=={'2x','3x'} and set(data['common'])=={'filtered-base','sticker-artwork'},'Incomplete controls')
    for name,key in [('inputArchive','archiveSHA256'),('inputImage','sourcePNG_SHA256')]:
        blob=data[name];require(set(blob)=={'sha256','base64'},'Unknown fixed-input field')
        payload=base64.b64decode(blob['base64'],validate=True)
        require(sha(payload)==blob['sha256']==data[key] and 0<len(payload)<=50_000,'Fixed control input identity')
    blobs=list(data['common'].values())+[data['inputImage']]
    for profile,row in data['profiles'].items():
        require(type(row['scale']) is int and row['scale']==int(profile[0]),'Wrong frozen scale')
        require(set(row['images'])=={'full','bubble-artwork','all-artwork'},'Incomplete scale-specific controls')
        blobs+=list(row['images'].values())
    for row in blobs:
        require(set(row)=={'sha256','base64'},'Unknown control image field')
        image=base64.b64decode(row['base64'],validate=True)
        require(sha(image)==row['sha256'] and image[:8]==b'\x89PNG\r\n\x1a\n' and image[12:16]==b'IHDR','Control image bytes/hash')
        require((int.from_bytes(image[16:20],'big'),int.from_bytes(image[20:24],'big'))==(480,640),'Wrong control dimensions')
    return raw

def integer(value,maximum):return type(value) is int and 0<=value<=maximum

def validate_receipt(record,fixture,profile=None):
    controls=json.loads(control_bytes())
    keys={'schema','profile','runtimeVersion','scale','controlFileSHA256','controlSourceSHA','archiveSHA256','sourceSHA256','nativeSHA256','historicalFullMaximum','sameRuntimeMaximums','exactComponentMaximums','artworkMetrics','rejectedArtworkMutations'}
    require(isinstance(record,dict) and set(record)==keys,'Unknown/missing rendering contract fields')
    require(record['schema']=='Celluloid.PlatformRendering.1','Wrong rendering contract schema')
    require(record['profile'] in controls['profiles'] and (profile is None or record['profile']==profile),'Wrong rendering profile')
    require(type(record['scale']) in (int,float) and record['scale']==int(record['profile'][0]),'Actual display mismatch')
    require(record['runtimeVersion']=='27.0' and record['controlFileSHA256']==CONTROL_SHA and record['controlSourceSHA']==CONTROL_SOURCE,'Wrong runtime/control provenance')
    require(record['archiveSHA256']==fixture['sha256']==controls['archiveSHA256'],'Wrong semantic archive fixture')
    require(record['sourceSHA256']==fixture['sourceSHA256']==controls['sourcePNG_SHA256'],'Wrong original image fixture')
    require(record['nativeSHA256']==fixture['renderedSHA256'] and re.fullmatch('[0-9a-f]{64}',record['nativeSHA256']),'Wrong native output binding')
    require(integer(record['historicalFullMaximum'],255),'Invalid retained historical delta')
    current=record['sameRuntimeMaximums'];require(isinstance(current,dict) and set(current)=={'full','bubble-artwork','all-artwork'},'Missing same-runtime controls')
    require(all(integer(v,2) for v in current.values()),'Fresh UIKit differs from own immutable runtime control')
    exact=record['exactComponentMaximums'];require(isinstance(exact,dict) and set(exact)=={'filtered-base','sticker-artwork'},'Missing exact components')
    require(all(type(v) is int and v==0 for v in exact.values()),'Previously exact base/sticker pixels changed')
    artwork=record['artworkMetrics'];require(isinstance(artwork,dict) and set(artwork)==set(BANDS),'Missing artwork geometry proof')
    for name,metrics in artwork.items():
        require(isinstance(metrics,dict) and set(metrics)=={'outsideMaximum','edgeViolations','envelopeViolations','opacityViolations','controlBandPixels'},'Unknown artwork fields')
        require(all(type(v) is int for v in metrics.values()),'Noninteger artwork proof')
        require(metrics['controlBandPixels']==BANDS[name],'Edge mask no longer matches independent frozen controls')
        require(all(metrics[k]==0 for k in metrics if k!='controlBandPixels'),'Artwork placement/interior/edge failure')
    require(type(record['rejectedArtworkMutations']) is int and record['rejectedArtworkMutations']==6,'Artwork mutation oracle not exercised')
    return record

def require_case_enclosure(log,prefix,owner,method,modules):
    pattern=re.compile(r"^Test Case '-\[([\w.]+) "+re.escape(method)+r"\]' (started|passed|failed|skipped)\b.*$",re.M)
    events=[m for m in pattern.finditer(log) if m[1].rsplit('.',1)[-1]==owner]
    own_lines=[line for line in log.splitlines() if line.lstrip().lower().startswith('test case ') and owner in line and method in line]
    require(len(own_lines)==len(events) and all(line==line.strip() for line in own_lines),'Malformed/duplicate native or UIKit case records')
    for line in own_lines:
        require(re.fullmatch(r"Test Case '-\[[\w.]+ test\w+\]' (?:started\.|(?:passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)",line) is not None,'Malformed contract test execution')
    require(len(events)==2 and [m[2] for m in events]==['started','passed'],'Required contract testcase did not start and pass exactly once')
    require(all(m[1].rsplit('.',1)[0] in modules for m in events),'Contract belongs to wrong XCTest module')
    markers=list(re.finditer('^'+re.escape(prefix),log,re.M))
    require(len(markers)==1 and events[0].end()<markers[0].start()<events[1].start(),'Contract not emitted inside its actual required case')

def from_log(log,fixture,profile=None):
    lines=[line for line in log.splitlines() if line.lstrip().startswith(PREFIX.strip())]
    require(len(lines)==1 and lines[0].startswith(PREFIX),'Missing/duplicate/malformed platform contract')
    require(len(lines[0])<=20_000,'Oversized platform contract')
    require_case_enclosure(log,PREFIX,'MacPhotosManufacturedAdjustmentTests','testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor',{'CelluloidTests','CelluloidCompanionTests'})
    return validate_receipt(json.loads(lines[0][len(PREFIX):],object_pairs_hook=unique),fixture,profile)

NATIVE_PREFIX='MAC_NATIVE_TEXT_CONTRACT '
NATIVE_SPEC_PATH=ROOT/'Scripts/fixtures/native-text-expectations.json'
NATIVE_SPEC_SHA='f228faec71fa819ccec6c4f6fc5c2aea217cf219993145233869a4b004bad915'

def native_spec():
    require(NATIVE_SPEC_PATH.is_file() and not NATIVE_SPEC_PATH.is_symlink(),'Missing independent native expectations')
    raw=NATIVE_SPEC_PATH.read_bytes();require(sha(raw)==NATIVE_SPEC_SHA,'Independent native expectations changed')
    return json.loads(raw,object_pairs_hook=unique)

def finite_numbers(value):
    import math
    if isinstance(value,dict):return all(finite_numbers(x) for x in value.values())
    if isinstance(value,list):return all(finite_numbers(x) for x in value)
    if type(value) in (int,float):return math.isfinite(value)
    return isinstance(value,str)

def equal_fixed(actual,expected,tolerance=0):
    if isinstance(expected,dict):return isinstance(actual,dict) and set(actual)==set(expected) and all(equal_fixed(actual[k],v,tolerance) for k,v in expected.items())
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal_fixed(a,b,tolerance) for a,b in zip(actual,expected))
    if type(expected) in (int,float):return type(actual) in (int,float) and abs(actual-expected)<=tolerance
    return actual==expected

def validate_native(record,fixture):
    spec=native_spec();require(isinstance(record,dict) and set(record)==set(spec['keys']),'Unknown/missing native text fields')
    require(finite_numbers(record),'Nonfinite/boolean/native field type')
    require(record['schema']==spec['schema'],'Wrong native schema')
    for key,expected in spec['fixed'].items():
        require(equal_fixed(record[key],expected,1e-6 if key in {'baselines','destination','textRect'} else 0),'Native independent geometry/content differs: '+key)
    require(record['sourcePNG_SHA256']==fixture['sourceSHA256'] and record['actualPNG_SHA256']==fixture['renderedSHA256'],'Native text oracle not bound to actual manufactured output')
    for key in ['sourcePNG_SHA256','actualPNG_SHA256','actualRGBA_SHA256','controlRGBA_SHA256']:
        require(isinstance(record[key],str) and re.fullmatch('[0-9a-f]{64}',record[key]),'Invalid native digest')
    require(integer(record['maximumChannelDifference'],2) and type(record['differentPixels']) is int and record['differentPixels']==0,'Actual production text differs from independent native oracle')
    require(type(record['comparedBytes']) is int and record['comparedBytes']==1_228_800,'Wrong native compared-byte count')
    mutations=record['mutations'];require(isinstance(mutations,list) and [x.get('name') for x in mutations]==spec['mutation_names'],'Missing/unknown/duplicate native path mutation')
    for row in mutations:
        require(set(row)==set(spec['mutation_keys']),'Unknown/missing mutation metrics')
        require(type(row['hookCalls']) is int and row['hookCalls']==1,'Actual production path mutation was not exercised once')
        require(re.fullmatch('[0-9a-f]{64}',row['rgbaSHA256']) and row['rgbaSHA256'] not in {record['actualRGBA_SHA256'],record['controlRGBA_SHA256']},'Mutation did not produce distinct actual pixels')
        for key in ['maximumDifferenceFromControl','maximumDifferenceFromUnmutated']:
            require(integer(row[key],255) and row[key]>2,'Live mutation escaped the independent pixel oracle')
        for key in ['differentPixelsFromControl','differentPixelsFromUnmutated']:
            require(integer(row[key],307_200) and row[key]>0,'Mutation has no materially different output pixels')
    return record

def native_from_log(log,fixture):
    lines=[line for line in log.splitlines() if line.lstrip().startswith(NATIVE_PREFIX.strip())]
    require(len(lines)==1 and lines[0].startswith(NATIVE_PREFIX) and len(lines[0])<=20_000,'Missing/duplicate/malformed native text contract')
    owner,method=native_spec()['required_test'].split('.')
    require_case_enclosure(log,NATIVE_PREFIX,owner,method,{'CelluloidMacPhotosExtensionTests'})
    return validate_native(json.loads(lines[0][len(NATIVE_PREFIX):],object_pairs_hook=unique),fixture)
