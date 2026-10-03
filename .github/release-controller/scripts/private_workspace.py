"""Own and remove only a newly created ephemeral signing workspace.

This module never reads credentials or removes provisioning-profile directories.
Environment checks prevent accidental use outside the fixed hosted-runner workflow;
they are not an authentication mechanism against a malicious environment owner.
"""
from __future__ import annotations
import argparse, json, os, pathlib, re, shutil, stat, sys, tempfile

MARKER = '.release-workspace.json'
MARKER_VALUE = {'schema_version': 1, 'purpose': 'ephemeral-release-workspace'}

def require_hosted_runner(environment):
    expected = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'macOS'}
    if any(environment.get(key) != value for key, value in expected.items()):
        raise ValueError('Hosted macOS runner required')

def checked_root(value):
    root = pathlib.Path(value)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid runner temporary root')
    resolved = root.resolve(strict=True)
    if root != resolved or resolved == pathlib.Path('/'):
        raise ValueError('Canonical runner temporary root required')
    return resolved

def create(root_value):
    root = checked_root(root_value)
    folder = pathlib.Path(tempfile.mkdtemp(prefix='cloud-signing.', dir=root))
    folder.chmod(0o700)
    marker = folder / MARKER
    with marker.open('x') as stream:
        json.dump(MARKER_VALUE, stream, sort_keys=True)
    marker.chmod(0o600)
    return folder

def cleanup(root_value, workspace_value):
    root = checked_root(root_value)
    folder = pathlib.Path(workspace_value)
    if not folder.is_absolute() or folder.parent != root or not re.fullmatch(r'cloud-signing\.[A-Za-z0-9_-]{8}', folder.name):
        raise ValueError('Workspace is outside its owned temporary root')
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError('Descriptor-safe cleanup is unavailable')
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            info = os.stat(folder.name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('Workspace ownership or mode mismatch')
        folder_fd = os.open(folder.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            opened = os.fstat(folder_fd)
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError('Workspace changed before validation')
            marker_fd = os.open(MARKER, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder_fd)
            with os.fdopen(marker_fd, 'rb') as stream:
                marker_info = os.fstat(stream.fileno())
                if not stat.S_ISREG(marker_info.st_mode) or marker_info.st_nlink != 1 or marker_info.st_uid != os.geteuid() or marker_info.st_size > 256 or stat.S_IMODE(marker_info.st_mode) != 0o600:
                    raise ValueError('Invalid workspace ownership marker')
                payload = stream.read(257)
            if len(payload) > 256 or json.loads(payload) != MARKER_VALUE:
                raise ValueError('Workspace was not created by this helper')
            current = os.stat(folder.name, dir_fd=root_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError('Workspace changed during validation')
        finally:
            os.close(folder_fd)
        # Pin the parent directory; fd-based rmtree also refuses a symlink swapped
        # into the workspace entry and never follows nested symlink targets.
        shutil.rmtree(folder.name, dir_fd=root_fd)
    finally:
        os.close(root_fd)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check-runner', 'create', 'cleanup'])
    parser.add_argument('--root')
    parser.add_argument('--workspace')
    args = parser.parse_args()
    require_hosted_runner(os.environ)
    if args.action == 'check-runner':
        return
    if not args.root:
        raise ValueError('Temporary root is required')
    if args.action == 'create':
        print(create(args.root))
    elif args.workspace:
        cleanup(args.root, args.workspace)
    else:
        raise ValueError('Owned workspace is required')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No environment values, paths, filenames, or key contents in diagnostics.
        print('SIGNING_WORKSPACE_GUARD_FAILED', file=sys.stderr)
        sys.exit(1)
