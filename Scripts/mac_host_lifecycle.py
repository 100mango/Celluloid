"""Strict replay of the bounded, owned real Photos filter lifecycle receipt."""
import base64,hashlib,json,math,re
from pathlib import Path
from mac_host_self_identity import validate as self_identity,RECEIPT,IDENTIFIER
from mac_host_transport import HOST_CONTRACT
from mac_host_lifecycle_pixels import decode,compare,checked_icc,NAMES,PNG_LIMIT,ICC_LIMIT

SCHEMA='Celluloid.PhotosFilterLifecycle.1'
PHASES=('source-retained','fade-ready','saved-export','reopened-fade','cancelled-export','reverted-export','unmodified-original','reopened-original')
COLUMNS=['scope','role','identifier','title','label','value','count','enabled','hittable']
META={'bytes','sha256','rgba_sha256','format','width','height','bit_depth','color_type','interlace','orientation','profile','profile_encoding','alpha'}
FIELDS={'schema','host_entry_contract','source_sha','context_sha256','test_source_sha256','verifier_sha256','photos_pid','fixture_sha256','asset_label','single_photo_topologies','export_option_bindings','binary_states','binary_scalar_self_tested','complete','dirty_cancel_tested','deadline_seconds','control_columns','control_catalog','phases','images','raw_exports','srgb_icc_reference'}
SINGLE_PHOTO_TOPOLOGIES=('collection-present','collection-absent')
FILENAME='Celluloid-Owned-Host.png'

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def integer(v,low,high):return type(v) is int and low<=v<=high
def exact(row,keys,message):require(type(row) is dict and set(row)==set(keys),message)
def digest(v):return type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None

def validate_metadata(row,decoded):
    exact(row,META,'Unknown/missing lifecycle image metadata')
    require(integer(row['bytes'],1,PNG_LIMIT) and row['bytes']==decoded['bytes'] and row['sha256']==decoded['png_sha256'],'Lifecycle PNG byte/hash mismatch')
    require(row['rgba_sha256']==decoded['rgba_sha256'],'Lifecycle RGBA hash mismatch')
    for key,value in [('width',1200),('height',800),('bit_depth',8),('interlace',0),('orientation',1)]:
        require(type(row[key]) is int and row[key]==value,'Lifecycle image geometry/format mismatch')
    require(type(row['color_type']) is int and row['color_type']==decoded['color_type'],'Lifecycle PNG color type mismatch')
    require(row['format']=='public.png' and row['profile']=='sRGB' and row['alpha']=='opaque','Lifecycle format/profile/alpha mismatch')
    encoding='srgb-chunk' if decoded['profile']=='sRGB' else 'icc-reference'
    require(row['profile_encoding']==encoding,'Lifecycle profile encoding mismatch')

def validate(row,context,photos,ownership,baseline,images,context_hash):
    exact(row,FIELDS,'Unknown/missing lifecycle receipt field')
    require(row['schema']==SCHEMA and row['host_entry_contract']==HOST_CONTRACT,'Wrong lifecycle contract')
    for key,expected in [('source_sha',context['source_sha']),('context_sha256',context_hash),('test_source_sha256',context['test_source_sha256']),('verifier_sha256',context['script_sha256']),('fixture_sha256',ownership['fixture_sha256']),('asset_label',ownership['asset_label'])]:
        require(row[key]==expected,'Wrong lifecycle binding: '+key)
    require(type(row['photos_pid']) is int and row['photos_pid']==photos['pid']>0,'Wrong lifecycle Photos PID')
    require(row['complete'] is True and row['dirty_cancel_tested'] is False and type(row['deadline_seconds']) is int and row['deadline_seconds']==600,'Incomplete/overclaimed lifecycle')
    topologies=row['single_photo_topologies']
    require(type(topologies) is list and 1<=len(topologies)<=2 and
            all(type(value) is str and value in SINGLE_PHOTO_TOPOLOGIES for value in topologies) and
            len(set(topologies))==len(topologies),'Missing/duplicate/unknown single-photo topology')
    require(row['control_columns']==COLUMNS,'Wrong lifecycle control columns')
    phases=row['phases'];require(type(phases) is list and len(phases)==len(PHASES),'Missing/duplicate lifecycle phases')
    last=-1;details={}
    for index,(phase,name) in enumerate(zip(phases,PHASES)):
        exact(phase,{'index','name','elapsed_ms','controls','details'},'Malformed lifecycle phase')
        require(type(phase['index']) is int and phase['index']==index and phase['name']==name,'Out-of-order lifecycle phase')
        require(integer(phase['elapsed_ms'],0,599999) and phase['elapsed_ms']>=last,'Out-of-budget/nonmonotonic lifecycle phase')
        last=phase['elapsed_ms'];details[name]=phase['details']
    validate_controls(row['control_catalog'],phases)
    validate_export_bindings(row['export_option_bindings'],row['control_catalog'])
    require(row['binary_scalar_self_tested'] is True,'Foundation binary scalar self-test not completed')
    validate_binary_states(row['binary_states'],row['control_catalog'])
    source=details['source-retained'];exact(source,{'fixture_filename','fixture_sha256','retained_before_import'},'Malformed source retention')
    require(source=={'fixture_filename':FILENAME,'fixture_sha256':ownership['fixture_sha256'],'retained_before_import':True} and source['retained_before_import'] is True,'Original was not retained before import')
    fade=details['fade-ready'];exact(fade,{'filter','independent_filter','jpeg_quality','jpeg_sha256'},'Malformed independent reference')
    require(fade['filter']=='Fade' and fade['independent_filter']=='CIPhotoEffectInstant' and type(fade['jpeg_quality']) is float and fade['jpeg_quality']==0.95 and digest(fade['jpeg_sha256']),'Wrong independent filter/JPEG reference')
    generations={baseline['generation']}
    for name,wanted in [('reopened-fade','Fade'),('reopened-original','Original')]:
        d=details[name];exact(d,{'filter','editor_count_before','editor_count_after','identity_element_counts','observations'},'Malformed reopened editor')
        require(d['filter']==wanted and type(d['editor_count_before']) is int and d['editor_count_before']==0 and type(d['editor_count_after']) is int and d['editor_count_after']==1,'Wrong restored filter/editor transition')
        bound={'schema':RECEIPT,'host_entry_contract':HOST_CONTRACT,'source_sha':context['source_sha'],'photos_pid':photos['pid'],
            'fixture_sha256':ownership['fixture_sha256'],'asset_label':ownership['asset_label'],'identity_identifier':IDENTIFIER,
            'identity_element_counts':d['identity_element_counts'],'observations':d['observations']}
        actual=self_identity(bound,context,photos,ownership)
        require(actual['generation'] not in generations,'Stale editing generation across lifecycle reentry');generations.add(actual['generation'])
    exact(images,NAMES,'Missing/unexpected lifecycle image bytes');exact(row['images'],NAMES,'Missing/unexpected lifecycle image metadata')
    require(sum(len(data) for data in images.values())<=5*PNG_LIMIT,'Lifecycle image aggregate budget')
    profile=row['srgb_icc_reference'];icc=None
    if profile is not None:
        exact(profile,{'bytes','sha256'},'Malformed independent sRGB ICC reference')
        require(integer(profile['bytes'],128,ICC_LIMIT) and digest(profile['sha256']),'Invalid independent sRGB ICC reference')
        icc=profile
    decoded={name:decode(data,reference_icc=icc) for name,data in images.items()}
    require((icc is not None)==any(d['profile']=='exact-reference-sRGB-ICC' for d in decoded.values()),'Unused/missing ICC reference')
    for name,value in decoded.items():validate_metadata(row['images'][name],value)
    require(decoded[NAMES[0]]['png_sha256']==ownership['fixture_sha256'],'Retained original PNG differs from imported fixture')
    require(decoded[NAMES[0]]['rgba_sha256']!=decoded[NAMES[1]]['rgba_sha256'],'Filter reference did not change owned pixels')
    exports=row['raw_exports'];exact(exports,{'saved','cancelled','reverted','original'},'Missing/unexpected raw exports')
    for name,image in [('saved',NAMES[2]),('cancelled',NAMES[3]),('reverted',NAMES[4]),('original',NAMES[0])]:
        exact(exports[name],{'image','relative_path','bytes','sha256'},'Malformed actual export metadata')
        require(exports[name]['relative_path']==name+'/'+FILENAME and exports[name]['image']==image,'Wrong fixed export path/image')
        require(type(exports[name]['bytes']) is int and exports[name]['bytes']==decoded[image]['bytes'] and exports[name]['sha256']==decoded[image]['png_sha256'],'Retained PNG is not the actual exported file')
    saved=compare(decoded[NAMES[2]],decoded[NAMES[1]])
    require(saved['maximum_channel_difference']<=2,'Stored filter pixels differ from independent reference')
    d=details['saved-export'];exact(d,{'max_channel_delta','limit','sole_asset_count'},'Malformed stored save comparison')
    require(integer(d['max_channel_delta'],0,2) and d['max_channel_delta']==saved['maximum_channel_difference'] and type(d['limit']) is int and d['limit']==2 and type(d['sole_asset_count']) is int and d['sole_asset_count']==1,'Wrong stored save comparison')
    for name,expected,a,b in [('cancelled-export',{'rgba_equal_saved':True,'new_edit_made':False,'sole_asset_count':1},NAMES[3],NAMES[2]),('reverted-export',{'rgba_equal_source':True,'sole_asset_count':1},NAMES[4],NAMES[0])]:
        d=details[name];exact(d,expected,'Malformed preservation comparison')
        require(d==expected and type(d['sole_asset_count']) is int and all(type(d[k]) is bool for k in expected if k!='sole_asset_count'),'Wrong preservation comparison')
        require(decoded[a]['rgba']==decoded[b]['rgba'],'Actual Cancel/Revert stored pixels changed')
    d=details['unmodified-original'];expected={'bytes_equal_source':True,'sha256_equal_source':True,'sole_asset_count':1};exact(d,expected,'Malformed original equality')
    require(d==expected and type(d['sole_asset_count']) is int and d['bytes_equal_source'] is True and d['sha256_equal_source'] is True,'Original export preservation unproved')
    return {'schema':SCHEMA,'filter_lifecycle_accepted':True,'dirty_cancel_tested':False,'complete_host_e2e':False,
        'single_photo_topologies':list(topologies),
        'phase_count':len(phases),'editing_generations':sorted(generations),'saved_comparison':saved,
        'images':{name:{key:d[key] for key in ['bytes','png_sha256','rgba_sha256','profile','profile_sha256','rendering_intent']} for name,d in decoded.items()}}

def validate_binary_states(states,catalog):
    require(type(states) is list and 2<=len(states)<=12,'Missing/oversized export binary scalar evidence')
    bound=set();serial=[]
    for row in states:
        require(type(row) is list and len(row)==6 and integer(row[0],0,len(catalog)-1),'Malformed binary scalar observation')
        index,kind,runtime_type,encoding,raw,state=row
        require(type(kind) is str and kind in ('string','number','boolean') and type(runtime_type) is str and 0<len(runtime_type.encode('utf8'))<=96
                and type(encoding) is str and integer(state,0,1),'Invalid binary scalar kind/type/state')
        control=catalog[index]
        labels=[s for s in control[3:5] if s]
        disclosure=control[:3]==['ExportOptions','DisclosureTriangle','button_disclosure'] and control[4]=='customize'
        sidecar=control[:2]==['ExportOptions','CheckBox'] and bool(labels) and all(s in ('Export IPTC as XMP','Export IPTC as XMP:') for s in labels)
        require((disclosure or sidecar) and control[5]==str(state),'Wrong binary target/control state')
        if kind=='string':require(encoding=='' and type(raw) is str and raw in ('0','1') and int(raw)==state,'Invalid binary string evidence')
        elif kind=='boolean':require(encoding in ('c','B') and type(raw) is bool and int(raw)==state,'Invalid binary Boolean evidence')
        else:require(encoding in ('c','C','s','S','i','I','l','L','q','Q','f','d') and type(raw) in (int,float)
                     and raw in (0,1) and math.isfinite(raw) and raw==state,'Invalid binary number evidence')
        encoded=json.dumps(row,separators=(',',':'),ensure_ascii=False)
        require(len(encoded.encode('utf8'))<=256,'Oversized binary scalar observation')
        serial.append(encoded);bound.add(index)
    require(len(serial)==len(set(serial)),'Duplicate binary scalar observation')
    expected={i for i,control in enumerate(catalog) if control[0]=='ExportOptions' and control[1] in ('CheckBox','DisclosureTriangle')}
    require(bound==expected,'Missing/unused binary scalar observations')

def validate_export_bindings(bindings,catalog):
    require(type(bindings) is list and 2<=len(bindings)<=6,'Missing/oversized export option bindings')
    def frame(value):
        require(type(value) is list and len(value)==4 and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=32768 for v in value)
                and value[2]>0 and value[3]>0,'Invalid observed export frame')
        return value
    def contains(parent,child):
        return parent[0]<=child[0] and parent[1]<=child[1] and child[0]+child[2]<=parent[0]+parent[2] and child[1]+child[3]<=parent[1]+parent[3]
    serial=[];bound=set()
    for binding in bindings:
        require(type(binding) is list and len(binding)==10 and integer(binding[0],0,len(catalog)-1),'Malformed export option binding')
        index,method,sheet,group,label,text,label_rect,control_rect,parent_rect,sheet_rect=binding
        require(all(type(value) is str and len(value.encode('utf8'))<=512 for value in binding[1:6]),'Invalid export binding text')
        require(method in ('direct','label-row') and sheet=='sheetWindow_export','Wrong export binding method/sheet')
        control=catalog[index];field=control[0].removeprefix('ExportOptions/')
        require(control[0]=='ExportOptions/'+field and field in ('Color Profile','Size') and control[1]=='PopUpButton','Unadmitted export binding field/control')
        require(text in (field,field+':'),'Observed export label does not name its field')
        require(all(value=='' or value in (field,field+':') for value in control[3:5]),'Contradictory export control label')
        control_rect=frame(control_rect);parent_rect=frame(parent_rect);sheet_rect=frame(sheet_rect)
        require(contains(sheet_rect,parent_rect) and contains(parent_rect,control_rect),'Export control escaped its visible container')
        if method=='direct':
            require(group==label=='' and label_rect==[] and parent_rect==sheet_rect and text in control[3:5],'Unbound direct export label')
        else:
            require(control[2]!='','Associated export control has no observed identity')
            label_rect=frame(label_rect)
            require(contains(parent_rect,label_rect),'Export label escaped its direct parent')
            gap=control_rect[0]-(label_rect[0]+label_rect[2])
            delta=abs(control_rect[1]+control_rect[3]/2-(label_rect[1]+label_rect[3]/2))
            require(0<=gap<=24 and delta<=6,'Export label/control row association mismatch')
        encoded=json.dumps(binding,separators=(',',':'),ensure_ascii=False)
        require(len(encoded.encode('utf8'))<=768,'Oversized export binding observation')
        serial.append(encoded);bound.add(index)
    require(len(serial)==len(set(serial)),'Duplicate export option binding')
    expected={i for i,row in enumerate(catalog) if row[0] in ('ExportOptions/Color Profile','ExportOptions/Size') and row[1]=='PopUpButton'}
    require(bound==expected,'Missing/unused export option association evidence')

def validate_controls(catalog,phases):
    require(type(catalog) is list and 1<=len(catalog)<=64,'Missing/oversized lifecycle control catalog')
    serial=[]
    for row in catalog:
        require(type(row) is list and len(row)==9 and all(type(v) is str and len(v.encode('utf8'))<=512 for v in row[:6]),'Malformed/oversized lifecycle control')
        require(type(row[6]) is int and row[6]==1 and row[7] is True and row[8] is True,'Unusable lifecycle control')
        serial.append(json.dumps(row,separators=(',',':')))
    require(len(serial)==len(set(serial)),'Duplicate lifecycle control catalog row')
    used=set()
    for phase in phases:
        indices=phase['controls'];require(type(indices) is list and len(indices)<=40 and all(integer(i,0,len(catalog)-1) for i in indices),'Invalid lifecycle control occurrence')
        used.update(indices);rows=[catalog[i] for i in indices];name=phase['name'];position=0
        def take(scope,role,identifier=None,title=None,label=None,value=None,public=None):
            nonlocal position
            require(position<len(rows),'Missing lifecycle UI action: '+scope)
            r=rows[position];position+=1
            require(r[0]==scope and r[1]==role,'Wrong lifecycle UI scope/role')
            for index,wanted in [(2,identifier),(3,title),(4,label),(5,value)]:
                if wanted is not None:require(r[index]==wanted,'Wrong lifecycle UI identity/value')
            if public is not None:require(r[3] in (public,public+':') or r[4] in (public,public+':'),'Wrong public export label')
            return r
        def toolbar(title,identifier,role='Button'):
            return take('MainWindow/Toolbar',role,identifier=identifier,label=title)
        def popup(title,wanted):
            known={'Photo Kind':'popup_photoKind','File Name':'popup_useFileName','Subfolder Format':'popup_subfolderFormat'}
            row=take('ExportOptions/'+title,'PopUpButton',identifier=known.get(title))
            if row[5]!=wanted:take('ExportOptions/'+title+'/Menu','MenuItem',title=wanted)
        def binary(role,wanted,identifier=None,label=None,public=None):
            first=take('ExportOptions',role,identifier=identifier,label=label,public=public)
            require(first[5] in ('0','1'),'Unknown export binary initial state')
            if first[5]!=wanted:
                fresh=take('ExportOptions',role,identifier=identifier,label=label,public=public,value=first[5])
                require(fresh[:5]==first[:5],'Binary identity changed before click')
            final=take('ExportOptions',role,identifier=identifier,label=label,public=public,value=wanted)
            require(final[:5]==first[:5],'Binary identity changed after transition')
        def export(phase,original=False):
            take('Photos/MenuBar','MenuBarItem',title='File')
            take('File/Menu','MenuItem',identifier='_NS:1604',title='Export')
            take('File/Export/Menu','MenuItem',identifier='_NS:635' if original else '_NS:630',title='Export Unmodified Original For 1 Photo' if original else 'Export 1 Photo')
            if original:
                binary('CheckBox','0',public='Export IPTC as XMP')
            else:
                popup('Photo Kind','PNG')
                binary('DisclosureTriangle','1',identifier='button_disclosure',label='customize')
                popup('Color Profile','sRGB IEC61966-2.1');popup('Size','Full Size')
            popup('File Name','Use File Name');popup('Subfolder Format','None')
            take('ExportOptions','Button',identifier='button_export',title='Export')
            title='Export Originals' if original else 'Export'
            take('ExportSavePanel','Button',public=title)
            require(position<len(rows) and rows[position][1] in ('ComboBox','TextField'),'Missing owned destination input')
            take('ExportSavePanel/GoToFolder',rows[position][1])
            take('ExportSavePanel/GoToFolder','Button',public='Go')
            take('ExportSavePanel','PopUpButton',public='Where',value=phase)
            take('ExportSavePanel','Button',public=title)
        if name=='source-retained':pass
        elif name=='fade-ready':
            take('Celluloid photo editor','PopUpButton',identifier='photos-extension.filter',label='Filter',value='Original')
            take('photos-extension.filter/Menu','MenuItem',title='Fade')
        elif name in ('reopened-fade','reopened-original'):
            toolbar('Edit','IPXToolbarItemIDToggleEdit')
            take('MainWindow/Toolbar','MenuButton',label='Extensions')
            take('Extensions/Menu','MenuItem',identifier='editWithPlugin:',title='Celluloid')
        elif name in ('saved-export','cancelled-export'):
            toolbar('Save Changes' if name=='saved-export' else 'Cancel','a_saveChangesPressed:' if name=='saved-export' else 'a_cancelPressed:','CheckBox')
            toolbar('Done','IPXToolbarItemIDToggleDoneEdit');export('saved' if name=='saved-export' else 'cancelled')
        elif name=='reverted-export':
            take('Photos/MenuBar','MenuBarItem',title='Image')
            take('Image/Menu','MenuItem',identifier='_NS:766',title='Revert to Original');export('reverted')
        elif name=='unmodified-original':export('original',original=True)
        else:raise ValueError('Unknown lifecycle phase')
        require(position==len(rows),'Extra/unexpected lifecycle UI action')
    require(used==set(range(len(catalog))),'Unused lifecycle control catalog observation')
