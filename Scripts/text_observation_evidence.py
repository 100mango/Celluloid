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
    keys={'schema','acceptance','text','sourcePNG_SHA256','actualCompositePNG_SHA256','actualTextRect','frameAllocationHeight','naturalBlockHeight','fontSize','lineHeight','backingScale','coreTextLines','oracleLines','images','isolatedMetrics','rasterExperiments','scope'}
    check(type(row) is dict and set(row)==keys and row['schema']=='Celluloid.NativeGlyphObservation.3' and row['acceptance'] is False,'Unknown/accepted glyph observation')
    check(row['text']=='Hello, 世界 🎬' and row['sourcePNG_SHA256']==contract['sourcePNG_SHA256'] and row['actualCompositePNG_SHA256']==contract['actualPNG_SHA256'],'Glyph/composite image binding changed')
    check(contract['schema']=='Celluloid.NativeTextContract.1' and contract['case']=='manufactured-affine','Wrong native diagnostic contract')
    for key in ['sourcePNG_SHA256','actualCompositePNG_SHA256']:check(re.fullmatch('[0-9a-f]{64}',row[key]) is not None,'Invalid glyph image digest')
    check(type(row['images']) is list and [r.get('role') for r in row['images']]==['replayed-production-backing','exact-appkit-oracle-backing'],'Wrong/missing isolated backings')
    check(all(type(r.get('width')) is int and type(r.get('height')) is int and (r['width'],r['height'])==(56,88) for r in row['images']),'Wrong isolated backing dimensions')
    check(type(row['coreTextLines']) is list and len(row['coreTextLines'])==3 and type(row['oracleLines']) is list and len(row['oracleLines'])==3,'Missing line/glyph observations')
    check([r.get('text') for r in row['oracleLines']]==['Hello,',' 世界 ','🎬'],'Wrong independent oracle line strings')
    metrics=row['isolatedMetrics'];check(type(metrics) is dict and set(metrics)=={'premultipliedRGBMaximum','alphaMaximum','premultipliedRGBPixelsAbove2','alphaPixelsAbove2'},'Malformed isolated metrics')
    for key,value in metrics.items():check(type(value) is int and 0<=value<=(255 if key.endswith('Maximum') else 56*88),'Invalid isolated metric')
    experiments=row['rasterExperiments']
    expected=[('frame-default','CTFrameDraw',{}),('frame-position-on','CTFrameDraw',{'positioning':True}),
        ('frame-position-off','CTFrameDraw',{'positioning':False}),
        ('frame-position-on-quant-off','CTFrameDraw',{'positioning':True,'quantization':False}),
        ('frame-position-on-quant-on','CTFrameDraw',{'positioning':True,'quantization':True}),
        ('frame-smoothing-off','CTFrameDraw',{'smoothing':False}),
        ('line-default','CTLineDraw',{}),('run-default','CTRunDraw',{}),('glyph-default','CTFontDrawGlyphs',{}),
        ('glyph-absolute-origin','CTFontDrawGlyphs',{}),('glyph-appkit-transform','CTFontDrawGlyphs',{})]
    check(type(experiments) is list and len(experiments)==len(expected),'Missing/duplicate raster experiment')
    fields={'name','api','explicitFlagOverrides','plannedCoordinateProof','initialCTM','initialTextMatrix','initialTextPosition',
        'finalCTM','finalTextMatrix','finalTextPosition','interpolationQuality','premultipliedRGBA_SHA256',
        'againstProductionReplay','againstExactOracle','width','height','pngSHA256','pngBase64'}
    for experiment,(name,api,flags) in zip(experiments,expected):
        check(type(experiment) is dict and set(experiment)==fields,'Unknown raster experiment fields')
        check((experiment['name'],experiment['api'])==(name,api),'Wrong/out-of-order raster experiment')
        check(experiment['explicitFlagOverrides']==flags and all(type(v) is bool for v in experiment['explicitFlagOverrides'].values()),'Wrong raster flag overrides')
        for key,size in [('initialCTM',6),('initialTextMatrix',6),('initialTextPosition',2),('finalCTM',6),('finalTextMatrix',6),('finalTextPosition',2)]:
            check(type(experiment[key]) is list and len(experiment[key])==size and all(type(v) in (int,float) and math.isfinite(v) for v in experiment[key]),'Malformed raster transform')
        wanted_ctm=[2,0,0,2,0,0] if name=='glyph-absolute-origin' else [2,0,0,-2,0,88] if name=='glyph-appkit-transform' else experiments[0]['initialCTM']
        check(experiment['initialCTM']==wanted_ctm and experiment['initialTextMatrix']==[1,0,0,1,0,0] and experiment['initialTextPosition']==[0,0],'Changed raster experiment geometry')
        proof=experiment['plannedCoordinateProof']
        if name in {'glyph-absolute-origin','glyph-appkit-transform'}:
            check(type(proof) is dict and set(proof)=={'glyphCount','maximumDeviceOriginDelta','maximumGlyphLinearDelta','drawInputs'},'Missing planned transform coordinate proof')
            source_runs=[(i,j,line,run) for i,line in enumerate(row['coreTextLines']) for j,run in enumerate(line['runs'])]
            glyph_count=sum(len(run['glyphs']) for _,_,_,run in source_runs)
            check(type(proof['glyphCount']) is int and 0<proof['glyphCount']==glyph_count,'Wrong coordinate proof glyph count')
            check(type(proof['drawInputs']) is list and len(proof['drawInputs'])==len(source_runs),'Missing exact draw inputs')
            def vector(value,n):return type(value) is list and len(value)==n and all(type(v) in (int,float) and math.isfinite(v) for v in value)
            def point(m,p):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
            def linear(c,t):return [c[0]*t[0]+c[2]*t[1],c[1]*t[0]+c[3]*t[1],c[0]*t[2]+c[2]*t[3],c[1]*t[2]+c[3]*t[3]]
            origin_delta=0;linear_delta=0;reference=experiments[0]['initialCTM']
            for draw,(i,j,line,run) in zip(proof['drawInputs'],source_runs):
                check(type(draw) is dict and set(draw)=={'lineIndex','runIndex','font','size','fontMatrix','inputCTM','glyphs','positions'},'Unknown/missing glyph draw input')
                check(type(draw['lineIndex']) is int and type(draw['runIndex']) is int and (draw['lineIndex'],draw['runIndex'])==(i,j),'Changed glyph input order')
                check(draw['font']==run['font'] and type(draw['font']) is str and type(draw['size']) in (int,float) and 0<draw['size']==run['size'],'Changed draw font/size')
                check(draw['glyphs']==run['glyphs'] and all(type(g) is int and 0<=g<=65535 for g in draw['glyphs']),'Changed shaped glyph stream')
                check(vector(draw['inputCTM'],6) and draw['inputCTM']==wanted_ctm and vector(draw['fontMatrix'],6) and vector(run['fontMatrix'],6),'Malformed input font/CTM matrix')
                check(draw['fontMatrix'][4:]==run['fontMatrix'][4:]==[0,0],'Unexpected font matrix translation')
                check(type(draw['positions']) is list and len(draw['positions'])==len(draw['glyphs'])==len(run['positionsFromCTRunGetPositions']),'Changed input position count')
                check(vector(line['frameLineOrigin'],2),'Malformed frame line origin')
                for actual_pos,relative in zip(draw['positions'],run['positionsFromCTRunGetPositions']):
                    check(vector(actual_pos,2) and vector(relative,2),'Malformed supplied glyph position')
                    original=[x+y for x,y in zip(line['frameLineOrigin'],relative)]
                    expected=point(reference,original);actual=point(draw['inputCTM'],actual_pos)
                    check(all(math.isfinite(v) for v in expected+actual),'Overflow in planned origin mapping')
                    origin_delta=max(origin_delta,*[abs(a-b) for a,b in zip(expected,actual)])
                expected=linear(reference,run['fontMatrix']);actual=linear(draw['inputCTM'],draw['fontMatrix'])
                check(all(math.isfinite(v) for v in expected+actual),'Overflow in planned glyph mapping')
                linear_delta=max(linear_delta,*[abs(a-b) for a,b in zip(expected,actual)])
            for key in ['maximumDeviceOriginDelta','maximumGlyphLinearDelta']:
                check(type(proof[key]) in (int,float) and math.isfinite(proof[key]) and 0<=proof[key]<=1e-9,'Planned device geometry changed')
            check(origin_delta<=1e-9 and linear_delta<=1e-9,'Recomputed input geometry changed')
        else:check(proof is None,'Unexpected coordinate proof')
        # Final context matrices/positions are bounded observations only. No
        # claim about undocumented post-call state can discard diagnostic pixels.
        check(type(experiment['interpolationQuality']) is int and experiment['interpolationQuality']==experiments[0]['interpolationQuality'],'Changed raster interpolation')
        check(re.fullmatch('[0-9a-f]{64}',experiment['premultipliedRGBA_SHA256']) is not None,'Malformed raster digest')
        check(type(experiment['width']) is int and type(experiment['height']) is int and (experiment['width'],experiment['height'])==(56,88),'Changed raster experiment backing')
        check(len(base64.b64decode(experiment['pngBase64'],validate=True))<=6000,'Raster experiment PNG cap')
        for key in ['againstProductionReplay','againstExactOracle']:
            value=experiment[key];check(type(value) is dict and set(value)==set(metrics),'Malformed raster comparison')
            for metric,n in value.items():check(type(n) is int and 0<=n<=(255 if metric.endswith('Maximum') else 56*88),'Invalid raster comparison')
        if name=='frame-default':check(all(v==0 for v in experiment['againstProductionReplay'].values()),'Default frame replay differs from production helper')
    validate_pngs(row)
    report={'source_sha':source,'log_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'acceptance':False,
        'case_result':events[1][0],'observation':row,'scope':'Bounded public glyph/baseline diagnostics only; neither test success nor rendering qualification follows from this record.'}
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();check(len(raw)<=GLYPH_LIMIT,'Glyph evidence byte cap')
    return raw
