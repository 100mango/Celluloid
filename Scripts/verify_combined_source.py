#!/usr/bin/env python3
"""Bind exact combined app/test/project bytes and workflow to the admitted checkout."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess
from validation_route import current_route
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['before','after'],required=True);args=parser.parse_args()
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    contract=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())
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
    (Path(os.environ['RUNNER_TEMP'])/('combined-source-'+args.phase+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('COMBINED_SOURCE '+json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
