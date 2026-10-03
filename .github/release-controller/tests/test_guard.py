from unittest import mock
import copy, hashlib, importlib.util, io, json, os, pathlib, plistlib, tarfile, tempfile, unittest, zipfile
BASE=pathlib.Path(__file__).resolve().parents[1]
WORKFLOW_PATH=BASE/'cloud-release.yml.template'
if not WORKFLOW_PATH.exists(): WORKFLOW_PATH=BASE.parent/'workflows'/'cloud-release.yml'
spec=importlib.util.spec_from_file_location('guard',BASE/'scripts/guard.py'); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.dir=pathlib.Path(self.temp.name)
        self.r=json.loads((BASE/'examples/QRCatcher.release.example.json').read_text())
        self.r.update(commit='a'*40,version='2.0',build='42',owner_review_reference='Fixture owner-reviewed release decision',app_store_record_id='1234567890',privacy_policy_url='https://owner.test/privacy',support_url='https://owner.test/support',privacy_support_review_reference='Fixture privacy and support basics approved',build_upload_review_reference='Fixture approved build upload decision',existing_bundle_ids_verified=True,archive_export_integration_probe_authorized=True,membership_valid_through='2099-01-01',existing_distribution_certificate_valid_through='2099-01-01',build_number_available_verified=True,upload_purpose='internal-device-validation')
        self.r['ci'].update(run_id=111,run_attempt=1,workflow_id=222,workflow_commit='a'*40,source_tree_sha='c'*40,reviewed_workflow_sha256='b'*64,required_steps={'simulator':['Verify exact tested commit','Verify stable cloud toolchain','Unit tests','UI tests','Verify tested source stayed unchanged']})
        self.r['api_key'].update(key_id='KEYTEST001',team_id='TEAMTEST01',issuer_id='00000000-0000-0000-0000-000000000000',setup_completed_verified=True,owner_approval_reference='Fixture explicit owner approval')
        self.r['unsigned_artifact_storage'].update(approved=True,quota_verified=True)
        self.r['framework_inventory'].update(verified=True,source_commit='a'*40,ci_run_id=111,ci_run_attempt=1,review_reference='Fixture reviewed empty framework inventory')
        self.r['approvals']={k:True for k in self.r['approvals']}
        self.r['expected_distribution_entitlements']={'100mango.QRCatcher':{'application-identifier':'${TEAM_ID}.100mango.QRCatcher','com.apple.developer.team-identifier':'${TEAM_ID}','get-task-allow':False}}
        self.run={'id':111,'run_attempt':1,'workflow_id':222,'path':'.github/workflows/ios.yml','head_sha':'a'*40,'event':'push','head_branch':'codex/ios-modernization','head_commit':{'id':'a'*40},'status':'completed','conclusion':'success','repository':{'full_name':'100mango/QRCatcher','id':123},'head_repository':{'full_name':'100mango/QRCatcher'}}
        self.jobs=[{'name':'simulator','labels':['xcode-27'],'head_sha':'a'*40,'run_id':111,'run_attempt':1,'status':'completed','conclusion':'success','steps':[{'name':n,'status':'completed','conclusion':'success'} for n in self.r['ci']['required_steps']['simulator']]}]
    def tearDown(self): self.temp.cleanup()
    def manifest(self,r=None,enabled=True):
        p=self.dir/'manifest.json'; p.write_text(json.dumps({'schema_version':1,'enabled':enabled,'releases':{'approved':r or self.r}})); return p
    def test_valid_dry_export_upload(self):
        for mode in ['dry-run','export','upload']: self.assertEqual(g.load_release(self.manifest(),'approved',mode)['commit'],'a'*40)
    def test_shipped_manifest_is_disabled(self):
        with self.assertRaisesRegex(ValueError,'disabled'):g.load_release(BASE/'release-manifest.json','anything')
    def test_no_arbitrary_sha_release(self):
        with self.assertRaisesRegex(ValueError,'allowlist'):g.load_release(self.manifest(),'a'*40)
    def test_shell_injection_release_rejected(self):
        with self.assertRaises(ValueError):g.load_release(self.manifest(),'x; echo secret')
    def test_wrong_identity_rejected(self):
        self.r['repository']='other/QRCatcher'
        with self.assertRaises(ValueError):g.load_release(self.manifest(),'approved')
    def test_missing_metadata_blocks_signing(self):
        self.r['privacy_policy_url']=None
        with self.assertRaisesRegex(ValueError,'privacy'):g.load_release(self.manifest(),'approved','export')
    def test_export_does_not_require_app_review_or_upload_metadata(self):
        self.r['build_upload_review_reference']=None
        self.r['app_review_questionnaire_complete']=False
        self.r['sticker_rights_review_complete']=False
        g.load_release(self.manifest(),'approved','export')
        with self.assertRaisesRegex(ValueError,'build-upload metadata'):g.load_release(self.manifest(),'approved','upload')
    def test_clean_checkout_verification(self):
        with mock.patch.object(g.subprocess,'check_output',side_effect=['a'*40+'\n',b'',b'']),mock.patch.object(g.subprocess,'run',return_value=mock.Mock(returncode=0)):
            g.verify_source_tree_clean(self.dir,'a'*40)
    def test_untracked_source_rejected(self):
        with mock.patch.object(g.subprocess,'check_output',side_effect=['a'*40+'\n',b'Unexpected.swift\0']),mock.patch.object(g.subprocess,'run',return_value=mock.Mock(returncode=0)):
            with self.assertRaisesRegex(ValueError,'untracked'):g.verify_source_tree_clean(self.dir,'a'*40)
    def test_ignored_source_rejected(self):
        with mock.patch.object(g.subprocess,'check_output',side_effect=['a'*40+'\n',b'',b'ignored/Injected.swift\0']),mock.patch.object(g.subprocess,'run',return_value=mock.Mock(returncode=0)):
            with self.assertRaisesRegex(ValueError,'ignored'):g.verify_source_tree_clean(self.dir,'a'*40)
    def test_each_approval_required(self):
        for field in ['create_dedicated_admin_team_key','store_dedicated_key_in_protected_github_environment','use_dedicated_key_for_exact_app_releases','acknowledge_admin_all_apps_scope','cloud_sign_existing_distribution_certificate','allow_provisioning_updates','automatic_signing_side_effects_acknowledged']:
            r=copy.deepcopy(self.r);r['approvals'][field]=False
            with self.subTest(field=field),self.assertRaises(ValueError):g.load_release(self.manifest(r),'approved','export')
    def test_upload_has_extra_gate(self):
        self.r['approvals']['upload_build_to_existing_app_store_record']=False
        g.load_release(self.manifest(),'approved','export')
        with self.assertRaisesRegex(ValueError,'upload not approved'):g.load_release(self.manifest(),'approved','upload')
    def test_unapproved_key_role_rejected(self):
        self.r['api_key']['role']='App Manager'
        with self.assertRaisesRegex(ValueError,'dedicated'):g.load_release(self.manifest(),'approved','export')
    def test_other_key_reuse_rejected(self):
        self.r['api_key']['name']='Other key'
        with self.assertRaisesRegex(ValueError,'dedicated'):g.load_release(self.manifest(),'approved','export')
    def test_missing_all_apps_disclosure_rejected(self):
        self.r['api_key']['scope']='THREE_APPS_ONLY'
        with self.assertRaisesRegex(ValueError,'all-apps'):g.load_release(self.manifest(),'approved','export')
    def test_unverified_secure_setup_rejected(self):
        self.r['api_key']['setup_completed_verified']=False
        with self.assertRaisesRegex(ValueError,'secure setup'):g.load_release(self.manifest(),'approved','export')
    def test_environment_key_identity_binding(self):
        key=self.r['api_key'];env={'ASC_KEY_ID':key['key_id'],'ASC_ISSUER_ID':key['issuer_id'],'APPLE_TEAM_ID':key['team_id']}
        g.verify_credential_metadata(self.r,env)
        env['ASC_KEY_ID']='WRONGKEY12'
        with self.assertRaisesRegex(ValueError,'key identifier'):g.verify_credential_metadata(self.r,env)
    def test_artifact_quota_requires_approval(self):
        self.r['unsigned_artifact_storage']['quota_verified']=False
        with self.assertRaisesRegex(ValueError,'quota'):g.load_release(self.manifest(),'approved','export')
    def test_artifact_ceiling_not_arbitrary(self):
        self.r['unsigned_artifact_storage']['max_compressed_bytes']=1024**3
        with self.assertRaisesRegex(ValueError,'100 MiB'):g.load_release(self.manifest(),'approved','export')
    def test_oversized_artifact_rejected(self):
        p=self.dir/'oversized'
        with p.open('wb') as f:f.truncate(g.MAX_COMPRESSED_BYTES+1)
        with self.assertRaisesRegex(ValueError,'100 MiB'):g.check_compressed_size(p)
    def test_inventory_must_be_verified(self):
        self.r['framework_inventory']['verified']=False
        with self.assertRaisesRegex(ValueError,'inventory'):g.load_release(self.manifest(),'approved','export')
    def test_inventory_is_tied_to_exact_ci_attempt(self):
        self.r['framework_inventory']['ci_run_attempt']=2
        with self.assertRaisesRegex(ValueError,'exact tested'):g.load_release(self.manifest(),'approved','export')
    def test_expired_membership_rejected(self):
        self.r['membership_valid_through']='2020-01-01'
        with self.assertRaisesRegex(ValueError,'membership'):g.load_release(self.manifest(),'approved','export')
    def test_unreviewed_entitlements_rejected(self):
        self.r['expected_distribution_entitlements']={}
        with self.assertRaisesRegex(ValueError,'entitlement'):g.load_release(self.manifest(),'approved','export')
    def test_correct_ci(self):g.validate_ci(self.r,self.run,self.jobs)
    def test_wrong_ci_sha_rejected(self):
        self.run['head_sha']='c'*40
        with self.assertRaisesRegex(ValueError,'exact commit'):g.validate_ci(self.r,self.run,self.jobs)
    def test_pr_merge_evidence_rejected(self):
        self.r['ci']['event']='pull_request'
        with self.assertRaisesRegex(ValueError,'exact-head'):g.load_release(self.manifest(),'approved')
    def test_ci_wrong_branch_rejected(self):
        self.run['head_branch']='master'
        with self.assertRaisesRegex(ValueError,'branch'):g.validate_ci(self.r,self.run,self.jobs)
    def test_ci_wrong_runner_rejected(self):
        self.jobs[0]['labels']=['self-hosted']
        with self.assertRaisesRegex(ValueError,'runner'):g.validate_ci(self.r,self.run,self.jobs)
    def test_ci_workflow_revision_must_match_source(self):
        self.r['ci']['workflow_commit']='f'*40
        with self.assertRaisesRegex(ValueError,'workflow commit'):g.load_release(self.manifest(),'approved')
    def test_ci_toolchain_step_required(self):
        self.r['ci']['required_steps']['simulator'].remove('Verify stable cloud toolchain')
        with self.assertRaisesRegex(ValueError,'toolchain'):g.load_release(self.manifest(),'approved')
    def test_ci_fork_rejected(self):
        self.run['head_repository']['full_name']='attacker/QRCatcher'
        with self.assertRaisesRegex(ValueError,'fork'):g.validate_ci(self.r,self.run,self.jobs)
    def test_wrong_ci_attempt_rejected(self):
        self.run['run_attempt']=2
        with self.assertRaisesRegex(ValueError,'attempt'):g.validate_ci(self.r,self.run,self.jobs)
    def test_skipped_job_rejected(self):
        self.jobs[0]['conclusion']='skipped'
        with self.assertRaises(ValueError):g.validate_ci(self.r,self.run,self.jobs)
    def test_skipped_test_step_rejected(self):
        self.jobs[0]['steps'][1]['conclusion']='skipped'
        with self.assertRaisesRegex(ValueError,'test step'):g.validate_ci(self.r,self.run,self.jobs)
    def test_missing_provenance_step_rejected(self):
        self.r['ci']['required_steps']['simulator'].remove('Verify exact tested commit')
        with self.assertRaisesRegex(ValueError,'Provenance'):g.load_release(self.manifest(),'approved')
    def test_ci_api_token_is_scoped_to_controller_repository(self):
        for repository in ['Celluloid','QRCatcher','ColorPicker']:
            with self.subTest(repository=repository),mock.patch.dict(os.environ,{'GH_READ_TOKEN':'synthetic-test-token'}),mock.patch.object(g.urllib.request,'urlopen',return_value=io.StringIO('{}')) as request:
                self.assertEqual(g.api_get('/repos/100mango/'+repository+'/actions/runs/111'),{})
                outgoing=request.call_args.args[0]
                self.assertEqual(outgoing.get_method(),'GET')
                expected='Bearer synthetic-test-token' if repository=='Celluloid' else None
                self.assertEqual(outgoing.get_header('Authorization'),expected)
    def test_ci_api_unapproved_destinations_never_requested(self):
        paths=['/repos/100mango/Other/actions/runs/111','/repos/attacker/Celluloid/actions/runs/111','/repos/100mango/Celluloid-extra/actions/runs/111','/repos/100mango/Celluloid/../../Other','/repos/100mango/Celluloid/%2e%2e/Other','https://api.github.com/repos/100mango/Celluloid/actions/runs/111']
        with mock.patch.object(g.urllib.request,'urlopen') as request:
            for path in paths:
                with self.subTest(path=path),self.assertRaises(ValueError):g.api_get(path)
            request.assert_not_called()
    def test_ci_api_error_fails_closed_without_retry(self):
        with mock.patch.dict(os.environ,{'GH_READ_TOKEN':'synthetic-test-token'}),mock.patch.object(g.urllib.request,'urlopen',side_effect=OSError('synthetic API failure')) as request:
            with self.assertRaises(OSError):g.api_get('/repos/100mango/QRCatcher/actions/runs/111')
            self.assertEqual(request.call_count,1)
    def make_tar(self,name,kind=None):
        p=self.dir/'input.tar.gz'
        with tarfile.open(p,'w:gz') as t:
            x=tarfile.TarInfo(name)
            if kind=='symlink': x.type=tarfile.SYMTYPE;x.linkname='../../outside'
            else:x.size=1
            t.addfile(x,None if kind else io.BytesIO(b'x'))
        return p
    def test_safe_tar(self):g.secure_extract_tar(self.make_tar('Release.xcarchive/Info.plist'),self.dir/'out')
    def test_preupload_tar_validation_does_not_extract(self):
        path=self.make_tar('Release.xcarchive/Info.plist')
        g.check_unsigned_artifact(path)
        self.assertEqual(set(self.dir.iterdir()),{path})
    def test_preupload_tar_expanded_limit_rejected(self):
        path=self.dir/'input.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            member=tarfile.TarInfo('Release.xcarchive/compressible');member.size=4096
            archive.addfile(member,io.BytesIO(b'\0'*4096))
        self.assertLess(path.stat().st_size,1024)
        with mock.patch.object(g,'MAX_EXPANDED_BYTES',1024),self.assertRaisesRegex(ValueError,'expanded-size'):g.check_unsigned_artifact(path)
    def test_preupload_tar_member_limit_rejected(self):
        path=self.dir/'input.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for name in ['first','second']:
                member=tarfile.TarInfo('Release.xcarchive/'+name);member.size=1
                archive.addfile(member,io.BytesIO(b'x'))
        with mock.patch.object(g,'MAX_ARCHIVE_MEMBERS',1),self.assertRaisesRegex(ValueError,'member-count'):g.check_unsigned_artifact(path)
    def test_preupload_tar_unsafe_contents_rejected(self):
        for name,kind in [('Release.xcarchive/../../outside',None),('Release.xcarchive/link','symlink'),('other/Info.plist',None)]:
            with self.subTest(name=name),self.assertRaises(ValueError):g.check_unsigned_artifact(self.make_tar(name,kind))
    def test_build_script_uses_complete_preupload_preflight(self):
        script=(BASE/'scripts/archive_unsigned.sh').read_text()
        self.assertIn('guard.py" check-unsigned-artifact ',script)
        self.assertNotIn('guard.py" check-artifact-size ',script)
    def test_tar_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):g.secure_extract_tar(self.make_tar('Release.xcarchive/../../outside'),self.dir/'out')
    def test_tar_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError,'Links'):g.secure_extract_tar(self.make_tar('Release.xcarchive/link','symlink'),self.dir/'out')
    def test_tar_wrong_root_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):g.secure_extract_tar(self.make_tar('other/Info.plist'),self.dir/'out')
    def test_zip_traversal_rejected(self):
        p=self.dir/'input.ipa'
        with zipfile.ZipFile(p,'w') as z:z.writestr('../outside','x')
        with self.assertRaisesRegex(ValueError,'Unsafe'):g.secure_extract_ipa(p,self.dir/'out')
    def app_fixture(self,bid='100mango.QRCatcher'):
        p=self.dir/'QRCatcher.app';p.mkdir();(p/'QRCatcher').write_bytes(b'fake binary')
        with (p/'Info.plist').open('wb') as f:plistlib.dump({'CFBundleIdentifier':bid,'CFBundleShortVersionString':'2.0','CFBundleVersion':'42','CFBundleSupportedPlatforms':['iPhoneOS'],'CFBundleExecutable':'QRCatcher'},f)
        return p
    def test_bundle_identity_and_version(self):self.assertEqual(g.inspect_app(self.r,self.app_fixture())['bundles'],['100mango.QRCatcher'])
    def test_wrong_bundle_rejected(self):
        with self.assertRaisesRegex(ValueError,'identity'):g.inspect_app(self.r,self.app_fixture('changed.identifier'))
    def celluloid_fixture(self):
        self.r['app']='Celluloid';self.r['repository']='100mango/Celluloid'
        inv=json.loads((BASE/'examples/Celluloid.release.example.json').read_text())['framework_inventory']
        inv.update(verified=True,source_commit='a'*40,ci_run_id=111,ci_run_attempt=1,review_reference='Synthetic unit-test inventory; not observed production facts')
        for f in inv['frameworks']: f.update(version='1.0',build='1')
        inv['frameworks'][1]['bundle_identifier']='org.fixture.synthetic-snapkit'
        self.r['framework_inventory']=inv
        return inv
    def test_missing_extension_rejected(self):
        self.celluloid_fixture()
        with self.assertRaisesRegex(ValueError,'Missing expected'):g.inspect_app(self.r,self.app_fixture('Mango.Celluloid'))
    def test_snapkit_exact_inventory_required(self):
        inv=self.celluloid_fixture();g.verified_framework_inventory(self.r)
        inv['frameworks'][1]['bundle_identifier']=None
        with self.assertRaisesRegex(ValueError,'Observed exact'):g.verified_framework_inventory(self.r)
    def test_snapkit_wildcard_identity_rejected(self):
        inv=self.celluloid_fixture();inv['frameworks'][1]['bundle_identifier']='org.*'
        with self.assertRaisesRegex(ValueError,'no wildcards'):g.verified_framework_inventory(self.r)
    def test_snapkit_wrong_pin_rejected(self):
        inv=self.celluloid_fixture();inv['frameworks'][1]['package']['revision']='f'*40
        with self.assertRaisesRegex(ValueError,'provenance'):g.verified_framework_inventory(self.r)
    def test_framework_metadata_never_defaults_to_app(self):
        inv=self.celluloid_fixture();del inv['frameworks'][1]['version']
        with self.assertRaisesRegex(ValueError,'no app-version fallback'):g.verified_framework_inventory(self.r)
    def test_snapkit_source_pins_verified(self):
        self.celluloid_fixture()
        pin={'identity':'snapkit','kind':'remoteSourceControl','location':g.SNAPKIT['repository'],'state':{'revision':g.SNAPKIT['revision'],'version':'5.7.1'}}
        for name in g.SNAPKIT['resolved_paths']:
            p=self.dir/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'version':2,'pins':[pin]}))
        g.verify_source_dependencies(self.r,self.dir)
        pin['state']['revision']='f'*40;p.write_text(json.dumps({'version':2,'pins':[pin]}))
        with self.assertRaisesRegex(ValueError,'lockfile'):g.verify_source_dependencies(self.r,self.dir)
    def full_celluloid_app(self):
        inv=self.celluloid_fixture();app=self.app_fixture('Mango.Celluloid')
        ext=app/'PlugIns'/'CelluloidPhotoExtension.appex';ext.mkdir(parents=True)
        info={'CFBundleIdentifier':'Mango.Celluloid.CelluloidPhotoExtension','CFBundleShortVersionString':'2.0','CFBundleVersion':'42','CFBundleSupportedPlatforms':['iPhoneOS'],'CFBundleExecutable':'Ext','NSExtension':{'NSExtensionPointIdentifier':'com.apple.photo-editing'}}
        (ext/'Ext').write_bytes(b'fixture')
        with (ext/'Info.plist').open('wb') as f:plistlib.dump(info,f)
        for row in inv['frameworks']:
            fw=app/'Frameworks'/row['directory'];fw.mkdir(parents=True)
            info={'CFBundleIdentifier':row['bundle_identifier'],'CFBundleShortVersionString':row['version'],'CFBundleVersion':row['build'],'CFBundleSupportedPlatforms':['iPhoneOS'],'CFBundleExecutable':'Framework'}
            (fw/'Framework').write_bytes(b'fixture')
            with (fw/'Info.plist').open('wb') as f:plistlib.dump(info,f)
        return app
    def test_framework_own_versions_are_accepted(self):
        app=self.full_celluloid_app();result=g.inspect_app(self.r,app)
        self.assertEqual(len(result['bundles']),4)
    def test_unexpected_framework_version_is_rejected(self):
        app=self.full_celluloid_app();p=app/'Frameworks'/g.SNAPKIT['product_directory']/'Info.plist'
        info=plistlib.loads(p.read_bytes());info['CFBundleVersion']='99';p.write_bytes(plistlib.dumps(info))
        with self.assertRaisesRegex(ValueError,'Version/build mismatch'):g.inspect_app(self.r,app)
    def test_unexpected_embedded_framework_is_rejected(self):
        app=self.full_celluloid_app();extra=app/'Frameworks'/'Extra.framework';extra.mkdir()
        (extra/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'unapproved.extra'}))
        with self.assertRaisesRegex(ValueError,'identity'):g.inspect_app(self.r,app)
    def test_workflow_is_manual_and_pinned(self):
        import yaml
        doc=yaml.safe_load(WORKFLOW_PATH.read_text())
        self.assertEqual(set(doc['on']),{'workflow_dispatch'})
        self.assertEqual(doc['on']['workflow_dispatch']['inputs']['mode']['default'],'dry-run')
        self.assertEqual(doc['permissions'],{'contents':'read','actions':'read'})
        for job in doc['jobs'].values():
            self.assertEqual(job['runs-on'],'xcode-27')
            for step in job['steps']:
                if 'uses' in step:self.assertRegex(step['uses'],r'^actions/[a-z-]+@[a-f0-9]{40}$')
        only_secret_steps=[s for job in doc['jobs'].values() for s in job['steps'] if 'secrets.' in json.dumps(s)]
        self.assertEqual(len(only_secret_steps),1)
        self.assertIn('Owner-approved cloud export',only_secret_steps[0]['name'])
        self.assertEqual(doc['jobs']['sign_or_upload']['environment'],'appstore-release')
        self.assertFalse(any('upload-artifact' in s.get('uses','') for s in doc['jobs']['sign_or_upload']['steps']))
    def test_signer_no_secret_print_or_upload_default(self):
        s=(BASE/'scripts/sign_export.sh').read_text()
        self.assertIn('trap cleanup EXIT',s)
        self.assertIn("trap 'exit 143' HUP TERM",s)
        self.assertNotIn('set -x',s)
        self.assertIn('if [ "$RELEASE_MODE" = upload ]',s)
        self.assertIn('unset ASC_PRIVATE_KEY_P8',s)
        self.assertIn('manageAppVersionAndBuildNumber', (BASE/'scripts/guard.py').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
