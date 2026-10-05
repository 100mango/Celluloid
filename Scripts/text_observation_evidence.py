"""Retain bounded synthetic typography observations without granting acceptance."""
import base64,hashlib,json,math,re
from pathlib import Path
from native_fixture_handoff import layer_from_log

PREFIX='CELLULOID_TEXT_OBSERVATION '
LIMIT=200_000
EXPECTED={'mac.log':{('actual-native-coretext-backing',2,0),('independent-appkit-textkit',2,0),('independent-appkit-textkit',2,8),('independent-appkit-textkit',3,0),('independent-appkit-textkit',3,8)},
          'early-uikit-2x-interop.log':{('separate-uikit-label-diagnostic',2,0),('separate-uikit-label-diagnostic',2,8)},
          'early-uikit-3x-interop.log':{('separate-uikit-label-diagnostic',3,0),('separate-uikit-label-diagnostic',3,8)}}

def check(value,message):
    if not value:raise ValueError(message)

def unique(pairs):
    result={}
    for k,v in pairs:check(k not in result,'Duplicate text observation key');result[k]=v
    return result

def validate_pngs(value):
    if isinstance(value,dict):
        if 'pngBase64' in value:
            raw=base64.b64decode(value['pngBase64'],validate=True)
            check(24<=len(raw)<=30_000 and hashlib.sha256(raw).hexdigest()==value['pngSHA256'],'Diagnostic PNG bytes/hash')
            check(raw[:8]==b'\x89PNG\r\n\x1a\n' and raw[12:16]==b'IHDR','Diagnostic PNG format')
            width,height=int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big')
            check(type(value['width']) is int and type(value['height']) is int and (width,height)==(value['width'],value['height']),'Diagnostic PNG dimensions')
            check(0<width<=512 and 0<height<=512,'Diagnostic PNG bounds')
        for v in value.values():validate_pngs(v)
    elif isinstance(value,list):
        for v in value:validate_pngs(v)
    elif isinstance(value,float):check(math.isfinite(value),'Nonfinite text observation')

def collect(temp,source):
    temp=Path(temp);rows=[];seen={name:set() for name in EXPECTED};raw_hashes={}
    for name,expected in EXPECTED.items():
        path=temp/name
        if not path.is_file():continue
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            at_line_start=True
            for line in iter(lambda:stream.readline(100_001),b''):
                digest.update(line)
                observation=at_line_start and line.startswith(PREFIX.encode())
                at_line_start=line.endswith(b'\n')
                if not observation:continue
                check(len(line)<=100_000,'Oversized text observation')
                row=json.loads(line[len(PREFIX):],object_pairs_hook=unique)
                check(row['schema']=='Celluloid.TextObservation.1' and row['text']=='Hello, 世界 🎬','Non-synthetic/unknown text observation')
                check(all(k in row for k in ['pngBase64','pngSHA256','width','height']),'Missing diagnostic PNG')
                check(type(row['scale']) in (int,float) and type(row['padding']) in (int,float),'Scale/padding type')
                key=(row['kind'],row['scale'],row['padding']);check(key in expected and key not in seen[name],'Wrong/duplicate typography observation')
                seen[name].add(key);validate_pngs(row);rows.append({'log':name,'observation':row})
        raw_hashes[name]=digest.hexdigest()
    if not rows:return None
    check(isinstance(source,str) and re.fullmatch(r'[0-9a-f]{40}',source) is not None,'Missing/invalid text observation source SHA')
    fixture=json.loads(layer_from_log(temp/'mac.log',source))['fixture']
    check(all(r['observation']['archiveSHA256']==fixture['sha256'] for r in rows),'Typography/archive source binding')
    report={'source_sha':source,'archive_sha256':fixture['sha256'],'log_hashes':raw_hashes,'observations':rows,
        'complete_observation_set':all(seen[name]==expected for name,expected in EXPECTED.items()),
        'acceptance':False,'scope':'Synthetic public-API diagnostics. Separate UIKit label is not the shipping compositor temporary backing; no clipping, typography or interoperability acceptance.'}
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();check(len(raw)<=LIMIT,'Typography evidence cap')
    return raw

GLYPH_PREFIX='MAC_NATIVE_GLYPH_OBSERVATION '
GLYPH_LIMIT=160_000
GLYPH_CASE=('CelluloidMacPhotosExtensionTests.MacPhotoRendererTests','testProductionTextMatchesIndependentNativeControlAndRejectsPathMutations')

def collect_glyphs(temp,source):
    """Retain one exact-case diagnostic even when its <=2 assertion is red."""
    from mac_host_transport import load_json
    path=Path(temp)/'mac.log'
    if not path.is_file():return None
    check(not path.is_symlink() and path.stat().st_size<=20_000_000,'Invalid glyph diagnostic log')
    lines=path.read_text().splitlines();rows=[];contracts=[];events=[]
    case=re.compile(r"^Test Case '-\[([\w.]+) (test\w+)\]' (started|passed|failed|skipped)\b")
    for number,line in enumerate(lines):
        if match:=case.match(line):
            if match.groups()[:2]==GLYPH_CASE:events.append((match[3],number))
        if line.lstrip().startswith(GLYPH_PREFIX):
            check(line.startswith(GLYPH_PREFIX) and len(line.encode())<=100_000,'Malformed/oversized glyph observation')
            rows.append((number,load_json(line[len(GLYPH_PREFIX):])))
        if line.startswith('MAC_NATIVE_TEXT_CONTRACT '):
            check(len(line.encode())<=20_000,'Oversized native contract binding')
            contracts.append((number,load_json(line.split(' ',1)[1])))
    if not rows:return None
    check(isinstance(source,str) and re.fullmatch('[0-9a-f]{40}',source),'Missing glyph observation source')
    check(len(rows)==len(contracts)==1,'Duplicate/missing glyph/native observations')
    check(len(events)==2 and events[0][0]=='started' and events[1][0] in {'passed','failed'},'Missing/ambiguous glyph diagnostic testcase')
    check(all(events[0][1]<position<events[1][1] for position,_ in rows+contracts),'Glyph observation outside actual testcase')
    row=rows[0][1];contract=contracts[0][1]
    keys={'schema','acceptance','text','sourcePNG_SHA256','actualCompositePNG_SHA256','actualTextRect','frameAllocationHeight','naturalBlockHeight','fontSize','lineHeight','backingScale','coreTextLines','oracleLines','images','isolatedMetrics','scope'}
    check(type(row) is dict and set(row)==keys and row['schema']=='Celluloid.NativeGlyphObservation.1' and row['acceptance'] is False,'Unknown/accepted glyph observation')
    check(row['text']=='Hello, 世界 🎬' and row['sourcePNG_SHA256']==contract['sourcePNG_SHA256'] and row['actualCompositePNG_SHA256']==contract['actualPNG_SHA256'],'Glyph/composite image binding changed')
    check(contract['schema']=='Celluloid.NativeTextContract.1' and contract['case']=='manufactured-affine','Wrong native diagnostic contract')
    for key in ['sourcePNG_SHA256','actualCompositePNG_SHA256']:check(re.fullmatch('[0-9a-f]{64}',row[key]) is not None,'Invalid glyph image digest')
    check(type(row['images']) is list and [r.get('role') for r in row['images']]==['replayed-production-backing','exact-appkit-oracle-backing'],'Wrong/missing isolated backings')
    check(all(type(r.get('width')) is int and type(r.get('height')) is int and (r['width'],r['height'])==(56,88) for r in row['images']),'Wrong isolated backing dimensions')
    check(type(row['coreTextLines']) is list and len(row['coreTextLines'])==3 and type(row['oracleLines']) is list and len(row['oracleLines'])==3,'Missing line/glyph observations')
    check([r.get('text') for r in row['oracleLines']]==['Hello,',' 世界 ','🎬'],'Wrong independent oracle line strings')
    metrics=row['isolatedMetrics'];check(type(metrics) is dict and set(metrics)=={'premultipliedRGBMaximum','alphaMaximum','premultipliedRGBPixelsAbove2','alphaPixelsAbove2'},'Malformed isolated metrics')
    for key,value in metrics.items():check(type(value) is int and 0<=value<=(255 if key.endswith('Maximum') else 56*88),'Invalid isolated metric')
    validate_pngs(row)
    report={'source_sha':source,'log_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'acceptance':False,
        'case_result':events[1][0],'observation':row,'scope':'Bounded public glyph/baseline diagnostics only; neither test success nor rendering qualification follows from this record.'}
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();check(len(raw)<=GLYPH_LIMIT,'Glyph evidence byte cap')
    return raw
