#!/usr/bin/env python3
"""Bind exact combined app/test/project bytes and workflow to the admitted checkout."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess
from validation_route import current_route,HOST_ONLY,host_only_source_binding,UIKIT_FULL,UIKIT_FULL_BASE,UIKIT_FULL_DRIVER_PATHS,UIKIT_FULL_PREDECESSOR,UIKIT_FULL_REPAIR_PATHS,ORIGINAL_IOS,ORIGINAL_IOS_BASE,ORIGINAL_IOS_PATHS
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['before','after'],required=True);args=parser.parse_args()
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    route=current_route()
    contract=json.loads((ROOT/('Scripts/original-ios-source-contract.json' if route==ORIGINAL_IOS else 'Scripts/combined-source-contract.json')).read_text())
    assert os.environ['GITHUB_REPOSITORY']=='100mango/Celluloid'
    route=current_route()
    assert os.environ['GITHUB_WORKFLOW_SHA']==os.environ['GITHUB_SHA']==git('rev-parse','HEAD')
    assert not git('status','--porcelain','--untracked-files=all'), 'Combined checkout changed'
    paths=git('ls-files','-z','--',*contract['roots']).split('\0')
    rows=[[p,hashlib.sha256((ROOT/p).read_bytes()).hexdigest()] for p in paths if p]
    assert rows==contract['files'], 'Combined production/test/project bytes or membership changed'
    fingerprint=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    assert fingerprint==contract['fingerprint']
    forbidden=['.github/release-controller','.github/workflows/cloud-release.yml']
    assert not any(git('ls-files','--',p) for p in forbidden)
    report={'source_sha':os.environ['GITHUB_SHA'],'tree':git('rev-parse','HEAD^{tree}'),'phase':args.phase,'file_count':len(rows),'source_fingerprint':fingerprint,'reviewed_source_tree':contract['reviewed_source_tree'],'appearance_cancel_patch_sha256':contract.get('appearance_cancel_patch_sha256'),'expected_UIKit_executions':contract.get('expected_UIKit_executions'),'uikit_base':contract['uikit_base'],'native_base':contract['native_base'],'workflow_sha256':hashlib.sha256((ROOT/route['workflow_path']).read_bytes()).hexdigest(),'validation_route':route}
    if route==ORIGINAL_IOS:
        from original_ios_source_contract import audit
        assert git('rev-list','--parents','-n','1','HEAD').split()==[os.environ['GITHUB_SHA'],ORIGINAL_IOS_BASE['commit']], 'Unreviewed staged iOS parent'
        assert git('rev-parse',ORIGINAL_IOS_BASE['commit']+'^{tree}')==ORIGINAL_IOS_BASE['tree'], 'Changed staged iOS baseline tree'
        assert set(git('diff','--name-only',ORIGINAL_IOS_BASE['commit'],'HEAD').splitlines())==ORIGINAL_IOS_PATHS, 'Unreviewed staged iOS delta'
        report['original_ios_source']=audit(ROOT)
    if route==HOST_ONLY:
        report['host_only_diagnostic']=host_only_source_binding(rows)
    if route==UIKIT_FULL:
        assert fingerprint==UIKIT_FULL_BASE['fingerprint'] and len(rows)==547
        assert git('rev-list','--parents','-n','1','HEAD').split()==[os.environ['GITHUB_SHA'],UIKIT_FULL_PREDECESSOR['commit']], 'Unreviewed UIKit clock-repair parent'
        assert git('rev-list','--parents','-n','1',UIKIT_FULL_PREDECESSOR['commit']).split()==[UIKIT_FULL_PREDECESSOR['commit'],UIKIT_FULL_BASE['commit']], 'Changed fixed UIKit predecessor parent'
        assert git('rev-parse',UIKIT_FULL_PREDECESSOR['commit']+'^{tree}')==UIKIT_FULL_PREDECESSOR['tree'], 'Changed fixed UIKit predecessor tree'
        assert set(git('diff','--name-only',UIKIT_FULL_PREDECESSOR['commit'],'HEAD').splitlines())==UIKIT_FULL_REPAIR_PATHS, 'Unreviewed UIKit clock-repair delta'
        assert git('rev-parse',UIKIT_FULL_BASE['commit']+'^{tree}')==UIKIT_FULL_BASE['tree']
        changed=set(git('diff','--name-only',UIKIT_FULL_BASE['commit'],'HEAD').splitlines())
        assert changed<=UIKIT_FULL_DRIVER_PATHS, 'Unreviewed full-shipping source change'
        report['full_shipping_source']={'base':dict(UIKIT_FULL_BASE),'fixed_predecessor':dict(UIKIT_FULL_PREDECESSOR),'clock_repair_paths':sorted(UIKIT_FULL_REPAIR_PATHS),'protected_files':547,'driver_paths':sorted(changed),
            'scope':'Fresh original UIKit row coverage; Mac Photos host and release remain separate'}
    (Path(os.environ['RUNNER_TEMP'])/('combined-source-'+args.phase+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('COMBINED_SOURCE '+json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
