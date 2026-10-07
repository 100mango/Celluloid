"""Portable display selection/restore facts; no native display operation."""
import copy
import json
import unittest
import mac_store_display as d

CASE='testStoreOriginalDocumentScreenshots'
TOKEN='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'


def mode(identifier,width,height,scale=1,usable=True):
    return dict(id=identifier,width=width,height=height,pixelWidth=width*scale,pixelHeight=height*scale,usable=usable)


def screen(value):
    width=value['width'];height=value['height']
    return dict(display=7,mode=value,frame=[0,0,width,height],visibleFrame=[0,60,width,height-91],
                cgBounds=[0,0,width,height],scale=value['pixelWidth']/width)


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def display_records(start=100.,scale=1,changed=True):
    after=screen(mode(2,1280,960,scale));before=screen(mode(1,1024,768)) if changed else copy.deepcopy(after)
    setup=dict(v=1,test='-[CelluloidMacUITests.NativeEditorUITests '+CASE+']',token=TOKEN,runnerPID=1234,display=7,
        started=start+.11,finished=start+.18,scope='forAppOnly',requestedWindowPoints=[1280,800],changed=changed,status='ready',
        activeDisplays=[7],before=before,availableModeCount=2 if changed else 1,
        availableModes=[before['mode'],after['mode']] if changed else [after['mode']],selected=after['mode'],configurationResult=0,after=after)
    raw=encode(setup)
    restore=dict(v=1,test=setup['test'],runnerPID=1234,display=7,scope='forAppOnly',started=start+1.3,finished=start+1.6,
        setupSHA256=d.digest(raw),changed=changed,configurationResult=0,original=before['mode'],after=before,restored=True)
    return raw,encode(restore)


class DisplayTests(unittest.TestCase):
    def validate(self,a,b):return d.validate(a,b,{'startTime':100.,'finishTime':102.})
    def test_one_supported_change_and_confirmed_restore(self):
        a,b=display_records();result=self.validate(a,b);self.assertEqual(result['scale'],1);self.assertEqual(result['visibleFrameAX'],[0,31,1280,869])
    def test_already_exact_one_x_mode_is_kept(self):
        a,b=display_records(changed=False);result=self.validate(a,b)
        self.assertEqual(result['scale'],1);self.assertFalse(result['setup']['changed'])
    def test_hidpi_mode_is_rejected(self):
        a,b=display_records(scale=2)
        with self.assertRaisesRegex(ValueError,'no-supported-mode'):self.validate(a,b)
    def test_exact_one_x_required_even_when_larger_display_fits(self):
        before=screen(mode(1,1440,900));exact=mode(3,1280,960);two=mode(2,1280,960,2)
        self.assertEqual(d.choose(before,[before['mode'],two,exact]),exact)
        with self.assertRaisesRegex(ValueError,'no-supported-mode'):d.choose(before,[before['mode'],two])
    def test_no_supported_candidate_is_one_explicit_block(self):
        before=screen(mode(1,1024,768))
        with self.assertRaisesRegex(ValueError,'no-supported-mode'):d.choose(before,[before['mode'],mode(2,1200,900)])
    def test_not_usable_or_wrong_pixel_scale_modes_are_not_selected(self):
        before=screen(mode(1,1024,768))
        for candidate in [mode(2,1440,900,usable=False),mode(3,1440,900,scale=3)]:
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):d.choose(before,[candidate])
    def test_unadvertised_selection_is_rejected(self):
        a,b=display_records();v=json.loads(a);v['selected']=mode(999,1600,1000)
        with self.assertRaises(ValueError):self.validate(encode(v),b)
    def test_permanent_configuration_scope_is_rejected(self):
        a,b=display_records();v=json.loads(a);v['scope']='permanently'
        with self.assertRaises(ValueError):self.validate(encode(v),b)
    def test_failed_restoration_is_separate_runner_cleanup(self):
        a,b=display_records();v=json.loads(b);v['restored']=False
        self.assertEqual(self.validate(a,encode(v))['cleanupStatus'],'unconfirmed')
        self.assertEqual(self.validate(a,None)['cleanupStatus'],'unconfirmed')
    def test_unconfirmed_restore_retains_asynchronous_screen_observation(self):
        a,b=display_records();v=json.loads(b);v['restored']=False
        v['after']=copy.deepcopy(json.loads(a)['after']);v['after']['mode']=v['original']
        raw=encode(v);result=self.validate(a,raw)
        self.assertEqual(result['cleanupStatus'],'unconfirmed');self.assertEqual(result['restore'],v)
        self.assertEqual(result['restoreText'],raw.decode());self.assertEqual(result['restoreSHA256'],d.digest(raw))
        v['restored']=True
        with self.assertRaisesRegex(ValueError,'display-mode-screen-scale-mismatch'):self.validate(a,encode(v))
    def test_restore_bound_to_original_mode_and_setup_digest(self):
        a,b=display_records()
        for key,value in [('setupSHA256','f'*64),('original',mode(9,1600,1000))]:
            v=json.loads(b);v[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(a,encode(v))
    def test_display_records_stay_inside_the_original_case_clock(self):
        a,b=display_records();v=json.loads(b);v['finished']=103
        with self.assertRaises(ValueError):self.validate(a,encode(v))
    def test_cg_and_nsscreen_backing_scale_must_agree(self):
        a,b=display_records(scale=2);v=json.loads(a);v['after']['scale']=1
        with self.assertRaises(ValueError):self.validate(encode(v),b)
    def test_mode_catalogue_bound_is_not_silently_truncated(self):
        a,b=display_records();v=json.loads(a);v['availableModeCount']=129
        with self.assertRaises(ValueError):self.validate(encode(v),b)


if __name__=='__main__':unittest.main()
