"""Synthetic full lifecycle replay; never claims a Photos runtime result."""
from validation_route import FULL,host_clock_profile,context_clock
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
    if original:rows.extend([control('ExportOptions','CheckBox',label='Export IPTC as XMP',value='0')]*2)
    else:
        rows.append(control('ExportOptions/Photo Kind','PopUpButton','popup_photoKind',value='PNG'))
        rows.append(control('ExportOptions','DisclosureTriangle','button_disclosure',label='customize',value='0'))
        rows.append(control('ExportOptions','DisclosureTriangle','button_disclosure',label='customize',value='0'))
        rows.append(control('ExportOptions','DisclosureTriangle','button_disclosure',label='customize',value='1'))
        for title,value in [('Color Profile','sRGB'),('Size','Full Size')]:rows.append(control('ExportOptions/'+title,'PopUpButton','synthetic_'+title,label=title,value=value))
    for title,identifier,value in [('File Name','popup_useFileName','Use File Name'),('Subfolder Format','popup_subfolderFormat','None')]:rows.append(control('ExportOptions/'+title,'PopUpButton',identifier,value=value))
    final='Export Originals' if original else 'Export'
    destination='/owned/tmp/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/'+phase
    path=control('ExportSavePanel/GoToWindow','TextField','PathTextField',value=destination)
    rows.extend([control('ExportOptions','Button','button_export',title='Export'),control('ExportSavePanel','Button','OKButton',title=final),
        path,path,control('ExportSavePanel','PopUpButton','where popup',title='Where:',value=phase),control('ExportSavePanel','Button','OKButton',title=final)])
    return rows

@lru_cache(maxsize=1)
def sample_images():
    source=encode(width=1200,height=800,pixels=bytes([200,100,50,255])*1200*800)
    expected=encode(width=1200,height=800,pixels=bytes([150,90,60,255])*1200*800)
    return dict(zip(pixels.NAMES,[source,expected,expected,expected,source]))

def fixture(context=None,photos=None,ownership=None,context_hash='f'*64):
    if context is None:
        ext='/owned/CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex';exe=ext+'/Contents/MacOS/CelluloidMacPhotosExtension'
        context={'validation_route':dict(FULL),'host_clock_profile':host_clock_profile(FULL),'source_sha':'a'*40,'extension_id':'Mango.Celluloid.CelluloidPhotoExtension','extension_path':ext,'extension_executable':exe,
            'extension_debug_dylib':exe+'.debug.dylib','extension_executable_sha256':'e'*64,'extension_debug_dylib_sha256':'9'*64,
            'test_source_sha256':'b'*64,'script_sha256':'c'*64}
    photos=photos or {'pid':122}
    images=dict(sample_images());source=images[pixels.NAMES[0]]
    ownership=ownership or {'fixture_sha256':gate.sha(source),'asset_label':'sole owned synthetic asset'}
    baseline=payload(context);top={'schema':gate.SCHEMA,'host_entry_contract':gate.HOST_CONTRACT,'source_sha':context['source_sha'],
        'context_sha256':context_hash,'test_source_sha256':context['test_source_sha256'],'verifier_sha256':context['script_sha256'],
        'photos_pid':photos['pid'],'fixture_sha256':ownership['fixture_sha256'],'asset_label':ownership['asset_label'],
        'complete':True,'dirty_cancel_tested':False,'deadline_seconds':context_clock(context)['case_seconds'],'control_columns':gate.COLUMNS,'control_catalog':[],
        'phases':[],'images':{},'raw_exports':{},'srgb_icc_reference':None,'single_photo_topologies':['collection-absent'],'export_option_bindings':[],
        'binary_states':[],'binary_scalar_self_tested':True}
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
    for index,row in enumerate(top['control_catalog']):
        if row[0] in ('ExportOptions/Color Profile','ExportOptions/Size') and row[1]=='PopUpButton':
            top['export_option_bindings'].append([index,'direct','sheetWindow_export','','',row[4],[],[410,300,302,26],[240,200,542,450],[240,200,542,450]])
        if row[0]=='ExportOptions' and row[1] in ('DisclosureTriangle','CheckBox'):
            top['binary_states'].append([index,'number','Synthetic.NSNumber','i',int(row[5]),int(row[5])])
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
        self.assertEqual(result['single_photo_topologies'],['collection-absent'])
    def test_both_observed_single_photo_topologies_are_strict_and_bounded(self):
        for values in [['collection-present'],['collection-absent'],list(gate.SINGLE_PHOTO_TOPOLOGIES),list(reversed(gate.SINGLE_PHOTO_TOPOLOGIES))]:
            args=self.packet();args[0]['single_photo_topologies']=values
            self.assertEqual(self.validate(args)['single_photo_topologies'],values)
        for values in [None,{},'collection-absent',[],[True],[1],[{}],['unknown'],['collection-absent']*2,list(gate.SINGLE_PHOTO_TOPOLOGIES)+['collection-absent']]:
            self.reject(lambda a:a[0].update(single_photo_topologies=values))
        self.reject(lambda a:a[0].pop('single_photo_topologies'))
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
    def test_measured_srgb_title_selection_and_exact_value_remain_required(self):
        args=self.packet();row=args[0];catalog=row['control_catalog']
        profile=next(i for i,value in enumerate(catalog) if value[:2]==['ExportOptions/Color Profile','PopUpButton'])
        catalog[profile][5]='Most Compatible'
        selected=len(catalog);catalog.append(control('ExportOptions/Color Profile/Menu','MenuItem','_popUpItemAction:',title='sRGB'))
        for phase in row['phases']:
            if profile in phase['controls']:
                position=phase['controls'].index(profile);phase['controls'].insert(position+1,selected)
        gate.validate(*args)
        for wrong in ['Most Compatible','AdobeRGB','Display P3','Original','sRGB IEC61966-2.1','srgb']:
            bad=copy.deepcopy(args);bad[0]['control_catalog'][selected][3]=wrong
            with self.subTest(menu=wrong),self.assertRaises(ValueError):gate.validate(*bad)
        for wrong in ['sRGB IEC61966-2.1','Display P3','Original']:
            self.reject(lambda a,w=wrong:next(value for value in a[0]['control_catalog'] if value[:2]==['ExportOptions/Color Profile','PopUpButton']).__setitem__(5,w))

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
    def test_actual_same_parent_label_row_binding_replays_without_echoed_popup_label(self):
        args=self.packet()
        for row in args[0]['export_option_bindings']:
            control=args[0]['control_catalog'][row[0]];control[4]=''
            field=control[0].split('/',1)[1]
            row[1:]=['label-row','sheetWindow_export','synthetic_parent','synthetic_label',field+':',
                     [300,304,104,18],[410,300,302,26],[260,220,502,400],[240,200,542,450]]
        self.assertTrue(self.validate(args)['filter_lifecycle_accepted'])
        self.assertLess(len(json.dumps(args[0],separators=(',',':')).encode()),16_000)
    def test_export_binding_unknown_labels_forgery_geometry_duplicates_and_missing_evidence_reject(self):
        for index,value in [(0,True),(0,0),(1,'guessed'),(2,'another_sheet'),(3,'unexpected_direct_parent'),
                            (5,'wrong field'),(5,''),(6,[1,2,3,4]),(7,[410,float('nan'),302,26]),
                            (7,[410,300,0,26]),(7,[False,300,302,26]),(7,[800,300,302,26]),
                            (8,[240,200,542,1000]),(9,[240,200,10,10])]:
            with self.subTest(column=index,value=value):
                self.reject(lambda a:a[0]['export_option_bindings'][0].__setitem__(index,value))
        self.reject(lambda a:a[0]['export_option_bindings'].pop())
        self.reject(lambda a:a[0]['export_option_bindings'].append(a[0]['export_option_bindings'][0]))
        self.reject(lambda a:a[0].pop('export_option_bindings'))
        self.reject(lambda a:a[0]['control_catalog'][a[0]['export_option_bindings'][0][0]].__setitem__(4,'unrelated'))
        for label_rect in [[300,304,80,18],[300,330,104,18],[420,304,104,18],[100,304,304,18]]:
            def mutate(a):
                row=a[0]['export_option_bindings'][0]
                row[1:]=['label-row','sheetWindow_export','group','label',row[5],label_rect,[410,300,302,26],
                         [260,220,502,400],[240,200,542,450]]
            self.reject(mutate)
    def test_observed_known_ids_and_customize_closed_to_expanded_receipt_are_required(self):
        for scope,role,identifier in [('ExportOptions/Photo Kind','PopUpButton','popup_photoKind'),
            ('ExportOptions/File Name','PopUpButton','popup_useFileName'),('ExportOptions/Subfolder Format','PopUpButton','popup_subfolderFormat'),
            ('ExportOptions','Button','button_export'),('ExportOptions','DisclosureTriangle','button_disclosure')]:
            def mutate(a):
                row=next(r for r in a[0]['control_catalog'] if r[:2]==[scope,role] and r[2]==identifier);row[2]='unknown'
            self.reject(mutate)
        self.reject(lambda a:next(row for row in a[0]['control_catalog'] if row[1]=='DisclosureTriangle' and row[5]=='1').__setitem__(5,'0'))
    def test_binary_scalar_string_number_and_boolean_evidence_recompute_exact_states(self):
        for kind,encoding,convert in [('string','',str),('number','d',float),('number','q',int),('boolean','c',bool),('boolean','B',bool)]:
            args=self.packet()
            for row in args[0]['binary_states']:row[1:5]=[kind,'Synthetic.'+kind,encoding,convert(row[5])]
            self.assertTrue(self.validate(args)['filter_lifecycle_accepted'])
        self.assertLess(len(json.dumps(self.packet()[0],separators=(',',':')).encode()),16_000)
    def test_binary_scalar_forgery_missing_mixed_fractional_and_nonfinite_values_reject(self):
        for column,value in [(0,True),(0,0),(1,'guessed'),(2,''),(2,'x'*97),(2,[]),(3,'B'),(3,'unknown'),
                             (4,None),(4,'0'),(4,False),(4,[]),(4,{}),(4,-1),(4,2),(4,10**400),(4,.5),(4,float('nan')),
                             (4,float('inf')),(4,float('-inf')),(5,True),(5,2),(5,1)]:
            with self.subTest(column=column,value=value):self.reject(lambda a:a[0]['binary_states'][0].__setitem__(column,value))
        for kind,encoding,raw in [('string','',''),('string','','mixed'),('string','',' 0'),('string','','01'),
            ('string','','+1'),('string','','1.0'),('string','','true'),('string','','false'),('string','','2'),
            ('boolean','c',0),('boolean','c','false'),('boolean','i',False),('number','i',True)]:
            self.reject(lambda a:a[0]['binary_states'][0].__setitem__(slice(1,5),[kind,'Synthetic.Value',encoding,raw]))
        self.reject(lambda a:a[0]['binary_states'].pop())
        self.reject(lambda a:a[0]['binary_states'].append(a[0]['binary_states'][0]))
        self.reject(lambda a:a[0].pop('binary_states'))
        for value in [False,1,None]:self.reject(lambda a:a[0].update(binary_scalar_self_tested=value))
    def test_binary_fresh_and_final_observations_cannot_be_omitted_or_relabelled(self):
        def omit_fresh(a):
            indices=a[0]['phases'][2]['controls'];catalog=a[0]['control_catalog']
            positions=[i for i,index in enumerate(indices) if catalog[index][1]=='DisclosureTriangle']
            indices.pop(positions[1])
        self.reject(omit_fresh)
        def wrong_final(a):
            indices=a[0]['phases'][2]['controls'];catalog=a[0]['control_catalog']
            positions=[i for i,index in enumerate(indices) if catalog[index][1]=='DisclosureTriangle']
            indices[positions[2]]=indices[positions[0]]
        self.reject(wrong_final)
        def omit_sidecar_final(a):
            indices=a[0]['phases'][6]['controls'];catalog=a[0]['control_catalog']
            positions=[i for i,index in enumerate(indices) if catalog[index][:2]==['ExportOptions','CheckBox']]
            indices.pop(positions[1])
        self.reject(omit_sidecar_final)
    def test_owned_destination_requires_exact_scoped_fields_ids_and_phase_path(self):
        for column,value in [(0,'ExportSavePanel/GoToFolder'),(1,'ComboBox'),(1,'Button'),(2,'other'),
            (5,'saved'),(5,'/tmp/saved'),(5,'/owned/tmp/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/cancelled'),
            (5,'/owned/tmp/CelluloidPhotosLifecycle-00000000-0000-0000-0000-000000000000/saved'),
            (5,'/owned/tmp/CelluloidPhotosLifecycle-invalid/saved'),
            (5,'/owned/tmp/../CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/saved'),
            (5,'/owned//tmp/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/saved'),
            (5,'//owned/tmp/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/saved'),
            (5,'/owned/'+('é'*250)+'/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/saved'),
            (5,'/owned/\x00tmp/CelluloidPhotosLifecycle-12345678-1234-4321-8123-123456789ABC/saved'),
            (6,2),(7,False),(8,False)]:
            def mutate(a):
                row=next(r for r in a[0]['control_catalog'] if r[0]=='ExportSavePanel/GoToWindow' and r[5].endswith('/saved'))
                row[column]=value
            with self.subTest(column=column,value=value):self.reject(mutate)
        for scope,role,column,value in [('ExportSavePanel','PopUpButton',2,'other'),('ExportSavePanel','PopUpButton',3,'Where'),
                                       ('ExportSavePanel','PopUpButton',5,'Desktop'),('ExportSavePanel','Button',2,'other')]:
            self.reject(lambda a:next(r for r in a[0]['control_catalog'] if r[:2]==[scope,role]).__setitem__(column,value))
    def test_fresh_path_readback_and_one_generated_root_are_required(self):
        def changed_readback(a):
            row=a[0];phase=row['phases'][2];catalog=row['control_catalog']
            positions=[i for i,index in enumerate(phase['controls']) if catalog[index][0]=='ExportSavePanel/GoToWindow']
            changed=copy.deepcopy(catalog[phase['controls'][positions[1]]]);changed[5]+='-different'
            phase['controls'][positions[1]]=len(catalog);catalog.append(changed)
        self.reject(changed_readback)
        def omit_readback(a):
            phase=a[0]['phases'][2];catalog=a[0]['control_catalog']
            position=next(i for i,index in enumerate(phase['controls']) if catalog[index][0]=='ExportSavePanel/GoToWindow')
            phase['controls'].pop(position)
        self.reject(omit_readback)
        def changed_root(a):
            row=next(r for r in a[0]['control_catalog'] if r[0]=='ExportSavePanel/GoToWindow' and r[5].endswith('/original'))
            row[5]=row[5].replace('12345678-1234-4321-8123-123456789ABC','22345678-1234-4321-8123-123456789ABC')
        self.reject(changed_root)

if __name__=='__main__':unittest.main()
