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
