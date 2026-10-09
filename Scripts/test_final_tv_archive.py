"""Closed control and owned subprocess regressions; pure stdlib, no Apple tools."""
import ast
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import final_tv_archive as gate

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SHA = '128bf2765fe50538c7dfb9521442eb53b1ccf7f7a30d120abc0b3d783a231281'


def config(enabled=True):
    return {'schema': 1, 'enabled': enabled, 'scope': 'unsigned-package-diagnostic',
        'product': {'commit': gate.SOURCE, 'tree': gate.TREE, 'version': '1.1.1', 'build': '3'},
        'qualification': {key: False for key in ('release', 'signing', 'store', 'native_ui', 'ios_photos_host', 'mac')}}


def env():
    return {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': gate.BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + gate.WORKFLOW + '@' + gate.BRANCH,
        'GITHUB_JOB': 'archive', 'GITHUB_RUN_ATTEMPT': '1', 'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer',
        'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': 'a'*40, 'GITHUB_WORKFLOW_SHA': 'a'*40, 'GITHUB_RUN_ID': '123'}


def git_values():
    return {('control', 'rev-parse', 'HEAD'): 'a'*40,
        ('control', 'rev-list', '--parents', '-n', '1', 'HEAD'): 'a'*40 + ' ' + gate.SOURCE,
        ('control', 'rev-parse', gate.SOURCE + '^{tree}'): gate.TREE,
        ('control', 'diff', '--name-status', gate.SOURCE, 'HEAD', '--'): '\n'.join('A\t' + p for p in gate.NEW_PATHS),
        ('control', 'status', '--porcelain', '--untracked-files=all'): '',
        ('product', 'status', '--porcelain', '--untracked-files=all'): '',
        ('product', 'rev-parse', 'HEAD'): gate.SOURCE,
        ('product', 'rev-parse', 'HEAD^{tree}'): gate.TREE,
        ('control', 'rev-parse', 'HEAD^{tree}'): 'b'*40}


def clock(start=None):
    return {'schema': 'Celluloid.FinalTVArchiveClock.1', 'control_sha': 'a'*40,
        'run_id': '123', 'run_attempt': '1', 'started_monotonic': time.monotonic() if start is None else start,
        'started_unix': time.time(), 'execution_budget_seconds': 1560}


class AdmissionTests(unittest.TestCase):
    def test_closed_config_and_scope_are_exact(self):
        gate.validate_config(config(False), enabled=False)
        gate.validate_config(config())
        for key, value in [('enabled', False), ('schema', True), ('scope', 'release')]:
            item = config(); item[key] = value
            with self.assertRaises(ValueError): gate.validate_config(item)
        for key in config()['qualification']:
            item = config(); item['qualification'][key] = True
            with self.assertRaises(ValueError): gate.validate_config(item)
        for key in config()['product']:
            item = config(); item['product'][key] = 'wrong'
            with self.assertRaises(ValueError): gate.validate_config(item)

    def test_exact_distinct_control_and_product_admitted(self):
        values = git_values()
        proof = gate.admit_sources(config(), env(), lambda *args: values[args])
        self.assertEqual(proof['product_sha'], gate.SOURCE)
        self.assertNotEqual(proof['control_sha'], gate.SOURCE)

    def test_every_source_binding_rejects_mutation(self):
        for key in git_values():
            if key == ('control', 'rev-parse', 'HEAD^{tree}'): continue
            values = git_values(); values[key] += 'changed'
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.admit_sources(config(), env(), lambda *args: values[args])
        values = git_values(); values[('control','rev-list','--parents','-n','1','HEAD')] += ' ' + 'c'*40
        with self.assertRaises(ValueError): gate.admit_sources(config(), env(), lambda *args: values[args])

    def test_no_environment_rerun_route_or_workflow_substitution(self):
        for key in env():
            item = env(); item[key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.admit_sources(config(), item, lambda *args: git_values()[args])

    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"enabled":false,"enabled":true}', b'{"x":NaN}'):
            with self.assertRaises(ValueError): gate.strict_json(raw)

    def test_original_cell_clock_and_cleanup_reserve(self):
        self.assertEqual(gate.PHASES, {'setup':(300,300),'archive':(900,1200),'proof':(180,1380),'source':(60,1440),'retention':(60,1500),'upload':(60,1560)})
        value = clock(100)
        gate.validate_clock(value, env(), 101)
        self.assertEqual(gate.phase_deadline(value, 'archive', 450), 1300)
        for change in ({'execution_budget_seconds':1800}, {'run_attempt':'2'}, {'started_monotonic':float('nan')}):
            with self.assertRaises(ValueError): gate.validate_clock({**value, **change}, env(), 101)
        with self.assertRaises(ValueError): gate.phase_deadline(value,'archive',1301)
        with self.assertRaises(ValueError): gate.Commands().run([sys.executable],deadline=time.monotonic()+1,seconds=10)

    def test_safe_read_rejects_parent_alias_and_hardlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve(); folder=root/'safe'; folder.mkdir(); path=folder/'x'; path.write_bytes(b'ok')
            self.assertEqual(gate.safe_read(path,10),b'ok')
            (root/'alias').symlink_to(folder,target_is_directory=True)
            with self.assertRaises(OSError): gate.safe_read(root/'alias/x',10)
            os.link(path,folder/'hard')
            with self.assertRaises(ValueError): gate.safe_read(path,10)

    def test_exact_workflow_body_only_reviewed_activation(self):
        raw=(ROOT/gate.WORKFLOW).read_text()
        active="if: ${{ github.ref == 'refs/heads/celluloid-final-tv-archive-v2' && github.run_attempt == 1 }}"
        self.assertLessEqual(raw.count(active),1)
        normalized=raw.replace(active,'if: ${{ false }}')
        self.assertEqual(hashlib.sha256(normalized.encode()).hexdigest(),WORKFLOW_SHA)
        for old,new in [('timeout-minutes: 30','timeout-minutes: 31'),('runs-on: xcode-27','runs-on: macos-latest'),('CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_ALLOWED=YES')]:
            if old in normalized:
                self.assertNotEqual(hashlib.sha256(normalized.replace(old,new).encode()).hexdigest(),WORKFLOW_SHA)
        self.assertEqual(raw.count('runs-on:'),1)
        self.assertIn('python3 -B -S control/Scripts/final_tv_archive.py',raw)
        self.assertNotIn('workflow_dispatch:',raw)

    def test_tv_branch_has_one_unfiltered_active_workflow(self):
        # These exact product workflows use only simple literal push branches.
        # Reject a new route syntax instead of approximating GitHub glob/YAML rules.
        def literal_push_branches(raw):
            events=re.search(r"(?m)^(?:on|'on'|\"on\"):\n((?:[ \t].*\n|[ \t]*\n)*)",raw)
            self.assertIsNotNone(events,'missing explicit on mapping')
            push=re.search(r'(?ms)^  push:\n(.*?)(?=^  [^ \t-]|\Z)',events[1])
            self.assertIsNotNone(push,'missing explicit push mapping')
            lines=[line for line in push[1].splitlines() if line.strip()]
            if len(lines)==1:
                match=re.fullmatch(r'    branches: \[([A-Za-z0-9_/-]+)\]',lines[0])
                self.assertIsNotNone(match,'unexpected push filter, wildcard, or path restriction')
                return [match[1]]
            self.assertEqual(lines[0],'    branches:')
            values=[]
            for line in lines[1:]:
                match=re.fullmatch(r'    - ([A-Za-z0-9_/-]+)',line)
                self.assertIsNotNone(match,'unexpected push filter, wildcard, or path restriction')
                values.append(match[1])
            self.assertTrue(values)
            return values
        branch=gate.BRANCH.removeprefix('refs/heads/')
        workflows=sorted((ROOT/'.github/workflows').glob('*.yml'))
        matching=[p.relative_to(ROOT).as_posix() for p in workflows if branch in literal_push_branches(p.read_text())]
        self.assertEqual(len(workflows),10)
        self.assertEqual(matching,[gate.WORKFLOW])
        actual=(ROOT/gate.WORKFLOW).read_text()
        self.assertIn("if: ${{ github.ref == 'refs/heads/celluloid-final-tv-archive-v2' && github.run_attempt == 1 }}",actual)
        self.assertIs(json.loads((ROOT/gate.CONFIG).read_text())['enabled'],True)
        # Any changed subset, including either script alone, reaches this workflow:
        # its push has no paths/paths-ignore and is not restricted to the YAML file.
        for key in ('paths','paths-ignore'):
            restricted=actual.replace('    branches: [celluloid-final-tv-archive-v2]',
                '    branches: [celluloid-final-tv-archive-v2]\n    '+key+': [Scripts/not-this-change.py]')
            with self.assertRaises(AssertionError): literal_push_branches(restricted)

    def test_archive_command_reaches_actual_scheme_without_test_selectors(self):
        command=gate.ARCHIVE_COMMAND
        self.assertEqual(command[command.index('-scheme')+1],'CelluloidTV')
        self.assertEqual(command[command.index('-project')+1],'CelluloidNative.xcodeproj')
        self.assertEqual(command[command.index('-configuration')+1],'Release')
        self.assertEqual(command[command.index('-jobs')+1],'2')
        self.assertIn('CODE_SIGNING_ALLOWED=NO',command)
        self.assertIn('archive',command)
        self.assertFalse(any('only-testing' in value or value in ('test','-exportArchive') for value in command))

    def test_process_body_only_changes_output_ceiling(self):
        original=(ROOT/'Scripts/mac_owned_crash.py').read_text()
        expected=original[original.index('def bounded_optional_process('):original.index('\ndef framework_dependencies(')]
        actual=Path(gate.__file__).read_text()
        actual=actual[actual.index('def bounded_optional_process('):actual.index('\nclass Commands:')]
        self.assertEqual(ast.dump(ast.parse(actual)),ast.dump(ast.parse(expected.replace('0<cap<=8192','0<cap<=524288'))))

    def test_real_process_success_and_output_bound(self):
        start=time.monotonic()
        result=gate.bounded_optional_process([sys.executable,'-B','-S','-c','print("owned")'],start+3,start+4,cap=8192,stop_on_signal_error=True)
        self.assertTrue(result['finalized']);self.assertEqual(result['output'],b'owned\n')
        start=time.monotonic()
        result=gate.bounded_optional_process([sys.executable,'-B','-S','-c','print("x"*16384)'],start+3,start+4,cap=1024,stop_on_signal_error=True)
        self.assertTrue(result['overflow']);self.assertLessEqual(result['bytes_read'],1024)
        self.assertTrue(result['child_reaped'])

    def test_cleanup_uncertainty_stops_later_commands(self):
        response={'output':b'partial','finalized':False,'timed_out':True,'overflow':False,'return_code':None}
        runner=gate.Commands()
        with patch.object(gate,'bounded_optional_process',return_value=response) as call:
            for _ in range(2):
                with self.assertRaises(ValueError):runner.run(['fake'],deadline=time.monotonic()+20,seconds=10)
            self.assertEqual(call.call_count,1)

    def test_helper_exception_is_unknown_cleanup_and_blocks_next_call(self):
        for error in (KeyboardInterrupt(), RuntimeError('synthetic helper interruption')):
            runner=gate.Commands()
            with patch.object(gate,'bounded_optional_process',side_effect=error) as call:
                with self.assertRaises(type(error)):
                    runner.run(['fake'],deadline=time.monotonic()+20,seconds=10)
                self.assertTrue(runner.blocked)
                self.assertFalse(runner.events[-1]['finalized'])
                with self.assertRaises(ValueError):
                    runner.run(['fake'],deadline=time.monotonic()+20,seconds=10)
                self.assertEqual(call.call_count,1)

    def test_upload_needs_original_clock_and_never_release_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve(); e=env();e['GITHUB_OUTPUT']=str(root/'output')
            report={'schema':'Celluloid.FinalTVArchiveDiagnostic.1','control_sha':e['GITHUB_SHA'],'product_sha':gate.SOURCE,'product_tree':gate.TREE,
                'run_id':'123','run_attempt':'1','clock':clock(),'archive_qualified':False,'commands':[],
                **{key:False for key in ('release_qualified','signing_qualified','store_qualified','native_ui_qualified','ios_photos_host_qualified','mac_qualified','binary_handoff')}}
            path=gate.retain_report(report,e,root)
            gate.upload_gate('admit-upload',e,root)
            with self.assertRaises(ValueError):
                gate.upload_gate('admit-upload',{**e, 'GITHUB_REF':'refs/heads/wrong'},root)
            for key in ('release_qualified','signing_qualified','native_ui_qualified'):
                changed=copy.deepcopy(report);changed[key]=True;path.write_bytes(gate.encoded(changed))
                with self.assertRaises(ValueError):gate.upload_gate('admit-upload',e,root)
            report['clock']['started_monotonic']-=1500;path.write_bytes(gate.encoded(report))
            with self.assertRaises(ValueError):gate.upload_gate('admit-upload',e,root)

    def test_complete_synthetic_driver_reuses_one_real_command_and_no_ui(self):
        from types import SimpleNamespace
        called=[]
        class Commands:
            def __init__(self): self.events=[];self.blocked=False
            def run(self, argv, **kwargs):
                called.append((argv,kwargs))
                return b'Xcode 27.0\nBuild version 27A266a\n' if argv==['xcodebuild','-version'] else b''
        package={'unsigned_package_verified':True,'all_processes_finalized':True,'release_acceptance':False,'signing_qualified':False}
        checker=SimpleNamespace(source_graph=lambda root:{'archive':['Celluloid','CelluloidKit','CelluloidPhotoExtension']},verify_package=lambda root,deadline,commands:package)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();product=root/'product';product.mkdir();control=root/'control';control.mkdir()
            with patch.object(gate,'Commands',Commands),patch.object(gate,'source_binding',return_value={'bound':True}):
                result=gate.execute(env(),clock(),control=control,product=product,checker=checker)
        self.assertTrue(result['archive_qualified'])
        self.assertEqual(sum(argv==gate.ARCHIVE_COMMAND for argv,_ in called),1)
        archive=next(kwargs for argv,kwargs in called if argv==gate.ARCHIVE_COMMAND)
        self.assertEqual((archive['seconds'],archive['cleanup']),(900,10))
        self.assertEqual(sum('-S' in argv for argv,_ in called),8)
        self.assertIs(result['release_qualified'],False)
        self.assertIs(result['native_ui_qualified'],False)
        self.assertIs(result['ios_photos_host_qualified'],False)
        self.assertEqual(result['source_before'],result['source_after'])

    def test_archive_failure_cannot_become_qualification(self):
        e=env()
        with patch.object(gate,'source_binding',side_effect=ValueError('synthetic admission rejection')):
            result=gate.execute(e,clock())
        self.assertFalse(result['archive_qualified'])
        self.assertEqual(result['failure']['phase'],'setup')
        for key in ('release_qualified','signing_qualified','store_qualified','native_ui_qualified','ios_photos_host_qualified','mac_qualified'):
            self.assertIs(result[key],False)


if __name__=='__main__':
    unittest.main()
