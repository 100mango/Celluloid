"""Synthetic calibrated PNG/replay adversaries; no ImageIO or Photos claim."""
import copy,struct,unittest,zlib
from functools import lru_cache
from unittest.mock import patch
import mac_host_lifecycle as gate
import mac_host_lifecycle_pixels as pixels
from test_mac_host_lifecycle import fixture
from test_mac_host_lifecycle_pixels import chunk,encode,fake_icc,pieces,rebuild
from test_mac_photos_lifecycle_observation import packet
from validation_route import FULL,LIFECYCLE,host_clock_profile

CHROMA=list(pixels.SRGB_CHROMATICITIES)

def calibration(gamma=100000,chromaticities=None):
    return chunk(b'gAMA',struct.pack('>I',gamma))+chunk(b'cHRM',struct.pack('>8I',*(CHROMA if chromaticities is None else chromaticities)))


@lru_cache(maxsize=1)
def calibrated_fixture():
    args=list(copy.deepcopy(fixture()));row,context,_,_,_,images,_=args
    context.update(validation_route=dict(LIFECYCLE),host_clock_profile=host_clock_profile(LIFECYCLE),
        owned_saved_pixel_observation='defer-known-saved-pixel-assertion-v1',owned_reverted_profile_observation=gate.REVERTED_PROFILE_MODE)
    row.update(functional_observation_complete=True,deadline_seconds=900)
    # Deliberately different samples and color type demonstrate that portable
    # replay consumes the separately bound canonical pixels, never relabels
    # the calibrated raw samples. This is not an ImageIO conversion fixture.
    raw=encode(width=1200,height=800,color=2,pixels=bytes([10,20,30])*1200*800,profile=calibration())
    canonical=images[pixels.NAMES[0]];raw_decoded=pixels.decode(raw,calibrated_rgb=True);canonical_decoded=pixels.decode(canonical)
    images[pixels.NAMES[4]]=raw
    row['images'][pixels.NAMES[4]].update(bytes=len(raw),sha256=pixels.sha(raw),color_type=2,
        profile='canonical-sRGB',profile_encoding='gama-chrm',rgba_sha256=canonical_decoded['rgba_sha256'])
    row['raw_exports']['reverted'].update(bytes=len(raw),sha256=pixels.sha(raw))
    profile=dict(raw_sha256=pixels.sha(raw),raw_bytes=len(raw),gamma_scaled=100000,chromaticities_scaled=CHROMA,
        imageio_color_space_model='rgb',imageio_color_space_name='synthetic calibrated RGB',imageio_profile_name='unavailable',
        imageio_icc_sha256='unavailable',canonical_sha256=pixels.sha(canonical),canonical_bytes=len(canonical),
        canonical_rgba_sha256=canonical_decoded['rgba_sha256'],canonical_space='sRGB')
    assert raw_decoded['rgba']!=canonical_decoded['rgba']
    return args,dict(png=canonical,profile=profile)


class CalibratedPNGTests(unittest.TestCase):
    def decode(self,data,**kwargs):return pixels.decode(data,dimensions=(3,2),calibrated_rgb=True,**kwargs)

    def test_calibrated_rgb_is_explicit_and_keeps_raw_samples(self):
        raw=bytes([13,127,231,255])*6
        for gamma in (1,45455,100000,pixels.PNG_UINT31_MAX):
            data=encode(profile=calibration(gamma),pixels=raw)
            result=self.decode(data)
            self.assertEqual(result['profile'],'gAMA-cHRM')
            self.assertEqual(result['gamma_scaled'],gamma)
            self.assertEqual(result['chromaticities_scaled'],CHROMA)
            self.assertEqual(result['rgba'],raw)
            self.assertEqual(result['rgba_sha256'],pixels.sha(raw))
            self.assertIsNone(result['profile_sha256'])
            with self.assertRaises(ValueError):pixels.decode(data,dimensions=(3,2))
        reversed_chunks=pieces(encode(profile=calibration()))
        reversed_chunks[1:3]=reversed(reversed_chunks[1:3])
        self.assertEqual(self.decode(rebuild(reversed_chunks))['profile'],'gAMA-cHRM')

    def test_supported_wide_primaries_and_reversed_winding(self):
        p3=[31270,32900,68000,32000,26500,69000,15000,6000]
        for values in (p3,CHROMA[:2]+CHROMA[6:8]+CHROMA[4:6]+CHROMA[2:4]):
            self.assertEqual(self.decode(encode(profile=calibration(chromaticities=values)))['chromaticities_scaled'],values)

    def test_strict_srgb_and_exact_icc_paths_are_unchanged(self):
        for profile in (chunk(b'sRGB',b'\0'),chunk(b'sRGB',b'\0')+calibration(45455)):
            data=encode(profile=profile)
            self.assertEqual(self.decode(data),pixels.decode(data,dimensions=(3,2)))
        icc=fake_icc();reference=dict(bytes=len(icc),sha256=pixels.sha(icc))
        data=encode(profile=chunk(b'iCCP',b'owned sRGB\0\0'+zlib.compress(icc))+calibration(45455))
        self.assertEqual(self.decode(data,reference_icc=reference),pixels.decode(data,dimensions=(3,2),reference_icc=reference))
        with self.assertRaisesRegex(ValueError,'Unknown/contradictory'):self.decode(data)
        for flag in (1,None,'true',[]):
            with self.assertRaisesRegex(ValueError,'switch'):pixels.decode(encode(),dimensions=(3,2),calibrated_rgb=flag)

    def test_missing_duplicate_malformed_and_non_png_integer_profiles_reject(self):
        good=pieces(encode(profile=calibration()))
        for profile in (b'',calibration()[:16],calibration()[16:],calibration()*2,
                chunk(b'gAMA',b'\0')+calibration()[16:],chunk(b'gAMA',b'\0'*8)+calibration()[16:],
                calibration(0),calibration(1<<31),calibration(0xffffffff),
                calibration()[:16]+chunk(b'cHRM',b'\0'*31),calibration()[:16]+chunk(b'cHRM',b'\0'*33)):
            with self.subTest(profile=profile),self.assertRaises(ValueError):self.decode(encode(profile=profile))
        for index in range(8):
            values=list(CHROMA);values[index]=1<<31
            with self.subTest(index=index),self.assertRaises(ValueError):self.decode(encode(profile=calibration(chromaticities=values)))
        for index in (1,2):
            with self.assertRaisesRegex(ValueError,'Duplicate'):self.decode(rebuild(good[:index]+[good[index]]+good[index:]))

    def test_physical_coordinates_degenerate_primaries_and_invalid_white_reject(self):
        bad=[list(CHROMA) for _ in range(10)]
        bad[0][0]=0;bad[1][1]=0;bad[2][2:4]=[80000,30000];bad[3][3]=0
        bad[4][2:4]=bad[4][4:6];bad[5][2:8]=[20000,20000,30000,30000,40000,40000]
        bad[6][:2]=[80000,10000];bad[7][:2]=bad[7][2:4]
        bad[8][:2]=[50000,50000];bad[9][:2]=[47000,46500]  # On the red-green edge.
        for values in bad:
            with self.subTest(values=values),self.assertRaises(ValueError):self.decode(encode(profile=calibration(chromaticities=values)))

    def test_crc_order_higher_profile_conflicts_and_unknown_chunks_reject(self):
        rows=pieces(encode(profile=calibration()))
        for index in (1,2):
            late=rows[:index]+rows[index+1:-1]+[rows[index],rows[-1]]
            with self.assertRaisesRegex(ValueError,'out-of-order'):self.decode(rebuild(late))
            damaged=bytearray(rebuild(rows));offset=8+sum(12+len(body) for _,body in rows[:index])
            damaged[offset+8]^=1
            with self.assertRaisesRegex(ValueError,'CRC'):self.decode(bytes(damaged))
        icc=fake_icc();reference=dict(bytes=len(icc),sha256=pixels.sha(icc))
        higher=(chunk(b'sRGB',b'\0'),chunk(b'iCCP',b'owned sRGB\0\0'+zlib.compress(icc)),
            chunk(b'cICP',b'\1\1\0\1'),chunk(b'mDCV',b'\0'*24),chunk(b'ABCD',b''))
        for extra in higher:
            for profile in (extra+calibration(),calibration()+extra):
                with self.subTest(profile=profile),self.assertRaises(ValueError):self.decode(encode(profile=profile),reference_icc=reference)
        # Matching gAMA is insufficient when cHRM contradicts higher sRGB.
        changed=list(CHROMA);changed[2]=65000
        with self.assertRaisesRegex(ValueError,'Non-sRGB chromaticities'):
            self.decode(encode(profile=chunk(b'sRGB',b'\0')+calibration(45455,changed)))


class CalibratedRevertReplayTests(unittest.TestCase):
    def fixture(self):return copy.deepcopy(calibrated_fixture())
    def validate(self,args,canonical):return gate.validate(*args,observe_saved_pixel_difference=True,canonical_reverted=canonical)
    def reject(self,mutation,pattern=None):
        args,canonical=self.fixture();mutation(args,canonical)
        with self.assertRaisesRegex(ValueError,pattern or '.'):
            self.validate(args,canonical)

    def test_bound_canonical_revert_preserves_raw_export_identity(self):
        args,canonical=self.fixture();original=copy.deepcopy((args,canonical))
        result=self.validate(args,canonical)
        self.assertTrue(result['filter_lifecycle_accepted']);self.assertTrue(result['strict_saved_pixel_passed'])
        self.assertFalse(result['complete_host_e2e']);self.assertEqual(result['strict_saved_pixel_limit'],2)
        self.assertEqual(result['reverted_profile_observation'],canonical['profile'])
        raw=result['images'][pixels.NAMES[4]]
        self.assertEqual(raw['profile'],'gAMA-cHRM')
        self.assertEqual(raw['png_sha256'],canonical['profile']['raw_sha256'])
        self.assertEqual(raw['bytes'],canonical['profile']['raw_bytes'])
        self.assertNotEqual(raw['rgba_sha256'],canonical['profile']['canonical_rgba_sha256'])
        self.assertEqual((args,canonical),original)

    def test_original_gate_and_unscoped_context_remain_closed(self):
        args,canonical=self.fixture()
        with self.assertRaises(ValueError):gate.validate(*args,canonical_reverted=canonical)
        with self.assertRaises(ValueError):gate.validate(*args)
        for key,value in [('validation_route',FULL),('owned_reverted_profile_observation','other'),('owned_saved_pixel_observation','other'),('boundary_probe',{})]:
            self.reject(lambda a,c:a[1].__setitem__(key,value))
        self.reject(lambda a,c:a[1].pop('owned_reverted_profile_observation'))
        with self.assertRaisesRegex(ValueError,'canonical Revert input'):self.validate(args,None)
        for name in pixels.NAMES[:4]:
            self.reject(lambda a,c:a[5].__setitem__(name,a[5][pixels.NAMES[4]]),'Non-sRGB gamma')

    def test_standard_revert_needs_no_canonical_input_and_rejects_unused_input(self):
        args,canonical=self.fixture();args[5][pixels.NAMES[4]]=args[5][pixels.NAMES[0]]
        args[0]['images'][pixels.NAMES[4]]=dict(args[0]['images'][pixels.NAMES[0]])
        args[0]['raw_exports']['reverted'].update(bytes=len(args[5][pixels.NAMES[4]]),sha256=pixels.sha(args[5][pixels.NAMES[4]]))
        self.assertTrue(self.validate(args,None)['filter_lifecycle_accepted'])
        with self.assertRaisesRegex(ValueError,'Unused canonical'):self.validate(args,canonical)
        self.assertTrue(gate.validate(*fixture())['filter_lifecycle_accepted'])

    def test_raw_and_canonical_hash_size_and_declaration_are_bound(self):
        for key,value in [('raw_sha256','0'*64),('raw_bytes',1),('gamma_scaled',45455),('chromaticities_scaled',CHROMA[:-1]+[6001]),
                ('canonical_sha256','0'*64),('canonical_bytes',1),('canonical_rgba_sha256','0'*64)]:
            self.reject(lambda a,c:c['profile'].__setitem__(key,value),'binding mismatch|declaration mismatch')
        self.reject(lambda a,c:a[5].__setitem__(pixels.NAMES[4],rebuild(pieces(a[5][pixels.NAMES[4]])[:-1]+[(b'tEXt',b'changed'),(b'IEND',b'')])),'raw PNG binding')
        self.reject(lambda a,c:c.__setitem__('png',rebuild(pieces(c['png'])[:-1]+[(b'tEXt',b'changed'),(b'IEND',b'')])),'binding mismatch')

    def test_profile_schema_fields_types_names_and_claims_fail_closed(self):
        for key in gate.REVERTED_PROFILE_FIELDS:
            self.reject(lambda a,c:c['profile'].pop(key),'profile field')
        self.reject(lambda a,c:c['profile'].update(unknown=True),'profile field')
        self.reject(lambda a,c:c.update(unknown=True),'canonical Revert input')
        invalid=[('raw_bytes',True),('canonical_bytes',True),('gamma_scaled',True),('gamma_scaled',0),('gamma_scaled',1<<31),
            ('chromaticities_scaled',tuple(CHROMA)),('chromaticities_scaled',[True]+CHROMA[1:]),
            ('imageio_color_space_model','gray'),('canonical_space','Display P3'),('imageio_icc_sha256','x'*64),
            ('imageio_icc_sha256','A'*64),('raw_sha256',None),('canonical_rgba_sha256',False)]
        for key in ('imageio_color_space_name','imageio_profile_name'):
            invalid.extend((key,value) for value in ('','x'*129,'é'*65,'bad\nname','bad\x00name','bad\x7fname',1,None))
        for key,value in invalid:
            with self.subTest(key=key,value=value):self.reject(lambda a,c:c['profile'].__setitem__(key,value))
        args,canonical=self.fixture();canonical['profile'].update(imageio_icc_sha256='a'*64,imageio_profile_name='é'*64)
        self.assertTrue(self.validate(args,canonical)['filter_lifecycle_accepted'])

    def test_metadata_does_not_relabel_or_replace_raw_png(self):
        for key,value in [('profile','sRGB'),('profile_encoding','srgb-chunk'),('color_type',6),('sha256','0'*64),('bytes',1),('rgba_sha256','0'*64)]:
            self.reject(lambda a,c:a[0]['images'][pixels.NAMES[4]].__setitem__(key,value))
        self.reject(lambda a,c:a[0]['raw_exports']['reverted'].update(bytes=c['profile']['canonical_bytes'],sha256=c['profile']['canonical_sha256']),
            'actual exported file')
        self.reject(lambda a,c:a[5].__setitem__(pixels.NAMES[4],c['png']),'Unused canonical')
        args,_=self.fixture();raw=pixels.decode(args[5][pixels.NAMES[4]],calibrated_rgb=True)
        metadata=dict(args[0]['images'][pixels.NAMES[4]],profile='sRGB',profile_encoding='icc-reference',rgba_sha256=raw['rgba_sha256'])
        with self.assertRaisesRegex(ValueError,'Unconverted lifecycle profile'):gate.validate_metadata(metadata,raw)

    def test_canonical_png_must_pass_the_original_strict_decoder(self):
        for data in (b'',encode(),encode(width=1200,height=800,profile=calibration()),
                encode(width=1200,height=800,pixels=bytes([10,20,30,254])*1200*800)):
            self.reject(lambda a,c:c.__setitem__('png',data))
        args,canonical=self.fixture();bad=bytearray(canonical['png']);bad[-1]^=1;canonical['png']=bytes(bad)
        with self.assertRaisesRegex(ValueError,'CRC'):self.validate(args,canonical)

    def test_canonical_exact_reference_icc_is_checked_and_counted_as_used(self):
        args,canonical=self.fixture();icc=fake_icc();args[0]['srgb_icc_reference']=dict(bytes=len(icc),sha256=pixels.sha(icc))
        rows=pieces(canonical['png']);rows[1]=(b'iCCP',b'owned sRGB\0\0'+zlib.compress(icc));canonical['png']=rebuild(rows)
        canonical['profile'].update(canonical_sha256=pixels.sha(canonical['png']),canonical_bytes=len(canonical['png']))
        self.assertTrue(self.validate(args,canonical)['filter_lifecycle_accepted'])
        args[0]['srgb_icc_reference']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'differs from independent'):self.validate(args,canonical)

    def test_exact_revert_comparison_rejects_even_one_changed_channel(self):
        args,canonical=self.fixture();changed=bytearray(pixels.decode(canonical['png'])['rgba']);changed[0]+=1
        canonical['png']=encode(width=1200,height=800,pixels=bytes(changed));d=pixels.decode(canonical['png'])
        canonical['profile'].update(canonical_sha256=d['png_sha256'],canonical_bytes=d['bytes'],canonical_rgba_sha256=d['rgba_sha256'])
        args[0]['images'][pixels.NAMES[4]]['rgba_sha256']=d['rgba_sha256']
        with self.assertRaisesRegex(ValueError,'Actual Cancel/Revert stored pixels changed'):self.validate(args,canonical)

    def test_known_saved_three_level_difference_stays_failed_after_canonical_revert(self):
        args=packet(True);_,canonical=self.fixture();raw=calibrated_fixture()[0][5][pixels.NAMES[4]]
        args[1]['owned_reverted_profile_observation']=gate.REVERTED_PROFILE_MODE
        args[5][pixels.NAMES[4]]=raw;canonical['png']=args[5][pixels.NAMES[0]];d=pixels.decode(canonical['png'])
        canonical['profile'].update(canonical_sha256=d['png_sha256'],canonical_bytes=d['bytes'],canonical_rgba_sha256=d['rgba_sha256'])
        args[0]['images'][pixels.NAMES[4]].update(bytes=len(raw),sha256=pixels.sha(raw),color_type=2,profile='canonical-sRGB',profile_encoding='gama-chrm',rgba_sha256=d['rgba_sha256'])
        args[0]['raw_exports']['reverted'].update(bytes=len(raw),sha256=pixels.sha(raw))
        with patch.object(gate,'KNOWN_SAVED_RGBA',args[0]['images'][pixels.NAMES[2]]['rgba_sha256']),patch.object(gate,'KNOWN_REFERENCE_RGBA',args[0]['images'][pixels.NAMES[1]]['rgba_sha256']):
            result=self.validate(args,canonical)
        self.assertTrue(result['functional_lifecycle_qualified']);self.assertFalse(result['filter_lifecycle_accepted'])
        self.assertFalse(result['strict_saved_pixel_passed']);self.assertEqual(result['strict_saved_pixel_limit'],2)
        self.assertFalse(args[0]['complete'])


if __name__=='__main__':unittest.main()
