"""Strict replay of the bounded, owned real Photos filter lifecycle receipt."""
import base64,hashlib,json,re
from pathlib import Path
from mac_host_self_identity import validate as self_identity,RECEIPT,IDENTIFIER
from mac_host_transport import HOST_CONTRACT
from mac_host_lifecycle_pixels import decode,compare,checked_icc,NAMES,PNG_LIMIT,ICC_LIMIT

SCHEMA='Celluloid.PhotosFilterLifecycle.1'
PHASES=('source-retained','fade-ready','saved-export','reopened-fade','cancelled-export','reverted-export','unmodified-original','reopened-original')
COLUMNS=['scope','role','identifier','title','label','value','count','enabled','hittable']
META={'bytes','sha256','rgba_sha256','format','width','height','bit_depth','color_type','interlace','orientation','profile','profile_encoding','alpha'}
FIELDS={'schema','host_entry_contract','source_sha','context_sha256','test_source_sha256','verifier_sha256','photos_pid','fixture_sha256','asset_label','complete','dirty_cancel_tested','deadline_seconds','control_columns','control_catalog','phases','images','raw_exports','srgb_icc_reference'}
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
    require(row['control_columns']==COLUMNS,'Wrong lifecycle control columns')
    phases=row['phases'];require(type(phases) is list and len(phases)==len(PHASES),'Missing/duplicate lifecycle phases')
    last=-1;details={}
    for index,(phase,name) in enumerate(zip(phases,PHASES)):
        exact(phase,{'index','name','elapsed_ms','controls','details'},'Malformed lifecycle phase')
        require(type(phase['index']) is int and phase['index']==index and phase['name']==name,'Out-of-order lifecycle phase')
        require(integer(phase['elapsed_ms'],0,599999) and phase['elapsed_ms']>=last,'Out-of-budget/nonmonotonic lifecycle phase')
        last=phase['elapsed_ms'];details[name]=phase['details']
    validate_controls(row['control_catalog'],phases)
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
        'phase_count':len(phases),'editing_generations':sorted(generations),'saved_comparison':saved,
        'images':{name:{key:d[key] for key in ['bytes','png_sha256','rgba_sha256','profile','profile_sha256','rendering_intent']} for name,d in decoded.items()}}

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
            row=take('ExportOptions','PopUpButton',public=title)
            if row[5]!=wanted:take('ExportOptions/'+title+'/Menu','MenuItem',title=wanted)
        def export(phase,original=False):
            take('Photos/MenuBar','MenuBarItem',title='File')
            take('File/Menu','MenuItem',identifier='_NS:1604',title='Export')
            take('File/Export/Menu','MenuItem',identifier='_NS:635' if original else '_NS:630',title='Export Unmodified Original For 1 Photo' if original else 'Export 1 Photo')
            if original:
                row=take('ExportOptions','CheckBox',public='Export IPTC as XMP');require(row[5] in ('0','1'),'Unknown sidecar state')
            else:
                popup('Photo Kind','PNG')
                if position<len(rows) and rows[position][:2]==['ExportOptions','DisclosureTriangle']:
                    take('ExportOptions','DisclosureTriangle')
                popup('Color Profile','sRGB IEC61966-2.1');popup('Size','Full Size')
            popup('File Name','Use File Name');popup('Subfolder Format','None')
            take('ExportOptions','Button',public='Export')
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
