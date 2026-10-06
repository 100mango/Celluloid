"""Fixed staged package route: source identity and original command preservation."""
import contextlib,hashlib,io,json,os,re,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import validation_route as route
import uikit_full_shipping_handoff as handoff
import original_ios_source_contract as projection
from test_native_workflow_syntax import run_blocks
from test_uikit_full_shipping_workflow import job,xcode_commands
ROOT=projection.ROOT

def environment():
    ref='refs/heads/'+route.ORIGINAL_IOS['branch'];source='a'*40
    return {'GITHUB_REPOSITORY':route.REPOSITORY,'GITHUB_EVENT_NAME':'push','GITHUB_REF':ref,
        'GITHUB_SHA':source,'GITHUB_WORKFLOW_SHA':source,'GITHUB_WORKFLOW_REF':route.REPOSITORY+'/'+route.ORIGINAL_IOS['workflow_path']+'@'+ref,
        'CELLULOID_VALIDATION_SCOPE':route.ORIGINAL_IOS['scope'],'GITHUB_RUN_ID':'1234567','GITHUB_RUN_ATTEMPT':'1'}

class OriginalIOSRouteTests(unittest.TestCase):
    def test_fixed_route_cannot_be_relabelled_or_given_historical_source(self):
        env=environment();old=dict(env)
        self.assertEqual(route.current_route(env),route.ORIGINAL_IOS);self.assertEqual(env,old)
        for key,value in [('GITHUB_REF','refs/heads/arbitrary'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REPOSITORY','other/Celluloid'),('GITHUB_WORKFLOW_SHA',route.ORIGINAL_IOS_BASE['commit']),('CELLULOID_VALIDATION_SCOPE','uikit-full-shipping'),('GITHUB_WORKFLOW_REF','arbitrary')]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(dict(env,**{key:value}))
        for key in env:
            if key in {'GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'}:continue
            value=dict(env);value.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):route.current_route(value)

    def test_archive_only_keeps_exact_native_archive_command_and_all_four_required_proofs(self):
        from staged_test_fixtures import qualified_staged_row_workflow
        from original_ios_fixed_rows import ARTIFACTS
        old=qualified_staged_row_workflow();new=(ROOT/route.ORIGINAL_IOS['workflow_path']).read_text()
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',new.split('jobs:\n',1)[1],re.M),['archive'])
        old_archive=job(old,'archive');archive=job(new,'archive')
        self.assertEqual(xcode_commands(archive),xcode_commands(old_archive))
        self.assertIn('timeout-minutes: 30',archive);self.assertIn("'execution_budget_seconds':1560",archive)
        self.assertIn('CODE_SIGNING_ALLOWED=NO',archive)
        self.assertIn('--fixed-archive-only-rows',archive)
        self.assertNotIn('needs:',archive);self.assertNotIn('workflow_dispatch',new)
        self.assertNotIn('exportArchive',archive);self.assertNotIn('cancel-in-progress: true',new)
        self.assertEqual(new.count('fetch-depth: 5'),1)
        self.assertEqual({str(v['artifact_id']) for v in ARTIFACTS.values()},set(re.findall(r'artifact-ids: ([0-9]+)',archive)))
        self.assertEqual(archive.count('repository: 100mango/Celluloid'),6)
        self.assertEqual(archive.count('run-id: 37432040947'),4)
        self.assertEqual(archive.count('run-id: 37441448096'),2)
        self.assertIn('python3 -m unittest -v test_original_ios_optional_process_contract',archive)
        self.assertLess(archive.index('Scripts/original_ios_rows.py'),archive.index('--label original-iOS-device-archive'))
        self.assertLess(archive.index('Scripts/original_ios_archive.py verify'),archive.index('--phase after'))
        self.assertLess(archive.index('--phase after'),archive.index('Scripts/original_ios_archive.py finalize'))

    def test_every_new_workflow_shell_block_parses(self):
        for line,body in run_blocks((ROOT/route.ORIGINAL_IOS['workflow_path']).read_text()):
            with self.subTest(line=line):
                result=subprocess.run(['bash','-n'],input=body,text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_staged_profile_requires_new_actual_source_and_original_feature_projection(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,environment(),clear=True):
            root=Path(folder);count,fingerprint=handoff.source_profile()
            self.assertEqual(count,546);self.assertNotEqual(fingerprint,handoff.UIKIT_FULL_BASE['fingerprint'])
            row={'source_sha':'a'*40,'file_count':count,'source_fingerprint':fingerprint,'validation_route':route.ORIGINAL_IOS,'phase':'before','tree':'b'*40,'original_ios_source':projection.audit()}
            path=root/'combined-source-before.json';path.write_text(json.dumps(row));self.assertEqual(handoff.source_proof(root),row)
            for key,value in [('source_sha',route.ORIGINAL_IOS_BASE['commit']),('file_count',547),('source_fingerprint',handoff.UIKIT_FULL_BASE['fingerprint']),('validation_route',route.UIKIT_FULL),('original_ios_source',{})]:
                path.write_text(json.dumps(dict(row,**{key:value})))
                with self.subTest(key=key),self.assertRaises(ValueError):handoff.source_proof(root)

    @unittest.skipUnless(__debug__,'Source executable guard is invoked under normal Python')
    def test_exact_parent_tree_delta_and_all_current_protected_bytes_are_bound(self):
        import verify_combined_source as guard
        contract=json.loads((ROOT/'Scripts/original-ios-source-contract.json').read_text())
        rows=contract['files'];self.assertEqual(len(rows),546)
        for name,digest in rows:self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        env=environment();base=route.ORIGINAL_IOS_BASE['commit'];prior=route.ORIGINAL_IOS_PREDECESSOR['commit'];qualified=route.ORIGINAL_IOS_QUALIFIED_PREDECESSOR['commit'];completed=route.ORIGINAL_IOS_ARCHIVE_PREDECESSOR['commit'];head=env['GITHUB_SHA']
        replies={('rev-parse','HEAD'):head,('status','--porcelain','--untracked-files=all'):'',
            ('ls-files','-z','--',*contract['roots']):'\0'.join(name for name,_ in rows)+'\0',
            ('ls-files','--','.github/release-controller'):'',('ls-files','--','.github/workflows/cloud-release.yml'):'',
            ('rev-parse','HEAD^{tree}'):'c'*40,('rev-list','--parents','-n','1','HEAD'):head+' '+completed,
            ('rev-list','--parents','-n','1',completed):completed+' '+qualified,
            ('rev-parse',completed+'^{tree}'):route.ORIGINAL_IOS_ARCHIVE_PREDECESSOR['tree'],
            ('diff','--name-only',completed,'HEAD'):'\n'.join(sorted(route.ORIGINAL_IOS_ARCHIVE_ONLY_PATHS)),
            ('rev-list','--parents','-n','1',qualified):qualified+' '+prior,
            ('rev-parse',qualified+'^{tree}'):route.ORIGINAL_IOS_QUALIFIED_PREDECESSOR['tree'],
            ('diff','--name-only',qualified,completed):'\n'.join(sorted(route.ORIGINAL_IOS_FIRST_SUMMARY_PATHS)),
            ('rev-list','--parents','-n','1',prior):prior+' '+base,
            ('rev-parse',prior+'^{tree}'):route.ORIGINAL_IOS_PREDECESSOR['tree'],
            ('rev-parse',base+'^{tree}'):route.ORIGINAL_IOS_BASE['tree'],
            ('diff','--name-only',base,prior):'\n'.join(sorted(route.ORIGINAL_IOS_PATHS)),
            ('diff','--name-only',prior,qualified):'\n'.join(sorted(route.ORIGINAL_IOS_REPAIR_PATHS))}
        actual_check_output=subprocess.check_output
        def call(command,**kwargs):
            if command[:2]==['git','show']:return actual_check_output(command,**kwargs)
            return replies[tuple(command[1:])]
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,dict(env,RUNNER_TEMP=folder),clear=True),patch.object(sys,'argv',['verify_combined_source.py','--phase','before']),patch.object(guard.subprocess,'check_output',side_effect=call),contextlib.redirect_stdout(io.StringIO()):
            guard.main();result=json.loads((Path(folder)/'combined-source-before.json').read_text())
            self.assertEqual(result['source_fingerprint'],contract['fingerprint']);self.assertFalse(result['original_ios_source']['source_equivalence'])
            self.assertTrue(result['original_ios_source']['original_features_preserved'])
            for key,value in [(('rev-list','--parents','-n','1','HEAD'),head+' '+'e'*40),(('rev-list','--parents','-n','1','HEAD'),head+' '+prior+' '+'e'*40),
                (('rev-list','--parents','-n','1',prior),prior+' '+'e'*40),
                (('rev-parse',prior+'^{tree}'),'e'*40),(('rev-parse',base+'^{tree}'),'e'*40),(('diff','--name-only',completed,'HEAD'),'\n'.join(sorted(route.ORIGINAL_IOS_ARCHIVE_ONLY_PATHS|{'CelluloidKit/Unexpected.swift'}))),(('rev-list','--parents','-n','1',completed),completed+' '+'e'*40),(('rev-parse',completed+'^{tree}'),'e'*40),(('rev-parse',qualified+'^{tree}'),'e'*40),(('rev-list','--parents','-n','1',qualified),qualified+' '+'e'*40)]:
                previous=replies[key];replies[key]=value
                with self.subTest(key=key),self.assertRaises(AssertionError):guard.main()
                replies[key]=previous

if __name__=='__main__':unittest.main()
