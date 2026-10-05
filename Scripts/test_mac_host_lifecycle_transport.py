"""Fixed-name, exact-test PNG attachment and actual-byte read bounds."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest import mock
import mac_host_transport as t
from mac_host_lifecycle_pixels import read_owned_png,PNG_LIMIT,NAMES
from test_mac_host_lifecycle_pixels import encode

class LifecycleAttachmentTests(unittest.TestCase):
    def manifest(self,name=NAMES[0],test=None,exported='owned.png'):
        stem=name.removesuffix('.png')
        return [{'testIdentifier':test or 'MacPhotosHostUITests/'+t.CASE[1]+'()',
            'attachments':[{'suggestedHumanReadableName':t.LIFECYCLE_PREFIX+stem+'_0_12345678-1234-4321-8123-123456789ABC.png','exportedFileName':exported}]}]
    def test_all_five_exact_names_types_and_test_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned.png').write_bytes(encode())
            for name in NAMES:
                self.assertEqual(t.attachment_candidates(root,self.manifest(name)),{name:encode()})
    def test_wrong_name_suffix_owner_path_duplicates_and_non_png_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned.png').write_bytes(encode())
            variants=[self.manifest('lifecycle-arbitrary.png'),self.manifest(test='OtherTests/testOther()'),self.manifest(exported='../owned.png')]
            row=self.manifest();row[0]['attachments'][0]['suggestedHumanReadableName']=row[0]['attachments'][0]['suggestedHumanReadableName'].replace('_0_','_1_');variants.append(row)
            row=self.manifest();row[0]['attachments']*=2;variants.append(row)
            for value in variants:
                with self.assertRaises(ValueError):t.attachment_candidates(root,value)
            (root/'owned.png').write_bytes(b'not png')
            with self.assertRaises(ValueError):t.attachment_candidates(root,self.manifest())
    def test_oversize_symlink_hardlink_fifo_and_directory_fail_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'owned.png'
            with file.open('wb') as stream:stream.truncate(PNG_LIMIT+1)
            with mock.patch('mac_host_lifecycle_pixels.os.read') as read:
                with self.assertRaises(ValueError):read_owned_png(file)
                read.assert_not_called()
            file.unlink();os.mkfifo(file)
            with self.assertRaises(ValueError):read_owned_png(file)
            file.unlink();file.mkdir()
            with self.assertRaises(ValueError):read_owned_png(file)
            file.rmdir();file.symlink_to(root/'missing')
            with self.assertRaises(OSError):read_owned_png(file)
            file.unlink();file.write_bytes(encode());os.link(file,root/'second')
            with self.assertRaises(ValueError):read_owned_png(file)
    def test_mutation_read_count_and_descriptor_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'owned.png';data=b'x'*PNG_LIMIT;file.write_bytes(data)
            actual=os.read;count=0;changed=False
            def read(fd,n):
                nonlocal count,changed
                value=actual(fd,n);count+=len(value)
                if not changed:
                    changed=True
                    with file.open('ab') as stream:stream.write(b'extra')
                return value
            with mock.patch('mac_host_lifecycle_pixels.os.read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'changed'):read_owned_png(file)
            self.assertEqual(count,PNG_LIMIT)
            file.write_bytes(data);opened=[];closed=[];original_open=os.open;original_close=os.close
            def op(*a,**k):
                fd=original_open(*a,**k);opened.append(fd);return fd
            def close(fd):closed.append(fd);return original_close(fd)
            with mock.patch('mac_host_lifecycle_pixels.os.open',side_effect=op),mock.patch('mac_host_lifecycle_pixels.os.close',side_effect=close),mock.patch('mac_host_lifecycle_pixels.os.read',side_effect=OSError('read failed')):
                with self.assertRaises(OSError):read_owned_png(file)
            self.assertEqual(opened,closed)

if __name__=='__main__':unittest.main()
