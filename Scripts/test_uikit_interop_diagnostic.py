"""Local-only admission tests for the exact fixed UIKit diagnostic driver delta."""
import hashlib,json,os,re,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import validation_route as route
from test_native_workflow_syntax import run_blocks

ROOT=Path(__file__).resolve().parents[1]
CANONICAL='40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91'
MAC_REPAIR='20b2fa6763be3b0014fb598a68088d9927c65790f30904cc04061a902b751daa'


def environment():
    return {'GITHUB_REF':'refs/heads/'+route.UIKIT['branch'],'GITHUB_REPOSITORY':route.REPOSITORY,
        'GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':route.UIKIT['scope'],
        'GITHUB_WORKFLOW_REF':route.REPOSITORY+'/'+route.UIKIT['workflow_path']+'@refs/heads/'+route.UIKIT['branch'],
        'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40}


class DiagnosticRouteTests(unittest.TestCase):
    def test_exact_route_preserves_real_driver_identity(self):
        env=environment();before=dict(env)
        self.assertEqual(route.current_route(env),route.UIKIT)
        self.assertEqual(env,before)
        self.assertTrue(route.validate_route(route.UIKIT)['diagnostic_only'])

    def test_wrong_branch_event_repository_scope_workflow_or_source_rejects(self):
        env=environment()
        for key,value in [('GITHUB_REF','refs/heads/arbitrary'),('GITHUB_REPOSITORY','someone/Celluloid'),
                          ('GITHUB_EVENT_NAME','workflow_dispatch'),('CELLULOID_VALIDATION_SCOPE','mac-repair'),
                          ('GITHUB_WORKFLOW_REF',route.REPOSITORY+'/'+route.FOCUSED['workflow_path']+'@'+env['GITHUB_REF']),
                          ('GITHUB_WORKFLOW_SHA',route.QUALIFIED_SOURCE_SHA),('GITHUB_SHA','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(dict(env,**{key:value}))
        for key in env:
            candidate=dict(env);candidate.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):route.current_route(candidate)

    def test_canonical_and_focused_routes_and_workflow_bytes_stay_frozen(self):
        from test_validation_route import focused_environment
        self.assertEqual(route.current_route(focused_environment()),route.FOCUSED)
        self.assertEqual(route.current_route(dict(environment(),GITHUB_REF='refs/heads/'+route.FULL['branch'])),route.FULL)
        for path,digest in [(route.FULL['workflow_path'],CANONICAL),(route.FOCUSED['workflow_path'],MAC_REPAIR)]:
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)

    def test_one_fixed_job_under_existing_cap_without_other_native_routes(self):
        source=(ROOT/route.UIKIT['workflow_path']).read_text()
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',source.split('jobs:\n',1)[1],re.M),['fixed-uikit-interop'])
        self.assertIn('branches: [codex/uikit-interop-diagnostic]',source)
        self.assertIn('group: celluloid-platforms-refs/heads/codex/apple-platforms',source)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count('runs-on: xcode-27'),1)
        self.assertEqual(source.count('timeout-minutes: 45'),1)
        self.assertEqual(source.count('timeout-minutes: 20'),1)
        self.assertEqual(source.count('retention-days: 1'),1)
        self.assertIn('fetch-depth: 3',source)
        self.assertIn('ref: ${{ github.sha }}',source)
        self.assertIn("'execution_budget_seconds':41*60",source)
        self.assertIn('CELLULOID_EVIDENCE_PLATFORM: mac',source)
        for forbidden in ['strategy:', 'matrix:', 'needs:', 'workflow_dispatch:', 'run_combined_preflight.py',
                          'swift test', 'mac_photos_host_gate.py', 'run_native_', 'archive:', 'CODE_SIGNING_ALLOWED=YES',
                          'continue-on-error:', 'GITHUB_SHA=', 'GITHUB_WORKFLOW_SHA=', 'simctl privacy', 'simctl addmedia']:
            self.assertNotIn(forbidden,source)

    def test_producer_and_both_original_consumers_keep_unmodified_commands(self):
        source=(ROOT/route.UIKIT['workflow_path']).read_text()
        commands=["xcodebuild -project CelluloidNative.xcodeproj -scheme CelluloidMac -destination 'platform=macOS'",
                  'verify_required_interoperability.py mac --platform-contract',
                  'python3 Scripts/run_early_uikit_interop.py',
                  'python3 Scripts/verify_interop_continuation.py --github-output "$GITHUB_OUTPUT"']
        positions=[source.index(value) for value in commands];self.assertEqual(positions,sorted(positions))
        self.assertIn('steps.native_tests.outcome == \'success\'',source)
        self.assertIn('steps.mac_producer.outcome == \'success\'',source)
        self.assertIn('steps.consumer_admission.outcome == \'success\'',source)
        self.assertEqual(source.count('python3 Scripts/verify_combined_source.py --phase before'),2)
        self.assertIn('python3 Scripts/verify_combined_source.py --phase after',source)
        self.assertIn('python3 Scripts/collect_native_evidence.py',source)
        from verify_required_interoperability import required
        self.assertEqual(sum(map(len,required('mac').values())),42)
        from run_early_uikit_interop import ACTIVE_SECONDS,PROFILES,FROZEN_UIKIT_FINGERPRINT,frozen_uikit_fingerprint
        self.assertEqual(ACTIVE_SECONDS,18*60)
        self.assertEqual(PROFILES,[('2x','iPhone SE (3rd generation)',2.0),('3x','iPhone 18 Pro Max',3.0)])
        self.assertEqual(frozen_uikit_fingerprint(),FROZEN_UIKIT_FINGERPRINT)
        from combined_evidence_budget import BUDGETS,WHOLE_RUN
        self.assertEqual(BUDGETS['mac'],2_000_000);self.assertEqual(WHOLE_RUN,20_000_000)

    def test_every_new_workflow_shell_block_parses(self):
        blocks=list(run_blocks((ROOT/route.UIKIT['workflow_path']).read_text()));self.assertEqual(len(blocks),9)
        for line,body in blocks:
            with self.subTest(line=line):
                result=subprocess.run(['bash','-n'],input=body,text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)


class QualifiedSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.git('init','-q');self.git('config','user.name','Local Diagnostic Test');self.git('config','user.email','local@example.invalid')
        for path in ['Celluloid/product.swift','CelluloidTests/consumer.swift','controls.json',route.FULL['workflow_path'],route.FOCUSED['workflow_path']]:self.write(path,'protected original\n')
        for path in ['Scripts/validation_route.py','Scripts/verify_combined_source.py',*route.PARSER_REPAIR_PATHS]:self.write(path,'original source\n')
        self.commit('base');self.base=self.git('rev-parse','HEAD');self.tree=self.git('rev-parse','HEAD^{tree}')
        for path in route.ORIGINAL_DRIVER_PATHS:self.write(path,'first admitted driver '+path+'\n')
        self.commit('previous driver');self.previous=self.git('rev-parse','HEAD');self.previous_tree=self.git('rev-parse','HEAD^{tree}')
        for path in route.SUCCESSOR_PATHS:self.write(path,'exact parser successor '+path+'\n')
        self.commit('driver');self.driver=self.git('rev-parse','HEAD')
        self.addCleanup(patch.stopall)
        # Synthetic repository identities for local mutation testing only.
        patch.object(route,'QUALIFIED_SOURCE_SHA',self.base).start();patch.object(route,'QUALIFIED_SOURCE_TREE',self.tree).start()
        patch.object(route,'PREVIOUS_DRIVER_SHA',self.previous).start();patch.object(route,'PREVIOUS_DRIVER_TREE',self.previous_tree).start()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.root,text=True,stderr=subprocess.PIPE,timeout=10).strip()
    def write(self,path,value):
        target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value)
    def commit(self,message):self.git('add','-A');self.git('commit','-qm',message)
    def amend(self):self.git('add','-A');self.git('commit','--amend','--no-edit','-q');self.driver=self.git('rev-parse','HEAD')
    def verify(self):return route.qualified_uikit_source(self.root,self.driver)

    def test_exact_direct_successor_reports_separate_qualified_and_driver_identities(self):
        result=self.verify()
        self.assertEqual(result['driver_commit'],self.driver);self.assertEqual(result['qualified_source_commit'],self.base)
        self.assertNotEqual(result['driver_commit'],result['qualified_source_commit'])
        self.assertEqual(result['previous_driver_commit'],self.previous)
        self.assertEqual(result['previous_driver_tree'],self.previous_tree)
        self.assertEqual(set(result['repair_files']),route.SUCCESSOR_PATHS)
        self.assertEqual(result['qualified_source_tree'],self.tree)
        self.assertEqual({row['path'] for row in result['driver_files']},route.DRIVER_ONLY_PATHS)
        self.assertFalse(result['full_release_accepted']);self.assertTrue(result['diagnostic_only'])

    def test_wrong_driver_or_qualified_tree_rejects(self):
        with self.assertRaisesRegex(ValueError,'driver checkout'):route.qualified_uikit_source(self.root,self.base)
        with patch.object(route,'QUALIFIED_SOURCE_TREE','b'*40),self.assertRaisesRegex(ValueError,'tree changed'):self.verify()

    def test_wrong_previous_tree_or_parent_rejects(self):
        with patch.object(route,'PREVIOUS_DRIVER_TREE','b'*40),self.assertRaisesRegex(ValueError,'driver tree changed'):self.verify()
        with patch.object(route,'QUALIFIED_SOURCE_SHA',self.previous),self.assertRaisesRegex(ValueError,'sole qualified8470 parent'):self.verify()

    def test_previous_only_unchanged_file_cannot_change_in_successor(self):
        self.write('Scripts/verify_combined_source.py','unadmitted successor change\n');self.amend()
        with self.assertRaisesRegex(ValueError,'five-file parser successor'):self.verify()

    def test_missing_parser_successor_delta_rejects(self):
        self.git('checkout',self.previous,'--','Scripts/consumer_runtime_binding.py');self.amend()
        with self.assertRaisesRegex(ValueError,'outside'):self.verify()

    def test_fake8470_execution_identity_rejects(self):
        with self.assertRaisesRegex(ValueError,'driver checkout'):route.qualified_uikit_source(self.root,self.base)

    def test_product_consumer_control_and_existing_workflow_changes_reject(self):
        for path in ['Celluloid/product.swift','CelluloidTests/consumer.swift','controls.json',route.FULL['workflow_path'],route.FOCUSED['workflow_path']]:
            with self.subTest(path=path):
                self.write(path,'unauthorized change\n');self.amend()
                with self.assertRaisesRegex(ValueError,'outside'):self.verify()
                self.git('checkout',self.base,'--',path);self.amend()

    def test_new_source_or_removed_protected_member_rejects(self):
        self.write('Platforms/new-lifecycle.swift','unadmitted lifecycle\n');self.amend()
        with self.assertRaisesRegex(ValueError,'outside'):self.verify()
        (self.root/'Platforms/new-lifecycle.swift').unlink();(self.root/'controls.json').unlink();self.amend()
        with self.assertRaisesRegex(ValueError,'outside'):self.verify()

    def test_missing_required_driver_delta_rejects(self):
        self.git('checkout',self.base,'--','Scripts/validation_route.py');self.amend()
        with self.assertRaisesRegex(ValueError,'outside'):self.verify()

    def test_driver_mode_change_rejects(self):
        (self.root/'Scripts/validation_route.py').chmod(0o755);self.amend()
        with self.assertRaisesRegex(ValueError,'type/mode'):self.verify()

    def test_dirty_or_untracked_source_rejects(self):
        self.write('Celluloid/product.swift','dirty\n')
        with self.assertRaisesRegex(ValueError,'Dirty'):self.verify()
        self.git('checkout','HEAD','--','Celluloid/product.swift');self.write('extra-file','unexpected\n')
        with self.assertRaisesRegex(ValueError,'Dirty'):self.verify()

    def test_second_successor_is_not_the_admitted_parent(self):
        self.git('commit','--allow-empty','-qm','extra successor');self.driver=self.git('rev-parse','HEAD')
        with self.assertRaisesRegex(ValueError,'direct single-parent'):self.verify()


class BudgetTests(unittest.TestCase):
    SOURCE='a'*40
    def clock(self):return {'source_sha':self.SOURCE,'started_monotonic':100.,'started_unix':1_700_000_000.,'execution_budget_seconds':41*60}
    def test_exact_boundary_admits_and_one_second_late_blocks(self):
        for phase,required in [('before',27*60),('after',4*60)]:
            now=100+41*60-required
            self.assertEqual(route.uikit_diagnostic_budget(self.clock(),self.SOURCE,phase,now)['remaining_seconds'],required)
            with self.assertRaisesRegex(ValueError,'Insufficient'):route.uikit_diagnostic_budget(self.clock(),self.SOURCE,phase,now+1)
    def test_wrong_source_cap_nonfinite_or_backwards_clock_blocks(self):
        for key,value in [('source_sha','b'*40),('execution_budget_seconds',45*60),('execution_budget_seconds',2460.),
                          ('started_monotonic',float('nan')),('started_monotonic',True),('started_unix',0)]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.uikit_diagnostic_budget(dict(self.clock(),**{key:value}),self.SOURCE,'before',100)
        for now in [0,99,float('nan'),float('inf'),True]:
            with self.subTest(now=now),self.assertRaises(ValueError):route.uikit_diagnostic_budget(self.clock(),self.SOURCE,'before',now)
    def test_invalid_phase_rejects(self):
        with self.assertRaises(ValueError):route.uikit_diagnostic_budget(self.clock(),self.SOURCE,'continue',100)


if __name__=='__main__':unittest.main()
