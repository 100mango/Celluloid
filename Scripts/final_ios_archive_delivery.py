#!/usr/bin/env python3
"""Retain only the already-verified, unsigned Celluloid archive. No subprocesses.

The tar preserves executable modes. Its files are rehashed against the unchanged
package checker, then the complete tar is read back before upload admission.
This artifact is not signed, installable, or release/Store qualified.
"""
import hashlib
import os
from pathlib import Path
import stat
import tarfile
import time

import final_ios_archive as gate
import final_ios_archive_package as package

TAR_NAME = 'Celluloid-1.1.1-3-UNSIGNED-NOT-RELEASE-QUALIFIED.xcarchive.tar'
MANIFEST_NAME = 'source-manifest.json'
ARCHIVE_ROOT = 'Celluloid.xcarchive'
MAX_TAR = package.MAX_BYTES + 8_000_000
MAX_MANIFEST = 1_000_000
FALSE_FLAGS = ('release_qualified', 'signing_qualified', 'store_qualified',
               'native_ui_qualified', 'ios_photos_host_qualified', 'mac_qualified')


def check(deadline):
    gate.need(time.monotonic() < deadline, 'delivery-deadline-exhausted')


def admissible(report):
    gate.need(report.get('archive_qualified') is True
              and report.get('driver_process_cleanup_confirmed') is True
              and 'failure' not in report, 'delivery-requires-complete-archive-proof')
    gate.need(all(report.get(key) is False for key in FALSE_FLAGS), 'delivery-is-not-release-qualification')
    gate.need(report.get('product_sha') == gate.SOURCE and report.get('product_tree') == gate.TREE,
              'delivery-product-identity')
    before, after = report.get('source_before'), report.get('source_after')
    gate.need(type(before) is dict and before == after
              and before.get('product_sha') == gate.SOURCE and before.get('product_tree') == gate.TREE
              and before.get('control_sha') == report.get('control_sha')
              and before.get('run_id') == report.get('run_id')
              and before.get('run_attempt') == report.get('run_attempt'), 'delivery-source-binding')
    proof = report.get('package', {})
    gate.need(proof.get('unsigned_package_verified') is True
              and proof.get('all_processes_finalized') is True
              and proof.get('release_acceptance') is False
              and proof.get('signing_qualified') is False, 'delivery-package-proof')
    gate.need(report.get('graph_before') == report.get('graph_after') == proof.get('source_graph'),
              'delivery-source-graph')
    gate.need(proof.get('inventory_sha256') == gate.digest(gate.encoded(proof.get('files'))),
              'delivery-inventory-binding')
    return proof


class Reader:
    def __init__(self, stream, deadline):
        self.stream, self.deadline = stream, deadline
        self.digest, self.size = hashlib.sha256(), 0

    def read(self, count):
        check(self.deadline)
        gate.need(type(count) is int and 0 <= count <= 65536, 'delivery-read-bound')
        data = self.stream.read(count)
        self.digest.update(data); self.size += len(data)
        return data


class Writer:
    def __init__(self, stream, deadline):
        self.stream, self.deadline = stream, deadline
        self.digest, self.size = hashlib.sha256(), 0

    def write(self, data):
        check(self.deadline)
        gate.need(self.size + len(data) <= MAX_TAR, 'delivery-tar-size-cap')
        written = self.stream.write(data)
        gate.need(written == len(data), 'delivery-short-write')
        self.digest.update(data); self.size += written
        return written


def file_descriptor(path):
    parent = package.directory_fd(path.parent)
    try:
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)


def verify_tar(path, manifest, deadline):
    """Read, never extract; reject missing, duplicate, extra, linked, or changed members."""
    expected = {item['path']: item for item in manifest['members']}
    gate.need(len(expected) == len(manifest['members']) <= package.MAX_ENTRIES + 1, 'delivery-member-count')
    fd = file_descriptor(path)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        gate.need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                  and before.st_size == manifest['archive']['bytes'] <= MAX_TAR, 'delivery-tar-file')
        reader = Reader(stream, deadline)
        seen = set()
        with tarfile.open(fileobj=reader, mode='r|', bufsize=10240) as archive:
            for member in archive:
                check(deadline)
                gate.need(member.name in expected and member.name not in seen, 'delivery-unexpected-tar-member')
                row = expected[member.name]; seen.add(member.name)
                gate.need(member.mode == row['mode'] and not member.linkname
                          and member.uid == member.gid == 0 and not member.pax_headers,
                          'delivery-member-metadata')
                if row['type'] == 'directory':
                    gate.need(member.isdir() and member.size == 0, 'delivery-directory-type')
                else:
                    gate.need(member.isfile() and member.size == row['bytes'], 'delivery-file-type-size')
                    digest = hashlib.sha256(); size = 0
                    content = archive.extractfile(member)
                    gate.need(content is not None, 'delivery-missing-file-stream')
                    with content:
                        while size < member.size:
                            check(deadline)
                            chunk = content.read(min(65536, member.size - size))
                            gate.need(chunk, 'delivery-truncated-member')
                            digest.update(chunk); size += len(chunk)
                    gate.need(digest.hexdigest() == row['sha256'], 'delivery-member-checksum')
        # tarfile may read ahead; all bytes it consumed went through this reader.
        while reader.read(65536):
            pass
        gate.need(seen == set(expected) and reader.size == before.st_size
                  and reader.digest.hexdigest() == manifest['archive']['sha256'], 'delivery-tar-checksum')
        gate.need(package.snapshot(before) == package.snapshot(os.fstat(stream.fileno()))
                  == package.snapshot(os.stat(path, follow_symlinks=False)), 'delivery-tar-changed')
    check(deadline)


def retain(report, product, folder, deadline):
    proof = admissible(report)
    check(deadline)
    archive = Path(product) / package.ARCHIVE
    files, directories, snapshots, _ = package.inventory(archive, deadline)
    gate.need(files == proof['files'], 'delivery-archive-changed-after-proof')
    rows = {item['path']: item for item in files}
    members = []
    for relative in sorted(['', *directories, *rows]):
        identity = snapshots[relative]
        mode = stat.S_IMODE(identity[2])
        gate.need(mode & 0o7000 == 0, 'delivery-special-permissions')
        item = {'path': ARCHIVE_ROOT + ('/' + relative if relative else ''),
                'mode': mode, 'type': 'file' if relative in rows else 'directory'}
        if relative in rows:
            item.update(bytes=rows[relative]['bytes'], sha256=rows[relative]['sha256'])
        members.append(item)
    folder = Path(folder)
    folder.mkdir(mode=0o700)
    directory = package.directory_fd(folder); os.close(directory)
    partial = folder / (TAR_NAME + '.partial')
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            writer = Writer(stream, deadline)
            with tarfile.open(fileobj=writer, mode='w|', format=tarfile.USTAR_FORMAT, bufsize=10240) as output:
                for row in members:
                    check(deadline)
                    relative = row['path'][len(ARCHIVE_ROOT):].lstrip('/')
                    info = tarfile.TarInfo(row['path'])
                    info.mode, info.mtime = row['mode'], 0
                    if row['type'] == 'directory':
                        info.type = tarfile.DIRTYPE
                        output.addfile(info)
                        continue
                    info.size = row['bytes']
                    descriptor = file_descriptor(archive / relative)
                    with os.fdopen(descriptor, 'rb') as content:
                        gate.need(package.snapshot(os.fstat(content.fileno())) == snapshots[relative], 'delivery-file-replaced')
                        reader = Reader(content, deadline)
                        output.addfile(info, reader)
                        gate.need(reader.size == row['bytes'] and reader.digest.hexdigest() == row['sha256'], 'delivery-file-changed')
                        gate.need(package.snapshot(os.fstat(content.fileno())) == snapshots[relative], 'delivery-file-changed')
        package.unchanged(archive, snapshots, deadline)
        manifest = {'schema': 'Celluloid.UnsignedArchiveDelivery.1',
                    'scope': 'unsigned-package-diagnostic-only',
                    'source': report['source_after'], 'version': '1.1.1', 'build': '3',
                    'repository': '100mango/Celluloid', 'xcode': report['xcode'],
                    'dependency': proof['snapkit'],
                    'source_graph_sha256': gate.digest(gate.encoded(report['graph_after'])),
                    'verified_inventory_sha256': proof['inventory_sha256'],
                    'qualification': {key: False for key in FALSE_FLAGS},
                    'installable': False, 'distribution_ready': False,
                    'archive': {'file': TAR_NAME, 'root': ARCHIVE_ROOT, 'bytes': writer.size,
                                'sha256': writer.digest.hexdigest(), 'format': 'ustar'},
                    'members': members,
                    'notice': 'Unsigned diagnostic archive. No signing credentials or provisioning profiles. Not an IPA or App Store submission. Native UI, Photos-host, physical-device, signing and Store gates remain separate.'}
        verify_tar(partial, manifest, deadline)
        raw = gate.encoded(manifest)
        gate.need(len(raw) <= MAX_MANIFEST, 'delivery-manifest-size-cap')
        target = folder / MANIFEST_NAME
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        gate.need(gate.safe_read(target, MAX_MANIFEST) == raw, 'delivery-manifest-readback')
        # Atomic publication inside the freshly created evidence directory.
        gate.need(not (folder / TAR_NAME).exists(), 'delivery-target-already-exists')
        partial.rename(folder / TAR_NAME)
        check(deadline)
        return {'manifest': MANIFEST_NAME, 'manifest_sha256': gate.digest(raw),
                'archive': manifest['archive'], 'readback_verified': True,
                'unsigned': True, 'release_qualified': False}
    except BaseException:
        # Only names created by this retention operation; no source deletion.
        for name in (TAR_NAME + '.partial', TAR_NAME, MANIFEST_NAME):
            (folder / name).unlink(missing_ok=True)
        raise


def verify_retained(report, folder, deadline):
    admissible(report)
    receipt = report.get('archive_delivery', {})
    gate.need(report.get('binary_handoff') is True and receipt.get('readback_verified') is True
              and receipt.get('unsigned') is True and receipt.get('release_qualified') is False,
              'delivery-missing-receipt')
    raw = gate.safe_read(Path(folder) / MANIFEST_NAME, MAX_MANIFEST)
    gate.need(gate.digest(raw) == receipt.get('manifest_sha256'), 'delivery-manifest-checksum')
    manifest = gate.strict_json(raw)
    gate.need(manifest.get('schema') == 'Celluloid.UnsignedArchiveDelivery.1'
              and manifest.get('source') == report['source_after']
              and manifest.get('archive') == receipt.get('archive')
              and manifest.get('qualification') == {key: False for key in FALSE_FLAGS}
              and manifest.get('installable') is False and manifest.get('distribution_ready') is False,
              'delivery-manifest-identity')
    gate.need(set(p.name for p in Path(folder).iterdir()) == {'report.json', MANIFEST_NAME, TAR_NAME},
              'delivery-evidence-members')
    verify_tar(Path(folder) / TAR_NAME, manifest, deadline)
