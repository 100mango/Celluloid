"""Immutable historical source fixtures for guards retired from this staged route."""
from contextlib import contextmanager
from pathlib import Path
import subprocess,tempfile
from original_ios_source_contract import ROOT,BASE

@contextmanager
def historical_checkout():
    # Local object sharing only. No network, credentials, publication or CI.
    with tempfile.TemporaryDirectory(prefix='celluloid-historical-source-') as folder:
        root=Path(folder)/'checkout'
        subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(ROOT),str(root)],check=True,capture_output=True,timeout=20)
        subprocess.run(['git','checkout','--quiet','--detach',BASE],cwd=root,check=True,capture_output=True,timeout=20)
        tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip()
        if tree!='67ee79704e23936ba451173ce8aa68614b1ec1da':raise ValueError('Changed historical source fixture')
        yield root


def qualified_staged_row_workflow():
    """Keep executed row-helper regressions tied to their immutable da9d flow."""
    import hashlib
    raw=subprocess.check_output(['git','show','da9d4abd6484ddaff469677d96caf24362645d7c:.github/workflows/original-ios-release.yml'],cwd=ROOT,timeout=5)
    if len(raw)!=50167 or hashlib.sha256(raw).hexdigest()!='b35a4c06656d86bed3142e0752a27f06675bbe13e8458bb0bae4f7ae24cc0118':raise ValueError('Changed qualified staged row workflow fixture')
    return raw.decode('utf8')
