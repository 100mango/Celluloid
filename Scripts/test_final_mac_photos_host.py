"""Portable current-source admission and unchanged strict-host replay tests."""
import ast,copy,hashlib,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
import final_mac_photos_route as route
import final_mac_photos_source as source
import final_mac_photos_gate as gate
import final_mac_photos_transport as transport
import final_mac_photos_lifecycle as lifecycle
ROOT=Path(__file__).resolve().parents[1]
def environment():
 return {'GITHUB_REPOSITORY':route.REPOSITORY,'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+route.HOST_ONLY['branch'],
  'CELLULOID_VALIDATION_SCOPE':route.HOST_ONLY['scope'],'GITHUB_WORKFLOW_REF':route.REPOSITORY+'/'+route.HOST_ONLY['workflow_path']+'@refs/heads/'+route.HOST_ONLY['branch'],
  'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
def functions(text):return {n.name:ast.dump(n) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
class FinalHostTests(unittest.TestCase):
 def test_route_rejects_wrong_source_branch_event_scope_and_workflow(self):
  e=environment();self.assertEqual(route.current_route(e),route.HOST_ONLY)
  for key in e:
   if key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):continue
   bad=dict(e);bad[key]='wrong'
   with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(bad)
  with self.assertRaises(ValueError):route.validate_route(dict(route.HOST_ONLY,diagnostic_only=1))
 def test_clock_is_exact_original_bounded_host_profile(self):
  p=route.host_clock_profile(route.HOST_ONLY);self.assertEqual([p[k] for k in ('case_seconds','test_seconds','process_seconds')],[900,960,1020])
  self.assertEqual(p['step_seconds'],p['pretest_seconds']+p['process_seconds']+p['tail_seconds']+p['step_margin_seconds'])
  self.assertEqual(p['before_prepare_seconds'],p['step_seconds']+300)
  for key in p:
   c={'validation_route':dict(route.HOST_ONLY),'host_clock_profile':dict(p)};c['host_clock_profile'][key]=True
   with self.subTest(key=key),self.assertRaises(ValueError):route.context_clock(c)
 def test_closed_controls_and_duplicate_json_fail_closed(self):
  c=source.strict_json((ROOT/source.CONFIG).read_bytes());source.validate_config(c,enabled=c['enabled']);c['enabled']=False
  with self.assertRaises(ValueError):source.validate_config(c)
  for raw in ('{"enabled":false,"enabled":true}','{"value":NaN}'):
   with self.assertRaises(ValueError):source.strict_json(raw)
 def test_full_current_product_graph_and_host_membership(self):
  c=source.snapshot();self.assertEqual(len(c['files']),962)
  result=route.host_only_source_binding(c['files']);self.assertTrue(result['layered_guard_unchanged']);self.assertFalse(result['release_qualified'])
  p='Platforms/UITests/MacPhotosHostUITests.swift';self.assertEqual(dict(c['files'])[p],hashlib.sha256((ROOT/p).read_bytes()).hexdigest())
  pbx=(ROOT/'CelluloidNative.xcodeproj/project.pbxproj').read_text();self.assertIn('MacPhotosHostUITests.swift',pbx)
  for changed in (c['files'][:-1],c['files']+[c['files'][0]],list(reversed(c['files']))):
   with self.assertRaises(ValueError):route.host_only_source_binding(changed)
 def test_product_bytes_modes_alias_and_membership_cannot_change(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td).resolve();c=source.load_contract()
   for rel in [source.CONTRACT]+[p for p,_ in c['files']]:
    target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
   source.snapshot(root)
   p=root/'Platforms/macOSExtension/MacPhotoSession.swift';raw=p.read_bytes();p.write_bytes(raw+b'\n')
   with self.assertRaises(ValueError):source.snapshot(root)
   p.write_bytes(raw);p.chmod(0o755)
   with self.assertRaises(ValueError):source.snapshot(root)
   p.chmod(0o644);p.unlink();p.symlink_to(ROOT/'Platforms/macOSExtension/MacPhotoSession.swift')
   with self.assertRaises(ValueError):source.snapshot(root)
 def test_exact_parent_actual_tree_inventory_and_clean_checkout(self):
  c=source.load_contract();e=environment()
  values={('rev-parse','HEAD'):e['GITHUB_SHA'],('cat-file','-p','HEAD'):'tree '+'b'*40+'\nparent '+source.BASE+'\nauthor Fixture <fixture@example.invalid> 1 +0000\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\nSynthetic fixture.',
   ('rev-parse',source.BASE+'^{tree}'):source.TREE,('status','--porcelain','--untracked-files=all'):'',
   ('diff','--name-status',source.BASE,'HEAD','--'):'\n'.join('A\t'+p for p in source.ADDITIONS),
   ('-c','core.quotepath=false','ls-tree','-r',source.BASE):'\n'.join(f'{m} blob {b}\t{p}' for p,m,b in c['git_files']),
   ('-c','core.quotepath=false','ls-files'):'\n'.join(sorted({p for p,_ in c['files']}|source.ADDITIONS)),('rev-parse','HEAD^{tree}'):'b'*40}
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/source.CONFIG).parent.mkdir(parents=True);config=source.strict_json((ROOT/source.CONFIG).read_bytes());config['enabled']=True;(root/source.CONFIG).write_text(json.dumps(config))
   wf=root/route.HOST_ONLY['workflow_path'];wf.parent.mkdir(parents=True);wf.write_bytes((ROOT/route.HOST_ONLY['workflow_path']).read_bytes())
   with mock.patch.object(source,'snapshot',return_value=c):
    _,proof=source.admit_sources(e,lambda *a:values[a],root);self.assertEqual(proof['base_sha'],source.BASE)
    for key in values:
     if key==('rev-parse','HEAD^{tree}'):continue
     bad=dict(values)
     if key==('cat-file','-p','HEAD'):bad[key]=bad[key].replace('parent '+source.BASE,'parent '+'c'*40)
     else:bad[key]+=' changed'
     with self.subTest(key=key),self.assertRaises(ValueError):source.admit_sources(e,lambda *a:bad[a],root)
    for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
     bad=dict(e);bad[key]='2' if key=='GITHUB_RUN_ATTEMPT' else 'x'
     with self.assertRaises(ValueError):source.admit_sources(bad,lambda *a:values[a],root)
 def test_raw_commit_parent_headers_reject_zero_two_wrong_and_malformed(self):
  def raw(parents):return 'tree '+'b'*40+'\n'+''.join('parent '+p+'\n' for p in parents)+'author Fixture <fixture@example.invalid> 1 +0000\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\nMessage with parent '+source.BASE
  self.assertEqual(source.commit_parents(raw([source.BASE])),[source.BASE])
  for parents in ([],[source.BASE,source.BASE],['c'*40]):self.assertNotEqual(source.commit_parents(raw(parents)),[source.BASE])
  for value in ('not a commit',raw(['invalid']),raw([source.BASE]).replace('parent '+source.BASE,'parentx '+source.BASE,1)):
   with self.assertRaises(ValueError):source.commit_parents(value)
 def test_transport_and_lifecycle_only_change_route_import(self):
  for old,new in [('mac_host_transport.py','final_mac_photos_transport.py'),('mac_host_lifecycle.py','final_mac_photos_lifecycle.py')]:
   expected=(ROOT/'Scripts'/old).read_text().replace('from validation_route import context_clock','from final_mac_photos_route import context_clock')
   self.assertEqual((ROOT/'Scripts'/new).read_text(),expected)
 def test_all_host_product_ui_pixel_and_acceptance_functions_are_preserved(self):
  original=(ROOT/'Scripts/mac_photos_host_gate.py').read_text();rebound=(ROOT/'Scripts/final_mac_photos_gate.py').read_text()
  normalized=rebound.replace('from final_mac_photos_transport import','from mac_host_transport import').replace("ROOT/'.github/final-mac-photos-product.json'","ROOT/'Scripts/combined-source-contract.json'")
  a=functions(original);b=functions(normalized);a.pop('verify_source')
  self.assertEqual(a,b)
  self.assertEqual(gate.CAP,1_000_000);self.assertEqual(gate.EXPECTED_CASE,('CelluloidMacUITests.MacPhotosHostUITests','testInstalledExtensionIsInvokedByActualPhotos'))
 def test_native_argv_and_entitlements_do_not_expand(self):
  old=(ROOT/'Scripts/run_mac_photos_host_gate.sh').read_text();new=(ROOT/'Scripts/run_final_mac_photos_host.sh').read_text()
  expected=old.replace('Scripts/mac_photos_host_gate.py','Scripts/final_mac_photos_gate.py').replace('refs/heads/photos-export-observation','refs/heads/celluloid-final-mac-photos-host-v2')
  self.assertEqual(new,expected)
  wf=(ROOT/route.HOST_ONLY['workflow_path']).read_text()
  for forbidden in ('tccutil','sqlite3','pluginkit','security import','allowProvisioningUpdates','owned_saved_pixel_observation','CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE','owned_reverted_profile_observation','permissions: write'):
   self.assertNotIn(forbidden,wf)
  active="if: ${{ github.ref == 'refs/heads/celluloid-final-mac-photos-host-v2' && github.run_attempt == 1 }}"
  normalized=wf.replace(active,'if: ${{ false }}');self.assertIn('if: ${{ false }}',normalized);self.assertEqual(wf.count('runs-on: xcode-27'),1)
  self.assertEqual(hashlib.sha256(normalized.encode()).hexdigest(),'3dc3c71c7455c43cd18473aeceae96f5c09c97eb36986ef33877e40094571c11')
  self.assertIn('timeout-minutes: 45',wf);self.assertIn('timeout-minutes: 28',wf);self.assertIn('retention-days: 1',wf)
  self.assertIn('cancel-in-progress: false',wf)
 def test_shell_blocks_parse(self):
  from test_native_workflow_syntax import run_blocks
  for _,body in run_blocks((ROOT/route.HOST_ONLY['workflow_path']).read_text()):
   p=subprocess.run(['bash','-n'],input=body,text=True,capture_output=True,timeout=5);self.assertEqual(p.returncode,0,p.stderr)
 def packet(self):
  from test_mac_host_lifecycle import fixture
  args=list(fixture());args[1]['validation_route']=dict(route.HOST_ONLY);args[1]['host_clock_profile']=route.host_clock_profile(route.HOST_ONLY);args[0]['deadline_seconds']=900
  return args
 def test_actual_filter_replay_can_accept_complete_synthetic_proof_only(self):
  result=lifecycle.validate(*self.packet());self.assertTrue(result['filter_lifecycle_accepted']);self.assertFalse(result['complete_host_e2e']);self.assertFalse(result['dirty_cancel_tested'])
 def test_incomplete_changed_pixels_dirty_cancel_and_stale_generation_reject(self):
  mutations=[lambda a:a[0].update(complete=False),lambda a:a[0].update(dirty_cancel_tested=True),lambda a:a[0]['phases'].pop(),lambda a:a[0]['phases'][2]['details'].update(max_channel_delta=3),lambda a:a[0]['images']['lifecycle-saved.png'].update(sha256='0'*64),lambda a:a[0].update(deadline_seconds=1200),lambda a:a[0]['phases'][3]['details'].update(filter='Original')]
  for i,m in enumerate(mutations):
   a=self.packet();m(a)
   with self.subTest(i=i),self.assertRaises((ValueError,KeyError,TypeError)):lifecycle.validate(*a)
 def test_optimized_native_gate_refuses_before_action(self):
  for name in ('final_mac_photos_gate.py','final_mac_photos_source.py'):
   result=subprocess.run([sys.executable,'-B','-O','-S',str(ROOT/'Scripts'/name),'admit'],capture_output=True,text=True,timeout=10)
   self.assertNotEqual(result.returncode,0);self.assertIn('optimized Python',result.stderr)
if __name__=='__main__':unittest.main()
