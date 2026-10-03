"""Nonsecret release guard. Network is used ONLY by the explicit verify-ci command.
This file is trusted controller code; never load it from the app checkout/artifact.
"""
from __future__ import annotations
import argparse, base64, datetime as dt, hashlib, json, os, pathlib, plistlib, re, shutil, stat, subprocess, sys, tarfile, urllib.request, urllib.parse, zipfile

APPS = {
    'Celluloid': {'repository':'100mango/Celluloid','project':'Celluloid.xcodeproj','scheme':'Celluloid','app':'Mango.Celluloid','extensions':['Mango.Celluloid.CelluloidPhotoExtension']},
    'QRCatcher': {'repository':'100mango/QRCatcher','project':'QRCatcher.xcodeproj','scheme':'QRCatcher','app':'100mango.QRCatcher','extensions':[]},
    'ColorPicker': {'repository':'100mango/ColorPicker','project':'TouchColor.xcodeproj','scheme':'TouchColor','app':'com.mango.touchColor','extensions':[]},
}
SHA = re.compile(r'[0-9a-f]{40}\Z')
RELEASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z')
MAX_COMPRESSED_BYTES=100*1024*1024
MAX_EXPANDED_BYTES=512*1024*1024
MAX_ARCHIVE_MEMBERS=10000
SNAPKIT={
    'identity':'snapkit',
    'repository':'https://github.com/SnapKit/SnapKit.git',
    'version':'5.7.1',
    'revision':'2842e6e84e82eb9a8dac0100ca90d9444b0307f4',
    'product_directory':'SnapKit_3965163F11347F41_PackageProduct.framework',
    'resolved_paths':[
        'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved',
        'Celluloid.xcworkspace/xcshareddata/swiftpm/Package.resolved',
    ],
}


def require(ok, message):
    if not ok: raise ValueError(message)

def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and not re.search(r'(?i)(TODO|REPLACE|EXAMPLE|PENDING|UNKNOWN)', value)

def https_url(value):
    if not nonempty(value): return False
    p = urllib.parse.urlsplit(value)
    return p.scheme == 'https' and bool(p.netloc) and not p.username and not p.password

def verified_framework_inventory(r):
    """Exact trusted manifest facts; never auto-learn or wildcard unknown bundles."""
    inv=r.get('framework_inventory',{})
    require(inv.get('verified') is True, 'Mandatory observed archive framework inventory is not verified')
    require(inv.get('source_commit')==r['commit'] and inv.get('ci_run_id')==r['ci']['run_id'] and inv.get('ci_run_attempt')==r['ci']['run_attempt'], 'Framework inventory must refer to this exact tested source and CI attempt')
    require(nonempty(inv.get('review_reference')), 'Framework inventory review evidence required')
    rows=inv.get('frameworks')
    require(isinstance(rows,list), 'Exact framework inventory list required')
    if r['app']=='Celluloid':
        require(len(rows)==2,'Celluloid requires explicit first-party and synthesized SnapKit framework inventory')
        byproduct={f.get('product'):f for f in rows}
        require(set(byproduct)=={'CelluloidKit','SnapKit'},'Unknown/missing Celluloid framework product')
        own=byproduct['CelluloidKit']
        require(own.get('bundle_identifier')=='Mango.CelluloidKit' and own.get('directory')=='CelluloidKit.framework' and own.get('origin')=='first-party','First-party framework identity mismatch')
        dep=byproduct['SnapKit']
        require(dep.get('directory')==SNAPKIT['product_directory'] and dep.get('origin')=='swift-package','Unexpected synthesized SnapKit product')
        require(dep.get('package')=={k:SNAPKIT[k] for k in ['identity','repository','version','revision']},'Unreviewed SnapKit package provenance')
    else:
        require(rows==[],'No embedded frameworks approved for this app')
    ids=set()
    for f in rows:
        bid=f.get('bundle_identifier')
        require(isinstance(bid,str) and re.fullmatch(r'[A-Za-z0-9-]+(?:[.][A-Za-z0-9-]+)+',bid) and nonempty(bid),'Observed exact framework bundle identifier required; no wildcards')
        require(bid not in ids and bid not in {APPS[r['app']]['app'],*APPS[r['app']]['extensions']},'Duplicate framework identity')
        ids.add(bid)
        require(nonempty(f.get('version')) and re.fullmatch(r'\d+(?:\.\d+){0,2}',f['version']), 'Observed framework version required; no app-version fallback')
        require(nonempty(f.get('build')) and re.fullmatch(r'\d+(?:\.\d+){0,2}',f['build']), 'Observed framework build required; no app-build fallback')
        require(f.get('architectures')==['arm64'],'Observed arm64 framework architecture required')
    return {f['bundle_identifier']:f for f in rows}

def verify_source_dependencies(r, source):
    if r['app']!='Celluloid': return
    source=pathlib.Path(source)
    expected={'identity':SNAPKIT['identity'],'kind':'remoteSourceControl','location':SNAPKIT['repository'],'state':{'revision':SNAPKIT['revision'],'version':SNAPKIT['version']}}
    for relative in SNAPKIT['resolved_paths']:
        data=json.loads((source/relative).read_text())
        require(data.get('version')==2 and data.get('pins')==[expected], 'Checked-in SnapKit lockfile differs from reviewed exact official revision')

def verify_credential_metadata(r, env):
    key=r['api_key']
    require(env.get('ASC_KEY_ID')==key['key_id'], 'Environment key identifier does not match approved dedicated key')
    require(env.get('ASC_ISSUER_ID')==key['issuer_id'], 'Environment issuer does not match approved dedicated team key')
    require(env.get('APPLE_TEAM_ID')==key['team_id'], 'Environment Apple team does not match approved key scope')

def verify_source_tree_clean(source, expected_sha):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==expected_sha,'App checkout is not the exact tested revision')
    result=subprocess.run(['git','diff','--quiet','HEAD','--'],cwd=source,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    require(result.returncode==0,'Tracked app sources changed during archive build')
    for args in [['--others','--exclude-standard'],['--others','--ignored','--exclude-standard']]:
        unexpected=subprocess.check_output(['git','ls-files',*args,'-z'],cwd=source)
        require(not unexpected,'Unexpected untracked or ignored files in source checkout; no implicit build-output exclusions are approved')

def check_compressed_size(path):
    size=pathlib.Path(path).stat().st_size
    require(0<size<=MAX_COMPRESSED_BYTES,'Compressed artifact exceeds approved 100 MiB ceiling')
    return size

def load_release(path, release_id, mode='dry-run'):
    require(mode in ('dry-run','export','upload'), 'Unsupported mode')
    require(bool(RELEASE_ID.fullmatch(release_id)), 'Invalid release identifier')
    root=json.loads(pathlib.Path(path).read_text())
    require(root.get('schema_version') == 1 and root.get('enabled') is True, 'Release manifest is disabled')
    r=root.get('releases',{}).get(release_id)
    require(isinstance(r,dict), 'Release is not in the trusted allowlist')
    require(r.get('app') in APPS, 'Unknown app')
    a=APPS[r['app']]
    require(r.get('repository') == a['repository'], 'Repository identity mismatch')
    require(isinstance(r.get('commit'),str) and bool(SHA.fullmatch(r['commit'])), 'Exact 40-character final tested commit required')
    require(r.get('ci',{}).get('workflow_path') == '.github/workflows/ios.yml', 'Unexpected test workflow')
    ci=r['ci']
    require(type(ci.get('run_id')) is int and ci['run_id'] > 0, 'Approved CI run ID required')
    require(type(ci.get('run_attempt')) is int and ci['run_attempt'] > 0, 'Approved CI attempt required')
    require(type(ci.get('workflow_id')) is int and ci['workflow_id'] > 0, 'Approved workflow ID required')
    require(ci.get('event') in ('push','workflow_dispatch'), 'Final exact-head push/manual CI is required; PR merge runs do not unlock signing')
    require(ci.get('head_branch')=='codex/ios-modernization', 'Final CI must use the approved modernization branch')
    require(ci.get('workflow_commit')==r['commit'], 'Executing workflow commit must equal the exact tested source commit')
    require(isinstance(ci.get('source_tree_sha'),str) and bool(SHA.fullmatch(ci['source_tree_sha'])), 'Reviewed final source tree SHA required')
    require(ci.get('expected_environment')=={'runner_label':'xcode-27','xcode_version':'27.0','xcode_build':'27A266a','device_sdk':'iphoneos27.0'}, 'Final CI toolchain environment must match reviewed stable Xcode 27')
    require(nonempty(ci.get('toolchain_step')), 'Named successful toolchain verification step required')
    require(bool(re.fullmatch(r'[0-9a-f]{64}',ci.get('reviewed_workflow_sha256',''))), 'Owner-reviewed CI workflow content digest required')
    require(ci.get('provenance_step') == 'Verify exact tested commit', 'Explicit checkout provenance step required')
    require(ci.get('final_provenance_step') == 'Verify tested source stayed unchanged', 'Final source provenance step required')
    require(isinstance(ci.get('required_jobs'),list) and len(ci['required_jobs']) > 0 and all(nonempty(x) for x in ci['required_jobs']), 'Named required CI jobs required')
    require(isinstance(ci.get('required_steps'),dict) and all(isinstance(v,list) and v and all(nonempty(x) for x in v) for v in ci['required_steps'].values()) and set(ci['required_steps']) == set(ci['required_jobs']), 'Named required successful test steps required')
    require(all(ci['provenance_step'] in ci['required_steps'][name] and ci['final_provenance_step'] in ci['required_steps'][name] and ci['toolchain_step'] in ci['required_steps'][name] for name in ci['required_jobs']), 'Provenance and reviewed toolchain verification must pass in every required test job')
    require(nonempty(r.get('version')) and re.fullmatch(r'\d+(?:\.\d+){1,2}',r['version']), 'Reviewed marketing version required')
    require(nonempty(r.get('build')) and re.fullmatch(r'\d+(?:\.\d+){0,2}',r['build']), 'Reviewed build number required')
    require(nonempty(r.get('owner_review_reference')), 'Owner review reference required')
    if mode != 'dry-run':
        require(type(r.get('app_store_record_id')) is str and r['app_store_record_id'].isdigit(), 'Existing App Store record ID required')
        require(https_url(r.get('privacy_policy_url')), 'Final HTTPS privacy policy URL required')
        require(https_url(r.get('support_url')), 'Final HTTPS support URL required')
        require(nonempty(r.get('privacy_support_review_reference')), 'Export privacy/support basics must be reviewed; App Review readiness is a later separate gate')
        storage=r.get('unsigned_artifact_storage',{})
        require(storage.get('approved') is True and storage.get('quota_verified') is True, 'Short-lived unsigned artifact storage/quota not approved and verified')
        require(storage.get('max_compressed_bytes')==MAX_COMPRESSED_BYTES and storage.get('max_expanded_bytes')==MAX_EXPANDED_BYTES and storage.get('retention_days')==1, 'Artifact limits must be reviewed 100 MiB compressed, 512 MiB expanded and one day')
        require(storage.get('paid_overage_authorized') is False,'This template does not authorize paid artifact overage')
        verified_framework_inventory(r)
        require(r.get('existing_bundle_ids_verified') is True, 'Existing Apple identifiers must be verified; new identifiers are forbidden')
        approvals=r.get('approvals',{})
        for approval in ['create_dedicated_admin_team_key','store_dedicated_key_in_protected_github_environment','use_dedicated_key_for_exact_app_releases','acknowledge_admin_all_apps_scope']:
            require(approvals.get(approval) is True, 'Dedicated-key owner approval missing: '+approval)
        key=r.get('api_key',{})
        require(key.get('name')=='iOS Release CI' and key.get('type')=='TEAM' and key.get('role')=='Admin' and key.get('scope')=='ALL_APPS', 'Only explicitly approved dedicated iOS Release CI Admin TEAM all-apps scope is supported')
        require(key.get('github_environment')=='100mango/Celluloid:appstore-release', 'Dedicated key storage destination mismatch')
        require(key.get('setup_completed_verified') is True and nonempty(key.get('owner_approval_reference')), 'Dedicated key secure setup and owner approval must be verified')
        require(bool(re.fullmatch(r'[A-Z0-9]{10}',key.get('key_id') or '')) and bool(re.fullmatch(r'[A-Z0-9]{10}',key.get('team_id') or '')), 'Verified dedicated key and team IDs required')
        require(bool(re.fullmatch(r'[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}',key.get('issuer_id') or '')), 'Verified dedicated team key issuer required')
        require(approvals.get('cloud_sign_existing_distribution_certificate') is True, 'Cloud signing not approved')
        require(approvals.get('allow_provisioning_updates') is True, 'Write-capable provisioning updates not approved')
        require(approvals.get('automatic_signing_side_effects_acknowledged') is True, 'Automatic profile/certificate management scope is not approved')
        require(r.get('archive_export_integration_probe_authorized') is True, 'Unsigned archive export integration probe not approved')
        require(r.get('membership_valid_through') and dt.date.fromisoformat(r['membership_valid_through']) > dt.date.today(), 'Current program membership required')
        require(r.get('existing_distribution_certificate_valid_through') and dt.date.fromisoformat(r['existing_distribution_certificate_valid_through']) > dt.date.today(), 'Valid retained cloud distribution certificate required')
        expected=set([a['app']]+a['extensions'])
        ent=r.get('expected_distribution_entitlements')
        require(isinstance(ent,dict) and set(ent) == expected, 'Explicit entitlement allowlist required for app and every extension')
        require(all(isinstance(v,dict) and v for v in ent.values()), 'Approved exact entitlement dictionaries required')
        if mode == 'upload':
            require(approvals.get('upload_build_to_existing_app_store_record') is True, 'Build upload not approved')
            require(nonempty(r.get('build_upload_review_reference')), 'Separate build-upload metadata decision required; this does not authorize App Review or release')
            require(r.get('upload_purpose') in ('internal-device-validation','release-candidate'), 'Reviewed build upload purpose required')
            require(r.get('build_number_available_verified') is True, 'Build number availability must be verified before upload')
    return r

def validate_ci(r, run, jobs):
    ci=r['ci']
    require(run.get('id') == ci['run_id'] and run.get('run_attempt') == ci['run_attempt'], 'CI run/attempt mismatch')
    require(run.get('workflow_id') == ci['workflow_id'] and run.get('path') == ci['workflow_path'], 'CI workflow identity mismatch')
    require(run.get('head_sha') == r['commit'], 'CI did not test this exact commit')
    require(run.get('repository',{}).get('full_name') == r['repository'] and run.get('head_repository',{}).get('full_name') == r['repository'], 'CI repository/fork mismatch')
    require(run.get('event') == ci['event'], 'CI event mismatch')
    require(run.get('head_branch')==ci['head_branch'], 'CI branch mismatch')
    require(run.get('head_commit',{}).get('id')==r['commit'], 'CI head commit metadata mismatch')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'CI is not completed successfully')
    if run.get('event') == 'pull_request':
        prs=run.get('pull_requests',[])
        require(prs and all(p.get('head',{}).get('sha') == r['commit'] and p.get('head',{}).get('repo',{}).get('id') == run.get('repository',{}).get('id') for p in prs), 'PR head must be the exact approved non-fork commit; merge-SHA evidence is not accepted')
    require(jobs and all(j.get('conclusion') == 'success' and j.get('status') == 'completed' for j in jobs), 'CI contains failed, skipped, cancelled or incomplete jobs')
    byname={j['name']:j for j in jobs}
    require(len(byname) == len(jobs), 'Ambiguous duplicate CI job names')
    for name in ci['required_jobs']:
        require(name in byname, 'Required CI job missing: '+name)
        job=byname[name]
        require(job.get('labels')==[ci['expected_environment']['runner_label']], 'CI runner label differs from the approved standard Xcode runner')
        require(job.get('head_sha') == r['commit'] and job.get('run_id') == ci['run_id'] and job.get('run_attempt') == ci['run_attempt'], 'CI job provenance mismatch')
        steps={s['name']:s for s in job.get('steps',[])}
        for step in ci['required_steps'][name]:
            require(step in steps and steps[step].get('status') == 'completed' and steps[step].get('conclusion') == 'success', 'Required test step missing/not successful: '+step)

def api_get(path):
    parsed=urllib.parse.urlsplit(path)
    parts=parsed.path.split('/')
    require(not parsed.scheme and not parsed.netloc and not parsed.fragment and len(parts)>=5 and parts[:2]==['','repos'] and not any(p in ('.','..') or '%' in p for p in parts), 'Invalid GitHub API destination')
    repository='/'.join(parts[2:4])
    require(repository in {a['repository'] for a in APPS.values()}, 'GitHub API destination outside approved repositories')
    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'trusted-ios-release-guard'}
    token=os.environ.get('GH_READ_TOKEN')
    if token and repository=='100mango/Celluloid': headers['Authorization']='Bearer '+token
    # Cross-repository evidence uses public GET endpoints without credentials.
    # Never retry with broader credentials or swallow errors/rate limits.
    # Explicit GET only. Never print request headers or response bodies.
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com'+path,headers=headers,method='GET'),timeout=30) as response:
        return json.load(response)

def verify_remote_ci(r):
    base='/repos/'+r['repository']+'/actions/runs/'+str(r['ci']['run_id'])
    run=api_get(base)
    jobs=[]; page=1
    while True:
        result=api_get(base+'/attempts/'+str(r['ci']['run_attempt'])+'/jobs?per_page=100&page='+str(page))
        batch=result.get('jobs',[]); jobs.extend(batch)
        if len(batch)<100: break
        page+=1; require(page<=10,'Unexpectedly many CI jobs')
    validate_ci(r,run,jobs)
    git_commit=api_get('/repos/'+r['repository']+'/git/commits/'+r['commit'])
    require(git_commit.get('sha')==r['commit'] and git_commit.get('tree',{}).get('sha')==r['ci']['source_tree_sha'], 'Final source tree differs from reviewed CI provenance')
    content=api_get('/repos/'+r['repository']+'/contents/'+r['ci']['workflow_path']+'?ref='+r['commit'])
    require(content.get('encoding')=='base64','Unsupported CI workflow content encoding')
    digest=hashlib.sha256(base64.b64decode(content['content'])).hexdigest()
    require(digest==r['ci']['reviewed_workflow_sha256'],'CI workflow differs from owner-reviewed checkout/test instructions')

def validated_tar_members(archive):
    """One shared preflight for pre-upload validation and signer extraction."""
    members=[];expanded_size=0;seen=set()
    for member in archive:
        require(member.size>=0,'Invalid archive member size')
        members.append(member);expanded_size+=member.size
        require(len(members)<=MAX_ARCHIVE_MEMBERS,'Archive member-count limit exceeded')
        require(expanded_size<=MAX_EXPANDED_BYTES,'Archive expanded-size limit exceeded')
        require(member.name not in seen,'Duplicate archive member'); seen.add(member.name)
        path=pathlib.PurePosixPath(member.name)
        require(not path.is_absolute() and '..' not in path.parts and path.parts and path.parts[0]=='Release.xcarchive','Unsafe archive path')
        require(member.isfile() or member.isdir(),'Links and special files are rejected by this starter template')
    require(members,'Empty archive')
    return members

def check_unsigned_artifact(src):
    check_compressed_size(src)
    with tarfile.open(src,'r:gz') as archive:
        validated_tar_members(archive)

def secure_extract_tar(src, destination):
    dest=pathlib.Path(destination)
    require(not dest.exists() or not any(dest.iterdir()), 'Extraction destination must be empty')
    dest.mkdir(parents=True,exist_ok=True)
    check_compressed_size(src)
    with tarfile.open(src,'r:gz') as archive:
        members=validated_tar_members(archive)
        # Current iOS products use no framework symlinks. If a future product needs
        # them, stop and review a confined extraction implementation first.
        archive.extractall(dest,members=members,filter='data')
    return dest/'Release.xcarchive'

def secure_extract_ipa(src, destination):
    dest=pathlib.Path(destination); require(not dest.exists() or not any(dest.iterdir()),'IPA destination must be empty')
    dest.mkdir(parents=True,exist_ok=True)
    check_compressed_size(src)
    with zipfile.ZipFile(src) as z:
        entries=z.infolist(); require(0<len(entries)<=MAX_ARCHIVE_MEMBERS,'IPA member-count limit exceeded')
        require(sum(e.file_size for e in entries)<=MAX_EXPANDED_BYTES,'IPA expanded-size limit exceeded')
        seen=set()
        for e in entries:
            p=pathlib.PurePosixPath(e.filename)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in e.filename,'Unsafe IPA path')
            require(e.filename not in seen,'Duplicate IPA entry'); seen.add(e.filename)
            require(not stat.S_ISLNK(e.external_attr >> 16),'IPA symlinks are rejected')
        z.extractall(dest)
    apps=list((dest/'Payload').glob('*.app')); require(len(apps)==1,'Expected one IPA application')
    return apps[0]

def plist(path):
    with open(path,'rb') as f: return plistlib.load(f)

def inspect_app(r,app, signed=False, team=None):
    app=pathlib.Path(app); a=APPS[r['app']]
    require(app.is_dir(),'App bundle missing')
    for p in app.rglob('*'):
        require(not p.is_symlink(),'Bundle symlinks require a separate reviewed policy')
    frameworks=verified_framework_inventory(r)
    found={}
    bundle_dirs=[app]+list(app.rglob('*.appex'))+list(app.rglob('*.framework'))+list(app.rglob('*.app'))
    expected={a['app'],*a['extensions'],*frameworks}
    for p in bundle_dirs:
        info=plist(p/'Info.plist'); bid=info.get('CFBundleIdentifier')
        require(bid in expected and bid not in found,'Unexpected/duplicate embedded bundle identity')
        found[bid]=(p,info)
        if p.suffix=='.framework':
            require(bid in frameworks and p.name==frameworks[bid]['directory'],'Framework product-directory mismatch')
            versions=frameworks[bid]
        else: versions={'version':r['version'],'build':r['build']}
        require(info.get('CFBundleShortVersionString') == versions['version'] and str(info.get('CFBundleVersion')) == versions['build'],'Version/build mismatch in '+str(bid))
        require(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'],'Non-device/simulator product')
        binary=info.get('CFBundleExecutable')
        require(isinstance(binary,str) and pathlib.PurePath(binary).name==binary and (p/binary).is_file(),'Invalid/missing bundle executable')
        if sys.platform=='darwin':
            archs=subprocess.check_output(['/usr/bin/lipo','-archs',str(p/binary)],text=True).split()
            require(archs==['arm64'],'Expected arm64-only device binary')
        if p.suffix=='.appex':
            require(info.get('NSExtension',{}).get('NSExtensionPointIdentifier')=='com.apple.photo-editing','Unexpected extension host/type')
    require(set(found)==expected,'Missing expected app, extension or framework')
    if signed:
        require(bool(re.fullmatch(r'[A-Z0-9]{10}',team or '')),'Verified Apple team ID required')
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for bid,(p,info) in found.items():
            # No credentials are needed for signature/profile inspection.
            signature=subprocess.check_output(['/usr/bin/codesign','-dv','--verbose=4',str(p)],stderr=subprocess.STDOUT,text=True)
            require('TeamIdentifier='+team in signature,'Code signature team mismatch')
            if p.suffix=='.framework': continue
            raw=subprocess.check_output(['/usr/bin/codesign','-d','--entitlements',':-',str(p)],stderr=subprocess.DEVNULL)
            ent=plistlib.loads(raw)
            expected_ent=r['expected_distribution_entitlements'][bid]
            expected_ent=json.loads(json.dumps(expected_ent).replace('${TEAM_ID}',team))
            require(ent==expected_ent,'Signed entitlements differ from owner-reviewed allowlist')
            application_id=ent.get('application-identifier','')
            require(isinstance(application_id,str) and application_id.endswith('.'+bid) and '*' not in application_id and len(application_id)>len(bid)+1,'Signed application identifier does not match bundle identity')
            profile=plistlib.loads(subprocess.check_output(['/usr/bin/security','cms','-D','-i',str(p/'embedded.mobileprovision')],stderr=subprocess.DEVNULL))
            require(profile.get('TeamIdentifier') == [team], 'Provisioning team mismatch')
            require(profile.get('ExpirationDate') and profile['ExpirationDate']>dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),'Expired profile')
            pe=profile.get('Entitlements',{})
            require(pe.get('application-identifier')==ent.get('application-identifier') and pe.get('get-task-allow') is False,'Invalid App Store profile identity/debug entitlement')
            require('ProvisionedDevices' not in profile and profile.get('ProvisionsAllDevices') is not True,'Device/ad-hoc/enterprise profile rejected')
            require(ent.get('get-task-allow') is False and ent.get('com.apple.developer.team-identifier') == team, 'Invalid distribution entitlements')
    return {'app':r['app'],'commit':r['commit'],'version':r['version'],'build':r['build'],'bundles':sorted(found),'signed_verified':signed}

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['validate','verify-ci','extract','inspect-archive','inspect-ipa','export-options','verify-source-dependencies','verify-credential-metadata','check-artifact-size','check-unsigned-artifact','verify-source-clean']); p.add_argument('--manifest',required=True); p.add_argument('--release',required=True); p.add_argument('--mode',default='dry-run'); p.add_argument('--path'); p.add_argument('--destination'); p.add_argument('--team'); p.add_argument('--output'); args=p.parse_args()
    r=load_release(args.manifest,args.release,args.mode)
    if args.command=='validate':
        if args.output: pathlib.Path(args.output).write_text(json.dumps(r,indent=2)+'\n')
        print('Allowlist and nonsecret release requirements passed')
    elif args.command=='verify-source-clean': verify_source_tree_clean(args.path,r['commit']); print('Exact source checkout is clean, including untracked and ignored files')
    elif args.command=='verify-source-dependencies': verify_source_dependencies(r,args.path); print('Reviewed source dependency pins verified')
    elif args.command=='verify-credential-metadata': verify_credential_metadata(r,os.environ); print('Approved dedicated key metadata matches protected environment')
    elif args.command=='check-artifact-size': check_compressed_size(args.path); print('Artifact within approved 100 MiB compressed ceiling')
    elif args.command=='check-unsigned-artifact': check_unsigned_artifact(args.path); print('Unsigned artifact size, member and path limits verified before upload')
    elif args.command=='verify-ci': verify_remote_ci(r); print('Exact allowlisted commit and successful CI run/attempt/steps verified')
    elif args.command=='extract': secure_extract_tar(args.path,args.destination); print('Unsigned archive safely extracted')
    elif args.command=='inspect-archive':
        archive=pathlib.Path(args.path); apps=list((archive/'Products'/'Applications').glob('*.app')); require(len(apps)==1,'Expected one archive application')
        print(json.dumps(inspect_app(r,apps[0]),sort_keys=True))
    elif args.command=='inspect-ipa':
        app=secure_extract_ipa(args.path,args.destination); print(json.dumps(inspect_app(r,app,signed=True,team=args.team),sort_keys=True))
    elif args.command=='export-options':
        require(bool(re.fullmatch(r'[A-Z0-9]{10}',args.team or '')),'Verified team ID required')
        # Deliberately export-only. Build upload is a later, distinct operation.
        options={'method':'app-store-connect','destination':'export','signingStyle':'automatic','teamID':args.team,'manageAppVersionAndBuildNumber':False,'stripSwiftSymbols':True,'uploadSymbols':False}
        with open(args.output,'wb') as f: plistlib.dump(options,f)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Avoid rendering raw external responses/credentials in CI logs.
        message=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        print('RELEASE BLOCKED: '+message,file=sys.stderr); sys.exit(1)
