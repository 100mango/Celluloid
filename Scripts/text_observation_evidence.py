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
