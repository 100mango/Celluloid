"""Synthetic local archive diagnostic tests; never native commands or uploads."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tv_archive_diagnostics as diag
import tv_release_archive as archive
from test_tv_release_archive import ArchiveFixture, environment


class DiagnosticTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return ArchiveFixture(Path(temp.name))

    def test_inventory_is_complete_before_unknown_entry_rejects_and_never_reads_its_payload(self):
        f=self.fixture();p=f.archive/'Products/usr/local/lib/Unknown.a';p.parent.mkdir(parents=True)
        p.write_bytes(b'PRIVATE_UNEXPECTED_PAYLOAD')
        second=f.archive/'UnknownRoot.txt';second.write_bytes(b'PRIVATE_UNEXPECTED_PAYLOAD')
        result=diag.collect(f.archive,100,clock=lambda:0)
        rows={x['path']:x for x in result['inventory']['entries']}
        self.assertTrue(result['inventory']['complete'])
        self.assertEqual(rows['Products/usr/local/lib/Unknown.a']['size'],len(b'PRIVATE_UNEXPECTED_PAYLOAD'))
        self.assertEqual(rows['UnknownRoot.txt']['type'],'file')
        self.assertNotIn('PRIVATE_UNEXPECTED_PAYLOAD',json.dumps(result))
        self.assertFalse(result['inventory']['content_read'])
        with self.assertRaisesRegex(archive.Rejected,'unexpected-archive-entry') as caught:f.verify()
        offending=caught.exception.offending_entry
        self.assertIn(offending['path'],rows)
        self.assertEqual(offending,rows[offending['path']])
        self.assertEqual(f.calls,[])

    def test_unknown_or_allowed_symlink_targets_are_never_followed(self):
        f=self.fixture();outside=f.root/'external';outside.mkdir();(outside/'private.txt').write_text('PRIVATE_TARGET')
        (f.archive/'UnknownLink').symlink_to(outside,target_is_directory=True)
        (f.app/'Info.plist').unlink();(f.app/'Info.plist').symlink_to(outside/'private.txt')
        value=diag.collect(f.archive,100,clock=lambda:0)
        rows={x['path']:x for x in value['inventory']['entries']}
        self.assertEqual(rows['UnknownLink']['type'],'symlink')
        self.assertFalse(any(x.startswith('UnknownLink/') for x in rows))
        self.assertEqual(value['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')
        self.assertNotIn('PRIVATE_TARGET',json.dumps(value))
        with self.assertRaises(ValueError):diag.safe_read(f.archive,'UnknownLink/private.txt',100,clock=lambda:0)

    def test_fixed_pure_file_metadata_continues_despite_unknown_entries_and_metadata_mismatch(self):
        f=self.fixture();(f.archive/'Unknown').write_bytes(b'ignored')
        f.package.metadata['UIDeviceFamily']=[1,2];f.package.write_info()
        result=diag.collect(f.archive,100,clock=lambda:0)
        self.assertTrue(result['inventory']['complete'])
        facts=result['fixed_files']
        self.assertFalse(facts['qualifying']);self.assertFalse(facts['external_commands'])
        self.assertFalse(facts['app_metadata_comparisons']['UIDeviceFamily']['matches'])
        self.assertTrue(facts['app_metadata_comparisons']['CFBundleIdentifier']['matches'])
        self.assertEqual(facts['files'][diag.APP+'/CelluloidTV']['mach_header']['build'][0]['platform'],3)
        self.assertEqual(facts['files'][diag.DSYM+'/Contents/Info.plist']['status'],'observed')
        self.assertEqual(f.calls,[])

    def test_photos_add_usage_description_is_observed_without_a_diagnostic_gate(self):
        key='NSPhotoLibraryAddUsageDescription'
        for description in ('Save your finished Celluloid pictures to Photos.', 'different copy', None):
            f=self.fixture()
            if description is None:f.package.metadata.pop(key, None)
            else:f.package.metadata[key]=description
            f.package.write_info()
            result=diag.collect(f.archive,100,clock=lambda:0)
            facts=result['fixed_files'];observation=facts['files'][diag.APP+'/Info.plist']
            with self.subTest(description=description):
                self.assertEqual(observation['status'],'observed')
                self.assertEqual(observation['metadata'].get(key),description)
                self.assertEqual(key in observation['metadata'],description is not None)
                self.assertFalse(facts['qualifying']);self.assertFalse(facts['external_commands'])
                self.assertNotIn(key,facts['app_metadata_comparisons'])
                self.assertEqual(f.calls,[])

    def test_inventory_limits_keep_collected_entries_and_never_claim_completeness(self):
        f=self.fixture()
        with patch.object(diag,'MAX_ENTRIES',3):value=diag.inventory(f.archive,100,clock=lambda:0)
        self.assertEqual(len(value['entries']),3);self.assertFalse(value['complete'])
        self.assertEqual(value['failure']['reason'],'diagnostic-inventory-limit')
        value=diag.inventory(f.archive,0,clock=lambda:0)
        self.assertEqual(value['entries'],[]);self.assertFalse(value['complete'])
        self.assertEqual(value['failure']['reason'],'diagnostic-deadline')

    def test_hardlink_fifo_and_oversize_fixed_file_are_metadata_only(self):
        for kind in ('hardlink','fifo','oversize'):
            f=self.fixture();p=f.app/'Info.plist';p.unlink()
            if kind=='hardlink':os.link(f.app/'PrivacyInfo.xcprivacy',p)
            elif kind=='fifo':os.mkfifo(p)
            else:
                with p.open('wb') as stream:stream.truncate(diag.MAX_FILE_BYTES+1)
            result=diag.collect(f.archive,100,clock=lambda:0)
            with self.subTest(kind=kind):self.assertEqual(result['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')

    def test_diagnostic_malformed_plist_and_mach_headers_do_not_abort_other_fields(self):
        f=self.fixture();(f.app/'Info.plist').write_bytes(b'invalid');(f.app/'CelluloidTV').write_bytes(b'invalid')
        result=diag.collect(f.archive,100,clock=lambda:0)['fixed_files']['files']
        self.assertEqual(result[diag.APP+'/Info.plist']['status'],'unavailable')
        self.assertEqual(result[diag.APP+'/CelluloidTV']['status'],'unavailable')
        self.assertEqual(result[diag.APP+'/PrivacyInfo.xcprivacy']['status'],'observed')
        f=self.fixture();f.package.metadata['CFBundleVersion']=float('nan');f.package.write_info()
        value=diag.collect(f.archive,100,clock=lambda:0)
        self.assertEqual(value['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')
        json.dumps(value,allow_nan=False)

    def test_report_size_fallback_preserves_original_offending_entry_and_diagnostics(self):
        failure={'phase':'proof','type':'Rejected','reason':'unexpected-archive-entry','offending_entry':{'path':'Products/usr','type':'directory','size':96}}
        observation={'inventory':{'entries':[failure['offending_entry']],'complete':True},'fixed_files':{'qualifying':False}}
        value={'schema':1,'qualified':False,'signing_qualified':False,'store_qualified':False,
               'older_os_qualified':False,'ui_qualification_separate':True,'failure':failure,
               'archive_diagnostic':observation,'oversized':'x'*archive.MAX_REPORT}
        report=json.loads(archive.report_bytes(value))
        self.assertEqual(report['failure'],failure);self.assertEqual(report['archive_diagnostic'],observation)
        self.assertEqual(report['retention_failure']['reason'],'report-byte-limit')
        self.assertFalse(report['qualified'])

    @patch.object(archive.package, 'verify_generated_icons', return_value={'synthetic_icons':True})
    def test_execute_failure_keeps_all_safe_observations_without_external_validation_commands(self, _icons):
        f=self.fixture();(f.archive/'UnknownRoot').write_text('unknown');calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv==archive.ARCHIVE_COMMAND:shutil.copytree(f.archive,f.root/archive.ARCHIVE)
            data=(b'Xcode 27.0\nBuild version 27A266a\n' if argv==['xcodebuild','-version'] else b'appletvos27.0\n')
            return subprocess.CompletedProcess(argv,0,data,b'')
        with patch.object(archive,'source_identity',return_value={'source':'synthetic'}):
            result=archive.execute(env=environment(),root=f.root,clock=lambda:0,runner=run)
        self.assertFalse(result['qualified']);self.assertEqual(result['failure']['reason'],'unexpected-archive-entry')
        self.assertEqual(result['failure']['offending_entry']['path'],'UnknownRoot')
        self.assertTrue(result['archive_diagnostic']['inventory']['complete'])
        self.assertTrue(result['archive_diagnostic']['fixed_files']['app_metadata_comparisons']['CFBundleIdentifier']['matches'])
        self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)
        self.assertFalse(any(a[:2]==['xcrun','assetutil'] or a[:2]==['xcrun','dwarfdump'] for a in calls))

    @patch.object(archive.package, 'verify_generated_icons', return_value={'synthetic_icons':True})
    def execute_archive_observation(self, _icons, *, outcome='error-zero', materialize=True, observation=None):
        f=self.fixture();calls=[];tick=[0]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv==archive.ARCHIVE_COMMAND:
                if materialize:shutil.copytree(f.archive,f.root/archive.ARCHIVE)
                if outcome=='capture-stopped':raise archive.CaptureStopped('duration-limit',False)
                if outcome=='cancelled':raise archive.CaptureStopped('interrupted-by-signal-15',True,15)
                if outcome=='late':tick[0]=621
                text=b'error: the following command failed with exit code 0 but produced no further output\nSwiftCompile normal arm64 TVHistory.swift\n'
                if outcome=='success':text=b'warning: main actor-isolated byteBudget; this is an error in the Swift 6 language mode\n** ARCHIVE SUCCEEDED **\n'
                return subprocess.CompletedProcess(argv,1 if outcome=='nonzero' else 0,text,b'')
            if argv[:3] in (['xcrun','assetutil','--info'],['xcrun','dwarfdump','--uuid']):
                return subprocess.CompletedProcess(argv,0,f.run(argv),b'')
            text=b'Xcode 27.0\nBuild version 27A266a\n' if argv==['xcodebuild','-version'] else b'appletvos27.0\n'
            return subprocess.CompletedProcess(argv,0,text,b'')
        with patch.object(archive,'source_identity',return_value={'source':'synthetic'}):
            if observation is None:
                result=archive.execute(env=environment(),root=f.root,clock=lambda:tick[0],runner=run)
            else:
                with patch.object(diag,'collect',side_effect=observation):
                    result=archive.execute(env=environment(),root=f.root,clock=lambda:tick[0],runner=run)
        return f,result,calls

    def test_exit_zero_error_observes_existing_archive_without_native_validation_or_retry(self):
        f,result,calls=self.execute_archive_observation()
        self.assertEqual(result['failure'],{'phase':'archive','type':'Rejected','reason':'archive-reported-error'})
        self.assertFalse(result['qualified']);self.assertNotIn('proof',result)
        value=result['archive_diagnostic'];self.assertTrue(value['inventory']['complete'])
        self.assertFalse(value['fixed_files']['qualifying'])
        files=value['fixed_files']['files']
        self.assertEqual(files[diag.APP+'/Info.plist']['metadata']['CFBundleIdentifier'],'Mango.Celluloid')
        self.assertEqual(files[diag.APP+'/CelluloidTV']['mach_header']['kind'],2)
        self.assertEqual(files[diag.APP+'/CelluloidTV']['mach_header']['build'][0]['platform'],3)
        app_paths={x['path'][len(diag.APP)+1:] for x in value['inventory']['entries'] if x['type']=='file' and x['path'].startswith(diag.APP+'/')}
        self.assertEqual(app_paths,archive.APP_FILES)
        self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)
        self.assertFalse(any(c[:2] in (['xcrun','assetutil'],['xcrun','dwarfdump']) for c in calls))
        self.assertNotIn('-quiet',archive.ARCHIVE_COMMAND)

    def test_exit_zero_error_missing_archive_keeps_original_failure_and_safe_missing_paths(self):
        _,result,calls=self.execute_archive_observation(materialize=False)
        self.assertEqual(result['failure']['reason'],'archive-reported-error')
        observation=result['archive_diagnostic']
        self.assertFalse(observation['inventory']['complete'])
        self.assertIn('failure',observation['inventory'])
        self.assertEqual(observation['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')
        self.assertFalse(result['qualified']);self.assertNotIn('proof',result)
        self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)

    def test_failure_observation_requires_timely_zero_exit_and_confirmed_host_return(self):
        for outcome in ('nonzero','capture-stopped','cancelled','late'):
            observer=[]
            def observe(*args,**kwargs):observer.append(args);return {}
            _,result,calls=self.execute_archive_observation(outcome=outcome,observation=observe)
            with self.subTest(outcome=outcome):
                self.assertFalse(result['qualified']);self.assertNotIn('archive_diagnostic',result)
                self.assertEqual(observer,[]);self.assertNotIn('proof',result)
                self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)

    def test_failure_file_observation_uses_existing_twenty_second_limit_and_original_clock(self):
        seen=[]
        def observe(path,deadline,**kwargs):
            seen.append(deadline);return {'qualifying':False,'observed':True}
        _,result,_=self.execute_archive_observation(observation=observe)
        self.assertEqual(seen,[20])
        self.assertEqual(result['clock']['phase_end_seconds'],archive.PHASE_END)
        self.assertEqual(archive.PHASE_END['finalization'],1020)
        self.assertEqual(result['failure']['reason'],'archive-reported-error')
        self.assertFalse(result['qualified'])
        def broken(*args,**kwargs):raise ValueError('synthetic observation failure')
        _,result,_=self.execute_archive_observation(observation=broken)
        self.assertEqual(result['failure']['reason'],'archive-reported-error')
        self.assertEqual(result['archive_diagnostic']['failure']['reason'],'synthetic observation failure')
        self.assertFalse(result['qualified'])

    def test_normal_archive_without_error_still_uses_full_original_qualification(self):
        _,result,calls=self.execute_archive_observation(outcome='success')
        self.assertTrue(result['qualified']);self.assertIn('proof',result)
        self.assertNotIn('failure',result)
        self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)
        self.assertEqual(sum(c[:2]==['xcrun','assetutil'] for c in calls),1)
        self.assertEqual(sum(c[:2]==['xcrun','dwarfdump'] for c in calls),1)

    def test_root_symlink_and_unlisted_reads_reject_without_traversal(self):
        f=self.fixture();link=f.root/'alias';link.symlink_to(f.archive,target_is_directory=True)
        result=diag.inventory(link,100,clock=lambda:0)
        self.assertFalse(result['complete']);self.assertEqual(result['entries'],[])
        with self.assertRaises(ValueError):diag.safe_read(f.archive,'../outside',100,clock=lambda:0)


if __name__=='__main__':unittest.main()
