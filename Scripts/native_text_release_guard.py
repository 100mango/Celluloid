"""Reject native text qualification hooks from the actual Release extension binary."""
from pathlib import Path
MARKERS=(b'TextRenderProbe',b'textRenderProbe')
def qualified_extension_has_no_hooks(app):
    path=Path(app)/'Contents/PlugIns/CelluloidMacPhotosExtension.appex/Contents/MacOS/CelluloidMacPhotosExtension'
    return path.is_file() and not path.is_symlink() and not any(marker in path.read_bytes() for marker in MARKERS)
