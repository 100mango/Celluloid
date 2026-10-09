#!/usr/bin/env python3
"""Dedicated diagnostic: one build/bootstrap plus five actual Photos-host cases."""
import json
import os
import re
import signal
import subprocess
import sys
import time
from run_swiftui_acceptance import Acceptance, ROOT, OUT, DERIVED, extract_json, owner_receipt, save, require
from run_picker_acceptance import build_binding
from run_ios_photos_host import check_product_control, PRODUCT_CONTROL_TREE, PRODUCT_CONTROL_SHA256, admit_probe

class HostDiagnostic(Acceptance):
    def command(self, name, command, seconds, simulator=False, allow_failure=False, nested_owned=False):
        require(not self.uncertain, 'Uncertain Photos native state blocks further command dispatch')
        dispatched=time.monotonic();result=None
        # Reuse the existing group-owned adapter, but include interpreter/startup
        # latency in the parent deadline. Nested bootstrap retains its own caps.
        if not nested_owned:
            command=[sys.executable,'-S','Scripts/run_bounded.py','--seconds',str(seconds),'--label',name,
                     '--deadline-monotonic',str(dispatched+seconds),*command]
        try:
            result=super().command(name,command,seconds,simulator=simulator,allow_failure=allow_failure,nested_owned=True)
        finally:
            elapsed=time.monotonic()-dispatched;late=elapsed>seconds
            if late:
                self.uncertain=True
                if not any(item['phase']==name for item in self.failures):self.failures.append({'phase':name,'exit_code':124})
            save(OUT/(name+'-dispatch-timing.json'),{'phase':name,'dispatch_started_monotonic':dispatched,
                 'deadline_monotonic':dispatched+seconds,'elapsed_seconds':elapsed,'limit_seconds':seconds,
                 'late_completion':late,'returned_exit_code':result[0] if result is not None else None,
                 'prohibit_further_native':self.uncertain})
        require(not late, name+': parent dispatch deadline exceeded, including late exit0')
        return result

    def cleanup(self):
        if not self.device or self.uncertain:return
        deadline=min(self.started+2370,time.monotonic()+90)
        for action in ['shutdown','delete']:
            if deadline-time.monotonic()<35:return
            dispatched=time.monotonic();path=OUT/('cleanup-'+action+'.log')
            command=[sys.executable,'-S','Scripts/run_bounded.py','--seconds','30','--label','cleanup-'+action,
                     '--deadline-monotonic',str(dispatched+30),'xcrun','simctl',action,self.device]
            try:
                with path.open('wb') as stream:code=subprocess.call(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            except BaseException:
                self.uncertain=True
                raise
            elapsed=time.monotonic()-dispatched;late=elapsed>30
            save(OUT/('cleanup-'+action+'-dispatch-timing.json'),{'phase':'cleanup-'+action,'elapsed_seconds':elapsed,
                 'limit_seconds':30,'returned_exit_code':code,'late_completion':late})
            if code or late:self.uncertain=True;return
        self.device=None

    def bootstrap(self):
        command = ['/bin/bash', 'Scripts/run_swiftui_photos_gate.sh', 'bootstrap', self.device,
            str(DERIVED), str(OUT / 'photos'), str(OUT / 'owned-simulator.json'), 'refs/heads/cell-ios-photos-host-final']
        code, _ = self.command('photos-bootstrap', command, 750, simulator=True, allow_failure=True, nested_owned=True)
        path = OUT / 'photos/bootstrap-safety.json'
        receipt = json.loads(path.read_text()) if path.is_file() else {}
        if (receipt.get('phase') != 'bootstrap' or receipt.get('exit_code') != code
                or any(type(receipt.get(key)) is not bool for key in ['timeout_observed', 'cleanup_uncertain_observed',
                    'shared_deadline_exhausted', 'prohibit_further_simctl'])
                or receipt.get('prohibit_further_simctl') is not False): self.uncertain = True
        return code

    def run(self):
        require(sys.platform == 'darwin' and os.environ.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong stable Xcode route')
        require(os.environ.get('GITHUB_REPOSITORY') == '100mango/Celluloid'
                and os.environ.get('GITHUB_REF') == 'refs/heads/cell-ios-photos-host-final'
                and os.environ.get('GITHUB_EVENT_NAME') == 'push'
                and os.environ.get('GITHUB_WORKFLOW_SHA') == self.source, 'Wrong exact-source diagnostic route')
        require(re.fullmatch(r'[0-9a-f]{40}', self.source), 'Missing exact source SHA')
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, timeout=15).strip() == self.source, 'Checkout source differs')
        self.source_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True, timeout=15).strip()
        self.command('clean-start', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)
        check_product_control()
        _, version = self.command('toolchain', ['xcodebuild', '-version'], 30)
        require('Xcode 27.0' in version.splitlines(), 'Wrong stable toolchain')
        self.command('host-portable', [sys.executable, '-S', 'Scripts/test_ios_photos_host.py'], 30)
        _, before = self.command('devices-before', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        before = extract_json(before, 'devices'); save(OUT / 'devices-before.json', before)
        _, created = self.command('create-owned-device', [sys.executable, 'Scripts/select_test_devices.py', 'iPhone SE (3rd generation)'], 60, simulator=True)
        matches = re.findall(r'^([0-9A-Fa-f-]{36}) iPhone SE \(3rd generation\)$', created, re.M)
        require(len(matches) == 1, 'Missing/ambiguous owned create receipt'); device = matches[0]
        _, after = self.command('devices-after-create', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        after = extract_json(after, 'devices'); save(OUT / 'devices-after-create.json', after)
        owner = owner_receipt(before, after, device, os.environ, self.source, self.started, self.deadline)
        self.device = device; save(OUT / 'owned-simulator.json', owner)
        base = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
            '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', str(DERIVED),
            'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO']
        self.command('build', [*base, '-jobs', '2', 'build-for-testing'], 720)
        binary = DERIVED / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
        save(OUT / 'build-binding.json', build_binding(binary, self.source, self.source_tree))
        self.command('boot', ['xcrun', 'simctl', 'boot', device], 60, simulator=True)
        self.command('bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], 300, simulator=True)
        # No preliminary product suite is needed to register the built app.
        self.command('install-owned-app', ['xcrun', 'simctl', 'install', device, str(binary.parent)], 120, simulator=True)
        require(self.bootstrap() == 0 and not self.uncertain, 'Real fixture bootstrap failed')
        command = [sys.executable, 'Scripts/run_ios_photos_host.py', '--device', device, '--derived', str(DERIVED),
            '--out', str(OUT / 'ios-photos-host'), '--owner', str(OUT / 'owned-simulator.json'),
            '--build-binding', str(OUT / 'build-binding.json'), '--fixture-manifest', str(OUT / 'photos/verified-library.json')]
        code, _ = self.command('actual-photos-host', command, 630, simulator=True, allow_failure=True, nested_owned=True)
        result = OUT / 'ios-photos-host/acceptance.json'
        receipt = json.loads(result.read_text()) if result.is_file() else {}
        if (receipt.get('source_sha') != self.source or receipt.get('device_id') != device
                or receipt.get('prohibit_further_simctl') is not False): self.uncertain = True
        require(code == 0 and receipt.get('all_five_stages_passed') is True, 'Actual Photos host diagnostic did not pass')
        self.command('clean-end', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)
        require(admit_probe() == self.admission, 'Source/control changed during Photos host diagnostic')

def main():
    admission = admit_probe()
    require(json.loads((ROOT/'build/final-photos-host-source-before.json').read_text()) == admission, 'Workflow source admission differs')
    os.chdir(ROOT); os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'): time.tzset()
    gate = HostDiagnostic(); gate.admission = admission; error = None
    def stop(signum, frame): raise KeyboardInterrupt('Actual Photos diagnostic interrupted')
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try: gate.run()
    except BaseException as failure: error = str(failure)
    finally:
        gate.cleanup()
        accepted = error is None and not gate.failures and not gate.device and not gate.uncertain
        save(OUT / 'acceptance.json', {'schema': 'celluloid.ios.photos-host-diagnostic.v1', 'source_sha': gate.source,
            'source_tree': gate.source_tree, 'actual_host_diagnostic_passed': accepted, 'error': error,
            'product_sha': admission['product_sha'], 'source_admission': admission,
            'product_control_tree': PRODUCT_CONTROL_TREE, 'product_control_sha256': PRODUCT_CONTROL_SHA256,
            'failed_phases': gate.failures, 'simulator_uncertain': gate.uncertain, 'pending_owned_device': gate.device,
            'work_budget_seconds': 2280, 'elapsed_seconds': time.monotonic() - gate.started,
            'existing_full_suite_rerun': False, 'new_host_test_count': 5, 'release_qualification': False})
    return 0 if accepted else 1

if __name__ == '__main__': raise SystemExit(main())
