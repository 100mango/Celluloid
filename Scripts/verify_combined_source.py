#!/usr/bin/env python3
"""Bind exact combined app/test/project bytes and workflow to the admitted checkout."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess
from validation_route import current_route,HOST_ONLY,host_only_source_binding,UIKIT_FULL,UIKIT_FULL_BASE,UIKIT_FULL_DRIVER_PATHS,UIKIT_FULL_PREDECESSOR,UIKIT_FULL_REPAIR_PATHS,ORIGINAL_IOS,ORIGINAL_IOS_BASE,ORIGINAL_IOS_PATHS,ORIGINAL_IOS_PREDECESSOR,ORIGINAL_IOS_REPAIR_PATHS,ORIGINAL_IOS_QUALIFIED_PREDECESSOR,ORIGINAL_IOS_FIRST_SUMMARY_PATHS,ORIGINAL_IOS_ARCHIVE_PREDECESSOR,ORIGINAL_IOS_ARCHIVE_ONLY_PATHS,ORIGINAL_IOS_RESOURCE_PREDECESSOR,ORIGINAL_IOS_RESOURCE_PATHS
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
        qualified=ORIGINAL_IOS_QUALIFIED_PREDECESSOR
        prior_archive=ORIGINAL_IOS_ARCHIVE_PREDECESSOR
        resource_prior=ORIGINAL_IOS_RESOURCE_PREDECESSOR
        assert git('rev-list','--parents','-n','1','HEAD').split()==[os.environ['GITHUB_SHA'],resource_prior['commit']], 'Unreviewed observed-resource parent'
        assert git('rev-list','--parents','-n','1',resource_prior['commit']).split()==[resource_prior['commit'],prior_archive['commit']], 'Changed exact archived predecessor parent'
        assert git('rev-parse',resource_prior['commit']+'^{tree}')==resource_prior['tree'], 'Changed exact archived predecessor tree'
        assert set(git('diff','--name-only',resource_prior['commit'],'HEAD').splitlines())==ORIGINAL_IOS_RESOURCE_PATHS, 'Unreviewed observed-resource delta'
        assert git('rev-list','--parents','-n','1',prior_archive['commit']).split()==[prior_archive['commit'],qualified['commit']], 'Changed exact completed-cohort parent'
        assert git('rev-parse',prior_archive['commit']+'^{tree}')==prior_archive['tree'], 'Changed exact completed-cohort tree'
        assert set(git('diff','--name-only',prior_archive['commit'],resource_prior['commit']).splitlines())==ORIGINAL_IOS_ARCHIVE_ONLY_PATHS, 'Unreviewed archive-only delta'
        assert git('rev-list','--parents','-n','1',qualified['commit']).split()==[qualified['commit'],ORIGINAL_IOS_PREDECESSOR['commit']], 'Changed exact qualified predecessor parent'
        assert git('rev-parse',qualified['commit']+'^{tree}')==qualified['tree'], 'Changed exact qualified predecessor tree'
        assert set(git('diff','--name-only',qualified['commit'],prior_archive['commit']).splitlines())==ORIGINAL_IOS_FIRST_SUMMARY_PATHS, 'Unreviewed fixed first-summary/replay delta'
        assert git('rev-list','--parents','-n','1',ORIGINAL_IOS_PREDECESSOR['commit']).split()==[ORIGINAL_IOS_PREDECESSOR['commit'],ORIGINAL_IOS_BASE['commit']], 'Changed fixed staged predecessor parent'
        assert git('rev-parse',ORIGINAL_IOS_PREDECESSOR['commit']+'^{tree}')==ORIGINAL_IOS_PREDECESSOR['tree'], 'Changed fixed staged predecessor tree'
        assert git('rev-parse',ORIGINAL_IOS_BASE['commit']+'^{tree}')==ORIGINAL_IOS_BASE['tree'], 'Changed staged iOS baseline tree'
        assert set(git('diff','--name-only',ORIGINAL_IOS_BASE['commit'],ORIGINAL_IOS_PREDECESSOR['commit']).splitlines())==ORIGINAL_IOS_PATHS, 'Changed original staged isolation delta'
        assert set(git('diff','--name-only',ORIGINAL_IOS_PREDECESSOR['commit'],qualified['commit']).splitlines())==ORIGINAL_IOS_REPAIR_PATHS, 'Unreviewed staged supervision delta'
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
