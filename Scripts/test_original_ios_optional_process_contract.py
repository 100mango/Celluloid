"""Real owned child calls catch metadata/observer/helper interface mismatches."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import mac_owned_crash as process
import original_ios_archive as archive
import original_ios_fixed_rows as fixed
from test_original_ios_route import environment


class OptionalProcessContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / 'bin'; self.bin.mkdir()
        env = environment(); env.update(RUNNER_TEMP=str(self.root),
                                       PATH=str(self.bin)+os.pathsep+os.environ.get('PATH', os.defpath))
        self.env = patch.dict(os.environ, env, clear=True); self.env.start(); self.addCleanup(self.env.stop)
        self.identity = fixed.handoff.identity()
        self.clock = {'schema': archive.CLOCK_SCHEMA, **self.identity,
                      'started_monotonic': time.monotonic(), 'started_unix': time.time(),
                      'execution_budget_seconds': 1560}
        (self.root / archive.CLOCK).write_text(json.dumps(self.clock))

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!'+sys.executable+'\n'+body)
        path.chmod(0o755)
        return path

    def test_metadata_calls_actual_helper_and_six_real_bounded_children(self):
        records = {}
        for key in fixed.ARTIFACTS:
            value = fixed.artifact_record(key)
            records[value['artifact_id']] = {'id': int(value['artifact_id']), 'name': value['name'],
                'expired': False, 'digest': 'sha256:'+value['reported_upload_artifact_digest'],
                'workflow_run': {'id': int(value['run_id']), 'head_sha': value['source_sha'],
                                 'head_branch': fixed.ORIGINAL_IOS['branch']}}
        (self.root/'metadata-fixture.json').write_text(json.dumps(records))
        self.script('gh', '''import json,os,pathlib,sys
root=pathlib.Path(os.environ['RUNNER_TEMP'])
expected='repos/100mango/Celluloid/actions/artifacts/'
if len(sys.argv)!=3 or sys.argv[1]!='api' or not sys.argv[2].startswith(expected):raise SystemExit(64)
records=json.loads((root/'metadata-fixture.json').read_text());key=sys.argv[2][len(expected):]
if key not in records:raise SystemExit(65)
with (root/'actual-metadata-children.jsonl').open('a') as out:out.write(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'artifact':key})+'\\n')
print(json.dumps(records[key]))
''')
        # No patch of bounded_optional_process or Popen: this is the production
        # callsite, argument signature, selector/pipe, wait and finalized result.
        result = fixed.fetch_metadata(self.root)
        calls = [json.loads(line) for line in (self.root/'actual-metadata-children.jsonl').read_text().splitlines()]
        self.assertEqual(len(calls), 6); self.assertEqual({r['artifact'] for r in calls}, set(records))
        self.assertEqual(len({r['pid'] for r in calls}), 6)
        self.assertTrue(all(r['pid']==r['pgid'] for r in calls))
        self.assertTrue(result['complete']); self.assertEqual(len(result['observations']), 6)
        self.assertTrue(all(r['finalized'] and r['pipe_eof'] and r['child_reaped'] for r in result['observations'].values()))

    def test_archive_observer_calls_actual_helper_with_controlled_tool(self):
        stub = self.script('controlled-lipo', "print('arm64')\n")
        actual_popen = subprocess.Popen
        def owned_tool(command, stdout, stderr, start_new_session, bufsize):
            self.assertEqual(command, ['/usr/bin/xcrun', 'lipo', '-archs', '/owned/Celluloid'])
            self.assertEqual((stdout,stderr,start_new_session,bufsize),
                             (subprocess.PIPE,subprocess.STDOUT,True,0))
            return actual_popen([str(stub)],stdout=stdout,stderr=stderr,
                                start_new_session=start_new_session,bufsize=bufsize)
        owner = archive.ProofCommands(time.monotonic()+10)
        # Only the exact macOS executable is substituted with this owned fixture;
        # helper signature, real child, pipes, deadlines and wait all execute.
        with patch.object(process.subprocess,'Popen',side_effect=owned_tool):
            raw = owner.run('lipo', Path('/owned/Celluloid'))
        self.assertEqual(raw, 'arm64\n')
        self.assertEqual(len(owner.events), 1)
        self.assertFalse(owner.blocked)

    def test_signal_denial_stops_real_helper_without_a_second_signal_or_reap(self):
        started = self.root / 'owned-child-started'
        child = self.script('denial-child', "import pathlib,time\npathlib.Path("+repr(str(started))+").touch()\ntime.sleep(.6)\n")
        real_popen = subprocess.Popen; children=[]; signals=[]
        def spawn(*args, **kwargs):
            actual = real_popen(*args, **kwargs); children.append(actual); return actual
        def deny(pid, sig):
            signals.append((pid, sig)); raise PermissionError(1, 'synthetic owned-group denial')
        now = time.monotonic()
        with patch.object(process.subprocess, 'Popen', side_effect=spawn), patch.object(process.os, 'killpg', side_effect=deny):
            result = process.bounded_optional_process([str(child)], now+.2, now+1, stop_on_signal_error=True)
        self.assertEqual(signals, [(children[0].pid, signal.SIGTERM)])
        self.assertFalse(result['finalized']); self.assertFalse(result['child_reaped'])
        self.assertEqual(result['cleanup_error'], 'PermissionError')
        # The isolated test child exits naturally; test teardown reaps it without
        # signaling. The production helper deliberately did not claim cleanup.
        self.assertEqual(children[0].wait(timeout=2), 0)


if __name__ == '__main__': unittest.main()
