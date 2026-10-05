"""Synthetic full lifecycle replay; never claims a Photos runtime result."""
import copy,hashlib,json,unittest
from functools import lru_cache
import mac_host_lifecycle as gate
import mac_host_lifecycle_pixels as pixels
from test_mac_host_lifecycle_pixels import encode
from test_mac_host_self_identity import payload,envelope

def control(scope,role,identifier='',title='',label='',value=''):
    return [scope,role,identifier,title,label,value,1,True,True]
def export_controls(phase,original=False):
    rows=[control('Photos/MenuBar','MenuBarItem',title='File'),control('File/Menu','MenuItem','_NS:1604','Export'),
        control('File/Export/Menu','MenuItem','_NS:635' if original else '_NS:630','Export Unmodified Original For 1 Photo' if original else 'Export 1 Photo')]
    if original:rows.append(control('ExportOptions','CheckBox',label='Export IPTC as XMP',value='0'))
    else:
        for title,value in [('Photo Kind','PNG'),('Color Profile','sRGB IEC61966-2.1'),('Size','Full Size')]:rows.append(control('ExportOptions','PopUpButton',label=title,value=value))
    for title,value in [('File Name','Use File Name'),('Subfolder Format','None')]:rows.append(control('ExportOptions','PopUpButton',label=title,value=value))
    final='Export Originals' if original else 'Export'
    rows.extend([control('ExportOptions','Button',label='Export'),control('ExportSavePanel','Button',label=final),
        control('ExportSavePanel/GoToFolder','ComboBox'),control('ExportSavePanel/GoToFolder','Button',label='Go'),
        control('ExportSavePanel','PopUpButton',label='Where',value=phase),control('ExportSavePanel','Button',label=final)])
    return rows

@lru_cache(maxsize=1)
def sample_images():
    source=encode(width=1200,height=800,pixels=bytes([200,100,50,255])*1200*800)
    expected=encode(width=1200,height=800,pixels=bytes([150,90,60,255])*1200*800)
    return dict(zip(pixels.NAMES,[source,expected,expected,expected,source]))

def fixture(context=None,photos=None,ownership=None,context_hash='f'*64):
    if context is None:
        ext='/owned/CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex';exe=ext+'/Contents/MacOS/CelluloidMacPhotosExtension'
        context={'source_sha':'a'*40,'extension_id':'Mango.Celluloid.CelluloidPhotoExtension','extension_path':ext,'extension_executable':exe,
            'extension_debug_dylib':exe+'.debug.dylib','extension_executable_sha256':'e'*64,'extension_debug_dylib_sha256':'9'*64,
            'test_source_sha256':'b'*64,'script_sha256':'c'*64}
    photos=photos or {'pid':122}
    images=dict(sample_images());source=images[pixels.NAMES[0]]
    ownership=ownership or {'fixture_sha256':gate.sha(source),'asset_label':'sole owned synthetic asset'}
    baseline=payload(context);top={'schema':gate.SCHEMA,'host_entry_contract':gate.HOST_CONTRACT,'source_sha':context['source_sha'],
        'context_sha256':context_hash,'test_source_sha256':context['test_source_sha256'],'verifier_sha256':context['script_sha256'],
        'photos_pid':photos['pid'],'fixture_sha256':ownership['fixture_sha256'],'asset_label':ownership['asset_label'],
        'complete':True,'dirty_cancel_tested':False,'deadline_seconds':600,'control_columns':gate.COLUMNS,'control_catalog':[],
        'phases':[],'images':{},'raw_exports':{},'srgb_icc_reference':None}
    def phase(name,details,controls=()):
        ids=[]
        for row in controls:
            if row not in top['control_catalog']:top['control_catalog'].append(row)
            ids.append(top['control_catalog'].index(row))
        index=len(top['phases']);top['phases'].append({'index':index,'name':name,'elapsed_ms':(index+1)*1000,'controls':ids,'details':details})
    def reopen(filter,generation):
        identity=payload(context);identity['generation']=generation;raw=json.dumps(identity,separators=(',',':'),sort_keys=True)
        return {'filter':filter,'editor_count_before':0,'editor_count_after':1,'identity_element_counts':[1,1],'observations':[envelope(raw),envelope(raw)]}
    toolbar=lambda title,id,role='Button':control('MainWindow/Toolbar',role,id,label=title)
    reentry=[toolbar('Edit','IPXToolbarItemIDToggleEdit'),control('MainWindow/Toolbar','MenuButton',label='Extensions'),control('Extensions/Menu','MenuItem','editWithPlugin:','Celluloid')]
    phase('source-retained',{'fixture_filename':gate.FILENAME,'fixture_sha256':ownership['fixture_sha256'],'retained_before_import':True})
    phase('fade-ready',{'filter':'Fade','independent_filter':'CIPhotoEffectInstant','jpeg_quality':0.95,'jpeg_sha256':'7'*64},
        [control('Celluloid photo editor','PopUpButton','photos-extension.filter',label='Filter',value='Original'),control('photos-extension.filter/Menu','MenuItem',title='Fade')])
    phase('saved-export',{'max_channel_delta':0,'limit':2,'sole_asset_count':1},[toolbar('Save Changes','a_saveChangesPressed:','CheckBox'),toolbar('Done','IPXToolbarItemIDToggleDoneEdit')]+export_controls('saved'))
    phase('reopened-fade',reopen('Fade','22345678-1234-4321-8123-123456789ABC'),reentry)
    phase('cancelled-export',{'rgba_equal_saved':True,'new_edit_made':False,'sole_asset_count':1},[toolbar('Cancel','a_cancelPressed:','CheckBox'),toolbar('Done','IPXToolbarItemIDToggleDoneEdit')]+export_controls('cancelled'))
    phase('reverted-export',{'rgba_equal_source':True,'sole_asset_count':1},[control('Photos/MenuBar','MenuBarItem',title='Image'),control('Image/Menu','MenuItem','_NS:766','Revert to Original')]+export_controls('reverted'))
    phase('unmodified-original',{'bytes_equal_source':True,'sha256_equal_source':True,'sole_asset_count':1},export_controls('original',True))
    phase('reopened-original',reopen('Original','32345678-1234-4321-8123-123456789ABC'),reentry)
    for name,data in images.items():
        d=pixels.decode(data);top['images'][name]={'bytes':len(data),'sha256':gate.sha(data),'rgba_sha256':d['rgba_sha256'],
            'format':'public.png','width':1200,'height':800,'bit_depth':8,'color_type':6,'interlace':0,'orientation':1,'profile':'sRGB','profile_encoding':'srgb-chunk','alpha':'opaque'}
    for phase,name in [('saved',pixels.NAMES[2]),('cancelled',pixels.NAMES[3]),('reverted',pixels.NAMES[4]),('original',pixels.NAMES[0])]:
        top['raw_exports'][phase]={'image':name,'relative_path':phase+'/'+gate.FILENAME,'bytes':len(images[name]),'sha256':gate.sha(images[name])}
    return top,context,photos,ownership,baseline,images,context_hash

class LifecycleReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=fixture()
    def packet(self):return copy.deepcopy(self.original)
    def validate(self,args):return gate.validate(*args)
    def reject(self,mutation):
        args=self.packet();mutation(args)
        with self.assertRaises((ValueError,KeyError,TypeError)):self.validate(args)
    def test_positive_recomputes_every_actual_png_and_keeps_limited_claim(self):
        result=self.validate(self.packet());self.assertTrue(result['filter_lifecycle_accepted']);self.assertFalse(result['dirty_cancel_tested']);self.assertFalse(result['complete_host_e2e'])
        self.assertEqual(result['phase_count'],8);self.assertEqual(len(result['editing_generations']),3)
    def test_missing_duplicate_out_of_order_or_late_phases_reject(self):
        for mutate in [lambda r:r.pop(),lambda r:r.append(r[-1]),lambda r:r.reverse(),lambda r:r[2].update(index=True),
                       lambda r:r[3].update(elapsed_ms=600000),lambda r:r[4].update(elapsed_ms=1),lambda r:r[1].update(extra=0)]:
            self.reject(lambda a:mutate(a[0]['phases']))
    def test_source_product_fixture_host_and_primitive_claims_reject(self):
        for key,value in [('schema','old'),('host_entry_contract','old'),('source_sha','d'*40),('context_sha256','0'*64),('test_source_sha256','0'*64),
            ('verifier_sha256','0'*64),('photos_pid',True),('fixture_sha256','0'*64),('asset_label','other'),('complete',1),('dirty_cancel_tested',True),('deadline_seconds',True)]:
            self.reject(lambda a:a[0].update({key:value}))
    def test_stale_generation_changed_product_or_missing_raw_identity_reject(self):
        for phase in [3,7]:
            self.reject(lambda a:a[0]['phases'][phase]['details'].update(observations=[]))
            def stale(a):
                row=a[0]['phases'][phase]['details'];raw=json.dumps(a[4]);row['observations']=[envelope(raw),envelope(raw)]
            self.reject(stale)
        self.reject(lambda a:a[1].update(extension_debug_dylib_sha256='0'*64))
    def test_missing_relabelled_changed_image_or_export_path_reject(self):
        self.reject(lambda a:a[5].pop(pixels.NAMES[2]))
        self.reject(lambda a:a[0]['raw_exports']['saved'].update(relative_path='../outside.png'))
        self.reject(lambda a:a[0]['images'][pixels.NAMES[2]].update(rgba_sha256='0'*64))
        self.reject(lambda a:a[0]['images'][pixels.NAMES[2]].update(width=True))
        self.reject(lambda a:a[0]['raw_exports']['original'].update(sha256='0'*64))
    def test_control_omissions_duplicates_wrong_scope_and_unused_rows_reject(self):
        self.reject(lambda a:a[0]['phases'][2]['controls'].pop())
        self.reject(lambda a:a[0]['phases'][4]['controls'].reverse())
        self.reject(lambda a:a[0]['phases'][5]['controls'].append(a[0]['phases'][5]['controls'][0]))
        self.reject(lambda a:a[0]['control_catalog'][0].__setitem__(7,1))
        self.reject(lambda a:a[0]['control_catalog'][0].__setitem__(6,2))
        self.reject(lambda a:a[0]['control_catalog'][0].__setitem__(0,'Other app'))
        self.reject(lambda a:a[0]['control_catalog'].append(control('unobserved','Button')))
        self.reject(lambda a:a[0]['control_catalog'].append(a[0]['control_catalog'][0]))
    def test_wrong_filter_reference_no_change_cancel_and_revert_claims_reject(self):
        self.reject(lambda a:a[0]['phases'][1]['details'].update(independent_filter='CIPhotoEffectFade'))
        self.reject(lambda a:a[0]['phases'][1]['details'].update(jpeg_quality=1))
        self.reject(lambda a:a[0]['phases'][2]['details'].update(limit=3))
        self.reject(lambda a:a[0]['phases'][4]['details'].update(new_edit_made=True))
        self.reject(lambda a:a[0]['phases'][5]['details'].update(rgba_equal_source=1))
    def test_hash_correct_pixel_mutation_still_rejects(self):
        def mutate(a):
            name=pixels.NAMES[2];old=pixels.decode(a[5][name]);rgba=bytearray(old['rgba']);rgba[0]+=3
            data=encode(width=1200,height=800,pixels=bytes(rgba));a[5][name]=data
            a[0]['images'][name].update(bytes=len(data),sha256=gate.sha(data),rgba_sha256=gate.sha(bytes(rgba)))
            a[0]['raw_exports']['saved'].update(bytes=len(data),sha256=gate.sha(data))
        self.reject(mutate)

if __name__=='__main__':unittest.main()
