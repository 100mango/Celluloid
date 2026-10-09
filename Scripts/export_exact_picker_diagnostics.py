#!/usr/bin/env python3
"""Read-only official export. No simulator, compile, test, signing or receipt pass."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, subprocess, sys, tempfile, zipfile
import picker_native_receipt as receipt

SOURCE = '9c85361da5fd26ac63a43c12813171c185928e1f'
TREE = '281e8d7763cb1b36a6d6422a90c735e6c6d712c6'
RUN = 37880596540
ARTIFACT = 11594561882
DIGEST = '58f86936e585e1d1c8bbba652f01cb040b834d97fe1282a4f4435de6fe44f382'
OUT = Path('build/exact-picker-diagnostics')


def require(value, message):
    if not value: raise ValueError(message)


def main():
    require(sys.platform == 'darwin', 'Official xcresult export requires the cloud Xcode runner')
    require(os.environ.get('GITHUB_REPOSITORY') == '100mango/Celluloid', 'Wrong repository')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/cell-receipt-diagnostics', 'Wrong export branch')
    require(os.environ.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong toolchain')
    require(not OUT.exists(), 'Refusing stale export')
    OUT.mkdir(parents=True)
    manifest = {'source_sha': SOURCE, 'source_tree': TREE, 'original_run': RUN, 'original_artifact': ARTIFACT,
                'artifact_sha256': DIGEST, 'export_commit': os.environ['GITHUB_SHA'], 'official_exports': {},
                'native_tests_rerun': False, 'release_qualification': False}
    (OUT/'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    version = subprocess.check_output(['xcodebuild', '-version'], text=True, timeout=20)
    require('Xcode 27.0' in version.splitlines(), 'Wrong stable Xcode')
    (OUT/'xcode-version.txt').write_text(version)
    with tempfile.TemporaryDirectory(prefix='celluloid-readonly-export-') as temp:
        temp = Path(temp); archive = temp/'source.zip'
        # gh follows GitHub's authenticated artifact redirect without logging the token.
        with archive.open('wb') as stream:
            subprocess.run(['gh', 'api', f'repos/100mango/Celluloid/actions/artifacts/{ARTIFACT}/zip'],
                           stdout=stream, check=True, timeout=45)
        require(archive.stat().st_size == 4113061 and receipt.sha256_file(archive) == DIGEST, 'Artifact bytes mismatch')
        with zipfile.ZipFile(archive) as z:
            require(z.read('swiftui-source.txt').decode().splitlines() == [SOURCE, TREE], 'Original checkout identity mismatch')
            keep = []
            for item in z.infolist():
                p = PurePosixPath(item.filename)
                require(not p.is_absolute() and '..' not in p.parts, 'Unsafe artifact member')
                if any(item.filename.startswith('swiftui-acceptance/picker-'+phase+'.xcresult/') for phase in ('stock','seeded')):
                    require(item.file_size < 64*1024*1024 and (item.external_attr >> 16) & 0o170000 != 0o120000, 'Unsafe/oversized member')
                    keep.append(item)
            require(keep and sum(x.file_size for x in keep) < 256*1024*1024, 'Oversized/empty evidence')
            for item in keep: z.extract(item, temp)
            for phase in ('stock', 'seeded'):
                name = 'picker-'+phase
                for suffix in ('identity.json', 'summary.json', 'native-receipt.json', 'ui.log'):
                    (OUT/(name+'-'+suffix)).write_bytes(z.read('swiftui-acceptance/'+name+'-'+suffix))
        total = 0
        for phase in ('stock', 'seeded'):
            name = 'picker-'+phase; bundle = temp/'swiftui-acceptance'/(name+'.xcresult')
            identity = json.loads((OUT/(name+'-identity.json')).read_text())
            require(identity['source_sha'] == SOURCE and identity['source_tree'] == TREE, 'Receipt source mismatch')
            require(receipt.bundle_digest(bundle) == identity['xcresult_sha256'], 'Result bundle hash mismatch')
            exported = temp/(name+'-official-export')
            method = receipt.export_diagnostics(bundle, exported)
            logs = receipt.read_diagnostics(exported)
            rows=[]; destination=OUT/name; destination.mkdir()
            for index, (original, text) in enumerate(sorted(logs.items())):
                data=text.encode(); total += len(data)
                require(total <= 64*1024*1024, 'Relevant text evidence exceeds bound')
                filename=f'log-{index:03d}.txt'; (destination/filename).write_bytes(data)
                rows.append({'file':name+'/'+filename, 'exported_relative_path':original,
                             'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()})
            manifest['official_exports'][phase]={'method':method,'logs':rows,'xcresult_sha256':identity['xcresult_sha256']}
            (OUT/'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    subprocess.run(['git','diff','--exit-code','HEAD','--'], check=True, timeout=15)
    print(json.dumps({'status':'official-diagnostics-exported','native_tests_rerun':False,'source_sha':SOURCE}))


if __name__ == '__main__': main()
