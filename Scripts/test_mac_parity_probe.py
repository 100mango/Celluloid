#!/usr/bin/env python3
import copy,json,unittest
import run_mac_parity_probe as probe

class MacParityProbeTests(unittest.TestCase):
    def fixture(self):
        controls=json.loads(probe.control_bytes());two=controls['profiles']['2x']['images']
        source=controls['inputImage'];archive=controls['inputArchive'];full=two['full']
        fixture={'name':'manufactured-affine','identifier':'Mango.CelluloidPhotoExtension','version':'1.0',
          'base64':archive['base64'],'sha256':archive['sha256'],'sourceBase64':source['base64'],'sourceSHA256':source['sha256'],
          'renderedBase64':full['base64'],'renderedSHA256':full['sha256'],
          'components':[dict(name=n,**(two.get(n) or controls['common'][n])) for n in ['filtered-base','bubble-artwork','sticker-artwork','all-artwork']]}
        rows=[]
        for name in ['full','filtered-base','bubble-artwork','sticker-artwork','all-artwork']:
            blob=two.get(name) or controls['common'][name]
            rows.append({'name':name,'actualPNG_SHA256':blob['sha256'],'originalPNG_SHA256':blob['sha256'],
              'maximumChannelDifference':0,'allowedMaximum':0 if name in ('filtered-base','sticker-artwork') else 2,
              'channelMaximumsRGBA':[0]*4,'pixelsAboveTwo':0,'boundsAboveTwo':[480,640,-1,-1]})
        record={'schema':'Celluloid.MacOriginal2xProbe.1','scope':'synthetic-pre-host-only','controlFileSHA256':probe.sha(probe.control_bytes()),
          'controlSourceSHA':controls['sourceSHA'],'controlProfile':'2x','controlRuntime':'27.0','controlBuild':'24A434',
          'archiveSHA256':archive['sha256'],'controlArchiveSHA256':archive['sha256'],'sourcePNG_SHA256':source['sha256'],
          'actualPNG_SHA256':full['sha256'],'comparisons':rows,'layeredPhotosOutputQualified':False}
        return record,fixture
    def summary(self):
        return {'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0,
          'result':'Passed','testFailures':[],'runtimeWarnings':[],
          'devicesAndConfigurations':[{'device':{'platform':'macOS','architecture':'arm64'},'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0}]}
    def log(self,terminal='TEST EXECUTE'):
        lines=[]
        for case in probe.CASES:
            owner='CelluloidMacPhotosExtensionTests.'+case.replace('.',' ',1)
            lines += [f"Test Case '-[{owner}]' started.",f"Test Case '-[{owner}]' passed (0.001 seconds)."]
        return '\n'.join(lines+[f'** {terminal} SUCCEEDED **'])
    def test_good_fixture_retains_strict_contract(self):
        record,fixture=self.fixture();self.assertTrue(probe.validate_probe(record,fixture))
    def test_rejects_inflated_or_wrong_profile_limits(self):
        for key,value in [('controlProfile','3x'),('controlFileSHA256','0'*64),('layeredPhotosOutputQualified',True)]:
            record,fixture=self.fixture();record[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):probe.validate_probe(record,fixture)
        for field,value in [('allowedMaximum',3),('maximumChannelDifference',3),('channelMaximumsRGBA',[0,0,0,3]),
                            ('pixelsAboveTwo',1),('boundsAboveTwo',[0,0,0,0]),('actualPNG_SHA256','0'*64),('originalPNG_SHA256','0'*64)]:
            record,fixture=self.fixture();record['comparisons'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):probe.validate_probe(record,fixture)
    def test_base_and_sticker_must_be_exact(self):
        for index in [1,3]:
            record,fixture=self.fixture();record['comparisons'][index]['channelMaximumsRGBA']=[1,0,0,0]
            record['comparisons'][index]['maximumChannelDifference']=1
            with self.assertRaises(ValueError):probe.validate_probe(record,fixture)
    def test_rejects_missing_duplicate_or_reordered_components(self):
        for change in [lambda x:x.pop(),lambda x:x.append(x[0]),lambda x:x.reverse()]:
            record,fixture=self.fixture();change(record['comparisons'])
            with self.assertRaises(ValueError):probe.validate_probe(record,fixture)
    def test_rejects_unknown_fields_and_unbound_archive(self):
        record,fixture=self.fixture();record['extra']=False
        with self.assertRaises(ValueError):probe.validate_probe(record,fixture)
        record,fixture=self.fixture();record['archiveSHA256']='0'*64
        with self.assertRaises(ValueError):probe.validate_probe(record,fixture)
    def test_two_actual_passed_cases_and_both_terminal_forms(self):
        for terminal in ['TEST','TEST EXECUTE']:probe.validate_summary(self.summary(),self.log(terminal))
    def test_rejects_skips_warnings_failures_and_wrong_platform(self):
        for key,value in [('totalTestCount',43),('passedTests',1),('skippedTests',1),('runtimeWarnings',[{'message':'warning'}]),('result','Failed')]:
            summary=self.summary();summary[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):probe.validate_summary(summary,self.log())
        summary=self.summary();summary['devicesAndConfigurations'][0]['device']['platform']='iOS Simulator'
        with self.assertRaises(ValueError):probe.validate_summary(summary,self.log())
    def test_rejects_missing_duplicate_or_failed_raw_case(self):
        for log in [self.log()+'\n'+self.log(),self.log().replace(' passed (',' failed ('),self.log().replace('** TEST EXECUTE SUCCEEDED **',''),
                    self.log()+'\n** TEST FAILED **',self.log()+'\nPublishing changes from within view updates']:
            with self.assertRaises(ValueError):probe.validate_summary(self.summary(),log)
    def test_exact_single_parent_source_route(self):
        source='a'*40;environment={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':probe.BRANCH,'GITHUB_EVENT_NAME':'push',
            'GITHUB_WORKFLOW_SHA':source,'GITHUB_SHA':source}
        probe.admit_identity(source,[source,probe.BASE],probe.BASE_TREE,sorted(probe.ALLOWED),environment)
        for parent in [[source,'b'*40],[source,probe.BASE,'b'*40]]:
            with self.assertRaises(ValueError):probe.admit_identity(source,parent,probe.BASE_TREE,sorted(probe.ALLOWED),environment)
        with self.assertRaises(ValueError):probe.admit_identity(source,[source,probe.BASE],probe.BASE_TREE,[*probe.ALLOWED,'Platforms/macOSExtension/MacPhotoRenderer.swift'],environment)
        environment['GITHUB_EVENT_NAME']='workflow_dispatch'
        with self.assertRaises(ValueError):probe.admit_identity(source,[source,probe.BASE],probe.BASE_TREE,sorted(probe.ALLOWED),environment)
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):json.loads('{"a":1,"a":2}',object_pairs_hook=probe.unique)
if __name__=='__main__':unittest.main()
