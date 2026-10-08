"""Portable post-test readback fixtures, including simulator reinstall relocation."""
import plistlib,hashlib,subprocess,tempfile,unittest
from pathlib import Path
from uikit_installed_identity import readback,validate
class InstalledIdentityTests(unittest.TestCase):
    UDID='12345678-1234-1234-1234-123456789AB0'
    def fixture(self,root):
        app=root.resolve()/('Devices/'+self.UDID+'/data/Containers/Bundle/Application/NEW/Celluloid.app');app.mkdir(parents=True)
        identity={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','DTPlatformName':'iphonesimulator'}
        (app/'Info.plist').write_bytes(plistlib.dumps(identity));(app/'Celluloid').write_bytes(b'actual exact compiled binary')
        staging={'binary_sha256':hashlib.sha256((app/'Celluloid').read_bytes()).hexdigest(),'installed_app':str(app).replace('/NEW/','/OLD/')}
        return app,staging
    def test_one_bounded_lookup_binds_relocated_actual_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            app,staging=self.fixture(Path(folder));calls=[]
            def run(args,**kwargs):calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,str(app)+'\n','')
            row=readback(run,self.UDID,staging);validate(row,self.UDID,staging)
            self.assertTrue(row['relocated_since_initial_staging']);self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][1]['timeout'],60);self.assertEqual(calls[0][0][-2:],['Mango.Celluloid','app'])
    def test_missing_wrong_device_product_or_binary_fails_without_retry(self):
        for change in ['binary','device','metadata','missing']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                app,staging=self.fixture(Path(folder));calls=[]
                if change=='binary':(app/'Celluloid').write_bytes(b'changed')
                if change=='metadata':(app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'other'}))
                path=str(app).replace(self.UDID,'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF') if change=='device' else str(app/'missing') if change=='missing' else str(app)
                def run(args,**kwargs):calls.append(args);return subprocess.CompletedProcess(args,0,path,'')
                with self.assertRaises((ValueError,FileNotFoundError)):readback(run,self.UDID,staging)
                self.assertEqual(len(calls),1)
    def test_timeout_does_not_retry(self):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs));raise TimeoutError('bounded post-test lookup')
        with self.assertRaises(TimeoutError):readback(run,self.UDID,{})
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][1]['timeout'],60)

    def test_receipt_rejects_forged_relocation_retry_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            app,staging=self.fixture(Path(folder))
            row=readback(lambda args,**kw:subprocess.CompletedProcess(args,0,str(app),''),self.UDID,staging)
            for field,value in [('relocated_since_initial_staging',False),('lookup_count',True),('lookup_count',2),('lookup_timeout_seconds',float('inf')),('binary_sha256','f'*64),('device_id','wrong'),('app_path',str(app).replace('/NEW/','/IGNORED/../NEW/'))]:
                bad=dict(row);bad[field]=value
                with self.subTest(field=field),self.assertRaises(ValueError):validate(bad,self.UDID,staging)
if __name__=='__main__':unittest.main()
