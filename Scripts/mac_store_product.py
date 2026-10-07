"""Fixed Celluloid Debug product/path binding; no launch code."""
import hashlib
from pathlib import Path
import plistlib
from mac_store_io import read_file, require
def digest(raw):return hashlib.sha256(raw).hexdigest()

def base_command():
    return ['xcodebuild', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidMacUI',
        '-configuration', 'Debug', '-destination', 'platform=macOS,arch=arm64',
        '-derivedDataPath', 'build/mac-tests', 'ARCHS=arm64', 'CODE_SIGNING_ALLOWED=NO']

def product_identity():
    app = Path('build/mac-tests/Build/Products/Debug/CelluloidMac.app').absolute()
    require(app.resolve() == app and app.is_dir() and not app.is_symlink(), 'unsafe-product-path')
    metadata = plistlib.loads(read_file(app / 'Contents/Info.plist', 128 * 1024))
    require(metadata.get('CFBundleIdentifier') == 'Mango.Celluloid' and metadata.get('CFBundleExecutable') == 'CelluloidMac', 'wrong-product')
    executable = app / 'Contents/MacOS/CelluloidMac'
    logic = app / 'Contents/MacOS/CelluloidMac.debug.dylib'
    require(executable.resolve() == executable and logic.resolve() == logic, 'linked-product')
    return {'applicationPath': str(app), 'executable': str(executable),
        'executableSHA256': digest(read_file(executable, 16 * 1024 * 1024)),
        'logicSHA256': digest(read_file(logic, 16 * 1024 * 1024))}
