"""Reject debug qualification hooks in two fixed actual Release extension files."""
import os
from pathlib import Path
import stat
import time

MARKERS = (b'TextRenderProbe', b'textRenderProbe',
           b'CELLULOID_EXTENSION_SELF_IDENTITY_V1', b'Celluloid.ExtensionSelfIdentity.1',
           b'photos-extension.self-identity', b'MacPhotoSelfIdentity',
           b'MacPhotoSelfIdentityCapture', b'MacPhotoSelfIdentityAccessibility',
           b'MacPhotoSelfIdentityAccessibilityView')
DIRECTORIES = ('Contents', 'PlugIns', 'CelluloidMacPhotosExtension.appex', 'Contents', 'MacOS')
EXECUTABLE = 'CelluloidMacPhotosExtension'
DEBUG_DYLIB = 'CelluloidMacPhotosExtension.debug.dylib'
MAX_BINARY_BYTES = 32 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
MAX_SECONDS = 10


def _snapshot(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _scan_binary(directory, name, required, check):
    check()
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        if required:
            raise ValueError('Missing Release extension executable')
        return None
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_BINARY_BYTES:
        raise ValueError('Invalid Release extension file')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        expected = _snapshot(before)
        if _snapshot(os.fstat(fd)) != expected:
            raise ValueError('Release file changed before reading')
        remaining, tail = before.st_size, b''
        overlap = max(map(len, MARKERS)) - 1
        while remaining:
            check()
            data = os.read(fd, min(CHUNK_BYTES, remaining))
            if not data:
                raise ValueError('Release file truncated')
            window = tail + data
            if any(marker in window for marker in MARKERS):
                raise ValueError('Debug hook in Release extension file')
            tail = window[-overlap:]
            remaining -= len(data)
        check()
        if os.read(fd, 1) or _snapshot(os.fstat(fd)) != expected:
            raise ValueError('Release file changed while reading')
        return expected
    finally:
        os.close(fd)


def qualified_extension_has_no_hooks(app):
    """Read only the fixed main binary and optional fixed debug dylib; fail closed."""
    descriptors, entries = [], []
    deadline = time.monotonic() + MAX_SECONDS

    def check():
        if time.monotonic() > deadline:
            raise ValueError('Release extension read budget exhausted')

    try:
        app = Path(app)
        root = os.open(app, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append((root, None))
        descriptors[-1] = (root, _snapshot(os.fstat(root)))
        directory = root
        for name in DIRECTORIES:
            check()
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            descriptors.append((child, None))
            before = _snapshot(os.fstat(child))
            descriptors[-1] = (child, before); entries.append((directory, name, before))
            directory = child
        for name, required in ((EXECUTABLE, True), (DEBUG_DYLIB, False)):
            entries.append((directory, name, _scan_binary(directory, name, required, check)))
        check()
        if _snapshot(os.stat(app, follow_symlinks=False)) != descriptors[0][1]:
            return False
        if any(_snapshot(os.fstat(fd)) != before for fd, before in descriptors):
            return False
        for parent, name, expected in entries:
            try:
                actual = _snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False))
            except FileNotFoundError:
                actual = None
            if actual != expected:
                return False
        check()
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        for fd, _ in reversed(descriptors):
            os.close(fd)
