#!/usr/bin/env python3
"""One immutable-product Vision UI method; no matrix, retry, archive or signing."""
from pathlib import Path
import argparse,hashlib,json,math,os,re,selectors,signal,stat,struct,subprocess,sys,time,zlib
from qualify_final_vision_wave_source import CONFIG,SOURCE,TREE,UI_METHODS,CONTROL_PATHS,DIAGNOSTIC_TEST,DIAGNOSTIC_TEST_SHA256,ORIGINAL_TEST_SHA256
ROOT=Path(__file__).resolve().parents[1]
CLOCK='final-vision-wave-clock.json'
UI_SECONDS=900
MAX_OUTPUT=1048576
from combined_evidence_budget import BUDGETS
MAX_EVIDENCE=BUDGETS['vision']
HOSTED=('testNativeVisionDocumentImportRenderSaveReopenAndExport','testSharedFieldMutationsRetainUnicodeAcrossBothOrdersUndoAndReopen','testPrepareVisionRemainingDocumentFixture','testNativeVisionExecutableAndSceneAreLive')
PRODUCER='testPrepareVisionRemainingDocumentFixture'
SHOTS={UI_METHODS[0]:('native-vision-launch','native-vision-editor-ready'),UI_METHODS[1]:('vision-imported-editable-bubble','vision-png-export-verified','vision-saved-document-reopened'),UI_METHODS[2]:(),UI_METHODS[3]:('vision-zh-Hans-privacy',)}
DEPENDENCIES={UI_METHODS[0]:'ui-created-document',UI_METHODS[1]:'own-generated-png',UI_METHODS[2]:'hosted-producer-package',UI_METHODS[3]:'ui-created-document'}
def need(value,reason):
 if not value:raise ValueError(reason)
check=need
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def strict_json(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'duplicate-json-key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite-json')))

# Exact no-follow reader copied from the reviewed final-TV control.
def safe_read(path, cap):
    path = Path(path).absolute()
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= cap, 'unsafe-input')
        raw = b''
        while len(raw) < before.st_size:
            part = os.read(descriptor, min(65536, before.st_size - len(raw)))
            need(part, 'truncated-input'); raw += part
        def identity(value):
            return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns
        need(identity(before) == identity(os.fstat(descriptor)) == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'changed-input')
        return raw
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


# Owned-session helper reused from the fixed source/final-TV control; only the output ceiling is1MiB for Vision AX logs.
def number(value):
    return (type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))

def bounded_optional_process(command,command_deadline,cleanup_deadline,cap=8192,*,stop_on_signal_error=False):
    """One owned session; finite reads and absolute deadlines, including pipe EOF.

    Do not poll/reap the leader while a descendant can retain the pipe. Its PID
    stays reserved until group cleanup, so a signal cannot target a reused PID.
    No change is made to the mandatory host command or shared run_bounded helper.
    """
    check(number(command_deadline) and number(cleanup_deadline) and time.monotonic()<command_deadline<cleanup_deadline,'Invalid/expired optional process deadlines')
    check(type(cap) is int and 0<cap<=1048576,'Invalid optional output cap')
    check(type(stop_on_signal_error) is bool,'Invalid signal cleanup policy')
    check(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'Unknown child-reaping policy')
    started=time.monotonic();data=bytearray();eof=False;reaped=False;timed_out=False;overflow=False;cleanup_error=None
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    selector=None;pipe=process.stdout
    class SignalCleanupStopped(Exception):pass
    def drain(until):
        nonlocal eof,overflow
        while not eof and not overflow and time.monotonic()<until:
            if len(data)>=cap:overflow=True;break
            events=selector.select(max(0,min(0.1,until-time.monotonic())))
            for _,_ in events:
                if time.monotonic()>=until:break
                try:part=os.read(pipe.fileno(),min(4096,cap-len(data)))
                except BlockingIOError:continue
                if not part:eof=True;break
                data.extend(part)
    def signal_group(sig):
        nonlocal cleanup_error
        if reaped:return # Never signal after releasing the leader's PID.
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:
            cleanup_error=type(error).__name__
            if stop_on_signal_error:raise SignalCleanupStopped() from error
    try:
        selector=selectors.DefaultSelector()
        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
        drain(command_deadline)
        if eof and not overflow:
            try:process.wait(timeout=max(0,command_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:timed_out=True
        else:timed_out=not overflow
        if not reaped:
            signal_group(signal.SIGTERM)
            term_deadline=min(cleanup_deadline,time.monotonic()+1)
            if not overflow:drain(term_deadline)
            # A completed leader may leave an ignoring descendant with the pipe.
            # Signal the same owned session before reaping that leader.
            signal_group(signal.SIGKILL)
            if not overflow:drain(cleanup_deadline)
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:cleanup_error='direct child unreaped at absolute deadline'
    except SignalCleanupStopped:
        pass # Fixed staged metadata reads never switch signals after denial.
    except (OSError,ValueError) as error:
        cleanup_error=type(error).__name__
        try:signal_group(signal.SIGKILL)
        except SignalCleanupStopped:pass
        else:
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:pass
    finally:
        if selector is not None:selector.close()
        pipe.close()
    finished=time.monotonic()
    if finished>command_deadline and not overflow:timed_out=True
    if finished>cleanup_deadline:cleanup_error='completion observed after absolute cleanup deadline'
    return {'return_code':process.returncode,'output':bytes(data),'bytes_read':len(data),'pipe_eof':eof,
        'child_reaped':reaped,'timed_out':timed_out,'overflow':overflow,'cleanup_error':cleanup_error,
        'finalized':eof and reaped and cleanup_error is None,'elapsed_seconds':finished-started,
        'command_deadline_monotonic':command_deadline,'cleanup_deadline_monotonic':cleanup_deadline}

# All time is measured from the first workflow step, before checkout.
NATIVE_SECONDS=1560
FINAL_SECONDS=1740
CLEANUP_RESERVE=120

def validate_config(c,env,enabled=True):
 keys={'schema','READY','platform','product_parent_sha','product_parent_tree','maximum_additional_spend_usd','confirmation','selected_method'}
 need(type(c) is dict and set(c)==keys,'config-fields')
 need(type(c['schema']) is int and c['schema']==1 and c['READY'] is enabled,'closed-or-schema')
 need(c['platform']=='vision' and c['product_parent_sha']==SOURCE and c['product_parent_tree']==TREE,'fixed-product')
 need(type(c['maximum_additional_spend_usd']) is int and c['maximum_additional_spend_usd']==0 and c['confirmation']=='RUN_ONE_UNSIGNED_PLATFORM_ZERO_USD','zero-dollar-confirmation')
 need(c['selected_method'] in UI_METHODS and env.get('VISION_WAVE_METHOD')==c['selected_method'],'single-whole-method')
 need(env.get('QUALIFICATION_PLATFORM')=='vision' and env.get('GITHUB_RUN_ATTEMPT')=='1','platform-or-attempt')
 return c

def validate_clock(c,env,now=None):
 need(type(c) is dict and set(c)=={'schema','control_sha','run_id','run_attempt','selected_method','started_monotonic','started_unix','native_seconds','final_seconds'},'clock-fields')
 need(c['schema']=='Celluloid.FinalVisionWaveClock.1','clock-schema')
 for field,key in [('control_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('selected_method','VISION_WAVE_METHOD')]:need(c[field]==env.get(key),'clock-identity-'+field)
 need(type(c['native_seconds']) is int and c['native_seconds']==NATIVE_SECONDS and type(c['final_seconds']) is int and c['final_seconds']==FINAL_SECONDS,'clock-budget')
 now=time.monotonic() if now is None else now
 for v in [c['started_monotonic'],c['started_unix'],now]:need(type(v) in (int,float) and math.isfinite(v) and v>0,'clock-number')
 need(c['started_monotonic']<=now,'clock-future')
 return c

def selectors_for(method):
 need(method in UI_METHODS,'unknown-ui-method')
 return {'ui':['-only-testing:CelluloidVisionUITests/NativeVisionUITests/'+method],
         'producer':['-only-testing:CelluloidVisionTests/NativeVisionTests/'+PRODUCER] if DEPENDENCIES[method]=='hosted-producer-package' else []}

def admit_ui(clock,now=None):
 now=time.monotonic() if now is None else now
 deadline=clock['started_monotonic']+NATIVE_SECONDS-CLEANUP_RESERVE-FIXTURE_READ_SECONDS
 need(now+UI_SECONDS+15<=deadline,'full-900-second-ui-plus-cleanup-does-not-fit')
 return deadline

def inspect_case(log,method,summary,kind='ui',udid=None,runtime_version=None):
 owner='CelluloidVisionUITests.NativeVisionUITests' if kind=='ui' else 'CelluloidVisionTests.NativeVisionTests'
 events=[]
 for line in log.splitlines():
  if line.startswith('Test Case '):
   m=re.fullmatch(r"Test Case '-\[([\w.]+) (\w+)\]' (started\.|(?:passed|failed|skipped) \([0-9.]+ seconds\)\.)",line)
   need(m is not None,'malformed-case-event')
   need((m[1],m[2])==(owner,method),'unexpected-case-executed')
   events.append(m[3].split()[0].rstrip('.'))
 need(events==['started','passed'],'selected-case-missing-failed-skipped-or-duplicate')
 for key,value in [('totalTestCount',1),('passedTests',1),('failedTests',0),('skippedTests',0)]:need(type(summary.get(key)) is int and summary[key]==value,'summary-'+key)
 need(not summary.get('testFailures') and summary.get('expectedFailures',0)==0,'summary-failures')
 if udid is not None:
  rows=summary.get('devicesAndConfigurations');need(type(rows) is list and len(rows)==1,'summary-device-count')
  device=rows[0].get('device',{});need(device.get('deviceId')==udid and device.get('osVersion')==runtime_version and device.get('architecture')=='arm64' and device.get('platform') in {'visionOS Simulator','xrOS Simulator'},'summary-runtime-binding')
  for k,v in [('passedTests',1),('failedTests',0),('skippedTests',0)]:need(type(rows[0].get(k)) is int and rows[0][k]==v,'summary-device-'+k)
 return {'method':method,'kind':kind,'events':events,'passed':True,'summary_counts':{k:summary[k] for k in ['totalTestCount','passedTests','failedTests','skippedTests']}}

def verify_producer(log,container):
 lines=[line.split(' ',1)[1] for line in log.splitlines() if line.startswith('VISION_REMAINING_FIXTURE_JSON ')]
 need(len(lines)==1,'one-producer-marker-required');v=strict_json(lines[0]);container=Path(container).resolve(strict=True)
 need(v.get('schema')=='Celluloid.VisionFixture.1' and v.get('bundle_identifier')=='Mango.Celluloid','producer-identity')
 need(v.get('pixel_width')==120 and v.get('pixel_height')==80 and v.get('initial_overlays')==0 and v.get('package_name')=='VisionRemaining.celluloid','producer-shape')
 need(Path(v.get('data_home','')).resolve(strict=True)==container,'producer-not-current-owned-container')
 docs=container/'Documents';package=docs/'VisionRemaining.celluloid'
 need(Path(v.get('documents_path','')).resolve(strict=True)==docs and Path(v.get('package_path','')).resolve(strict=True)==package,'producer-package-location')
 need(package.is_dir() and not package.is_symlink(),'producer-directory')
 files=v.get('files');need(type(files) is list and len(files)==2,'producer-file-count')
 names=[]
 for f in files:
  need(type(f) is dict and set(f)=={'name','bytes','sha256'},'producer-file-fields');name=f['name']
  need(type(name) is str and Path(name).name==name and (name=='recipe.json' or re.fullmatch(r'[0-9A-Fa-f-]{36}\.image',name)),'producer-file-name')
  need(name not in names and type(f['bytes']) is int and 0<f['bytes']<=1000000 and re.fullmatch('[0-9a-f]{64}',f['sha256']) is not None,'producer-file-identity');names.append(name)
  b=safe_read(package/name,1000000);need(len(b)==f['bytes'] and digest(b)==f['sha256'],'producer-file-hash')
 need('recipe.json' in names and sorted(p.name for p in package.iterdir())==sorted(names),'producer-exact-inventory')
 return v

def seed_png(container):
 documents=Path(container).resolve(strict=True)/'Documents';documents.mkdir(exist_ok=True)
 need(not documents.is_symlink(),'documents-symlink')
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 row=b''.join(bytes((240,40,30,255)) if x<600 else bytes((30,110,240,255)) for x in range(1200))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+row)*800))+chunk(b'IEND',b'')
 path=documents/'VisionSynthetic.png'
 with path.open('xb') as f:f.write(png)
 need(safe_read(path,1000000)==png,'png-readback')
 return {'path':str(path),'bytes':len(png),'sha256':digest(png),'width':1200,'height':800,'original_runner_algorithm_unchanged':True}

def print_command_receipt(phase,label,argv,started,result=None):
 # Only executable basename and fixed status fields; never argv, environment or output.
 receipt={'phase':phase,'label':label,'executable':Path(str(argv[0])).name,'started_monotonic':started,'observed_monotonic':time.monotonic()}
 if result is not None:
  for k in ['return_code','timed_out','overflow','finalized','pipe_eof','child_reaped','cleanup_error','elapsed_seconds','exception']:
   if k in result:receipt[k]=result[k]
 raw=json.dumps(receipt,sort_keys=True,allow_nan=False);need(len(raw.encode())<=1024,'command-receipt-cap')
 print('VISION_WAVE_COMMAND '+raw,flush=True)

# BEGIN_OWNED_FIXTURE_READER
"""Read one newly-created package in a disposable, controller-owned simulator.

Diagnostic only. No native commands, writes, directory recursion, save request,
retry, sleep, or qualification decision. The controller must establish ownership
of devices_root/owned_udid/container_path; path shape is not proof of ownership.
Keep the initial receipt in trusted controller memory, not app-controlled JSON.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import PurePosixPath
import re
import stat
import struct
import time
import uuid


SCHEMA = "Celluloid.OwnedVisionFixtureDiagnostic.1"
RECEIPT_SCHEMA = "Celluloid.OwnedVisionFixtureInitial.1"
PNG_NAME = "VisionSynthetic.png"
EXPORT_NAME = "Celluloid.png"
MAX_PNG = 1_000_000
MAX_RECIPE = 262_144
MAX_REPORT = 65_536
MAX_READ_SECONDS = 5
UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}\Z")


class FixtureReadError(ValueError):
    pass


def _need(condition, code):
    if not condition:
        raise FixtureReadError(code)


def _uuid(value):
    _need(type(value) is str and UUID_RE.fullmatch(value), "invalid-uuid")
    return str(uuid.UUID(value)).upper()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _identity(st):
    return {"device": st.st_dev, "inode": st.st_ino}


def _fingerprint(st):
    return {**_identity(st), "mode": st.st_mode, "links": st.st_nlink,
            "bytes": st.st_size, "mtime_ns": st.st_mtime_ns,
            "ctime_ns": st.st_ctime_ns}


def _deadline(end):
    _need(time.monotonic() <= end, "read-budget-exhausted")


def _absolute(path):
    _need(type(path) is str and 0 < len(path) <= 4096 and "\x00" not in path,
          "invalid-path")
    p = PurePosixPath(path)
    _need(p.is_absolute() and str(p) == path and ".." not in p.parts,
          "noncanonical-path")
    return p


@contextmanager
def _directory(path, end, *, identities=None, expected_identities=None):
    """Hold every ancestor open; reject symlinks and replaced path components."""
    p = _absolute(path)
    _need(len(p.parts) <= 32, "path-component-cap")
    _need(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
          "no-safe-open-support")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
    fds = [os.open("/", flags)]
    links = []
    observed_identities = {"/": _identity(os.fstat(fds[0]))}
    try:
        for component in p.parts[1:]:
            _deadline(end)
            parent = fds[-1]
            before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            _need(stat.S_ISDIR(before.st_mode), "path-component-not-directory")
            child = os.open(component, flags, dir_fd=parent)
            fds.append(child)
            current = os.fstat(child)
            _need(_identity(before) == _identity(current), "directory-replaced")
            links.append((parent, component, child, _identity(current)))
            observed_identities[str(PurePosixPath(*p.parts[:len(fds)]))] = _identity(current)
        if expected_identities is not None:
            _need(observed_identities == expected_identities, "path-ancestry-changed")
        if identities is not None:
            identities.update(observed_identities)
        yield fds[-1]
        for parent, name, child, expected in links:
            _deadline(end)
            observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
            _need(stat.S_ISDIR(observed.st_mode) and _identity(observed) == expected
                  and _identity(os.fstat(child)) == expected, "directory-replaced")
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _inventory(fd, cap, end):
    """One-level name inventory only, bounded before opening any child."""
    result = []
    with os.scandir(fd) as entries:
        for entry in entries:
            _deadline(end)
            result.append(entry.name)
            _need(len(result) <= cap, "directory-entry-cap")
    return sorted(result)


def _read(fd, name, cap, end):
    _deadline(end)
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
          "file-not-single-link-regular")
    _need(0 < before.st_size <= cap, "file-size-cap")
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        _need(_fingerprint(os.fstat(handle)) == _fingerprint(before), "file-replaced")
        chunks, size = [], 0
        while True:
            _deadline(end)
            part = os.read(handle, min(65_536, cap + 1 - size))
            if not part:
                break
            chunks.append(part)
            size += len(part)
            _need(size <= cap, "file-size-cap")
        data = b"".join(chunks)
        after = os.fstat(handle)
        linked = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _need(len(data) == before.st_size and _fingerprint(after) == _fingerprint(before)
              and _fingerprint(linked) == _fingerprint(before), "file-changed-during-read")
        return data, _fingerprint(before)
    finally:
        os.close(handle)


def _json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            _need(key not in out, "duplicate-json-key")
            out[key] = value
        return out
    def constant(_):
        raise FixtureReadError("nonfinite-json")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise FixtureReadError("malformed-json") from None


def _keys(obj, required, optional=()):
    _need(type(obj) is dict and set(required) <= set(obj)
          and set(obj) <= set(required) | set(optional), "unexpected-json-fields")


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _recipe(data):
    r = _json(data)
    _keys(r, ("format", "version", "sources", "filter", "overlays", "canvasWidth", "canvasHeight"), ("collageTemplate",))
    _need(r["format"] == "Celluloid.Document" and type(r["version"]) is int
          and r["version"] == 1 and r.get("collageTemplate") is None,
          "unexpected-recipe-format")
    _need(type(r["canvasWidth"]) is int and 1 <= r["canvasWidth"] <= 16_384
          and type(r["canvasHeight"]) is int and 1 <= r["canvasHeight"] <= 16_384
          and r["canvasWidth"] * r["canvasHeight"] <= 50_000_000
          and r["filter"] in ("Original", "Sepia", "Chrome", "Fade", "Invert", "Posterize", "Sketch", "Comic", "Crystal", "PixellateFace"), "unexpected-recipe-canvas")
    _need(type(r["sources"]) is list and len(r["sources"]) == 1, "source-count")
    source = r["sources"][0]
    _keys(source, ("id", "displayName", "pixelWidth", "pixelHeight", "crop"))
    source_id = _uuid(source["id"])
    _need(source["displayName"] == PNG_NAME and type(source["pixelWidth"]) is int
          and source["pixelWidth"] == 1200 and type(source["pixelHeight"]) is int
          and source["pixelHeight"] == 800, "unexpected-source-metadata")
    crop = source["crop"]
    _keys(crop, ("centerX", "centerY", "zoom"))
    _need(_number(crop["centerX"], 0, 1) and _number(crop["centerY"], 0, 1)
          and _number(crop["zoom"], 1, 5), "invalid-source-crop")
    # Preserve valid unexpected or missing layers; expectations are not a read gate.
    _need(type(r["overlays"]) is list and len(r["overlays"]) <= 100, "overlay-count")
    overlays = []
    ids = set()
    for overlay in r["overlays"]:
        _keys(overlay, ("id", "kind", "asset", "text", "centerX", "centerY", "width", "height", "rotation", "mirrored", "fontSize"))
        overlay_id = _uuid(overlay["id"])
        _need(overlay_id not in ids, "duplicate-overlay-id")
        ids.add(overlay_id)
        asset_valid = ((overlay["kind"] == "bubble" and overlay["asset"] in ("aside1", "call1", "call2", "call3", "say1", "say2", "say3", "think1", "think2", "think3"))
                       or (overlay["kind"] == "sticker" and overlay["asset"] in tuple(str(x) for x in range(32, 55))))
        _need(asset_valid and type(overlay["text"]) is str and len(overlay["text"].encode("utf-8")) <= 16_384
              and type(overlay["mirrored"]) is bool, "unexpected-overlay")
        for key, low, high in (("centerX", -2, 3), ("centerY", -2, 3),
                               ("width", .005, 4), ("height", .005, 4),
                               ("rotation", -3600, 3600), ("fontSize", .001, .5)):
            _need(_number(overlay[key], low, high), "invalid-overlay-geometry")
        overlays.append({"id": overlay_id, "kind": overlay["kind"], "asset": overlay["asset"], "text": overlay["text"]})
    return source_id, overlays, {"width": r["canvasWidth"], "height": r["canvasHeight"]}, r["filter"]


def prepare_fixture_receipt(*, devices_root, owned_udid, container_path, png_fixture, deadline):
    """Call after seed_png and before XCTest. Raises on any scope mismatch.

    png_fixture must be the controller's own seed_png result. devices_root must
    be the trusted CoreSimulator Devices root, not a value supplied by the app.
    """
    _need(type(deadline) in (int, float) and math.isfinite(deadline), "invalid-read-deadline")
    end = min(deadline, time.monotonic() + MAX_READ_SECONDS)
    _deadline(end)
    root = _absolute(devices_root)
    device = _uuid(owned_udid)
    container = _absolute(container_path)
    prefix = root / owned_udid / "data/Containers/Data/Application"
    _need(container.parent == prefix, "container-outside-owned-device")
    app_id = _uuid(container.name)
    docs = str(container / "Documents")
    _keys(png_fixture, ("path", "bytes", "sha256", "width", "height", "original_runner_algorithm_unchanged"))
    _need(png_fixture["path"] == str(container / "Documents" / PNG_NAME)
          and type(png_fixture["bytes"]) is int and 0 < png_fixture["bytes"] <= MAX_PNG
          and type(png_fixture["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", png_fixture["sha256"])
          and type(png_fixture["width"]) is int and png_fixture["width"] == 1200
          and type(png_fixture["height"]) is int and png_fixture["height"] == 800
          and png_fixture["original_runner_algorithm_unchanged"] is True, "invalid-png-receipt")
    path_identity = {}
    with _directory(docs, end, identities=path_identity) as fd:
        _need(_inventory(fd, 1, end) == [PNG_NAME], "initial-documents-not-pristine")
        before = _fingerprint(os.fstat(fd))
        data, identity = _read(fd, PNG_NAME, MAX_PNG, end)
        _need(len(data) == png_fixture["bytes"] and _hash(data) == png_fixture["sha256"], "initial-png-mismatch")
        _need(data[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
              and len(data) >= 24 and struct.unpack(">II", data[16:24]) == (1200, 800), "initial-png-dimensions")
        _need(_fingerprint(os.fstat(fd)) == before and _inventory(fd, 1, end) == [PNG_NAME], "initial-documents-changed")
        receipt = {"schema": RECEIPT_SCHEMA, "devices_root": str(root),
                   "owned_udid": owned_udid, "normalized_udid": device,
                   "container_path": str(container), "container_id": app_id,
                   "documents_path": docs, "documents_identity": _identity(os.fstat(fd)),
                   "path_identity": path_identity,
                   "initial_names": [PNG_NAME], "png": {"bytes": len(data), "sha256": _hash(data), "identity": identity}}
    return receipt


def _capture(receipt, package_name, ui_process, process_blocked, deadline):
    _need(process_blocked is False and type(ui_process) is dict
          and all(ui_process.get(k) is True for k in ("finalized", "child_reaped", "pipe_eof"))
          and all(ui_process.get(k) is False for k in ("timed_out", "overflow"))
          and "cleanup_error" in ui_process and ui_process["cleanup_error"] is None
          and type(ui_process.get("return_code")) is int, "ui-process-not-finalized")
    _keys(receipt, ("schema", "devices_root", "owned_udid", "normalized_udid", "container_path", "container_id", "documents_path", "documents_identity", "path_identity", "initial_names", "png"))
    _need(receipt["schema"] == RECEIPT_SCHEMA and receipt["initial_names"] == [PNG_NAME], "invalid-initial-receipt")
    root = _absolute(receipt["devices_root"])
    _need(_uuid(receipt["owned_udid"]) == receipt["normalized_udid"], "receipt-device-mismatch")
    container = _absolute(receipt["container_path"])
    _need(container.parent == root / receipt["owned_udid"] / "data/Containers/Data/Application"
          and _uuid(container.name) == receipt["container_id"]
          and receipt["documents_path"] == str(container / "Documents"), "receipt-path-mismatch")
    _need(type(package_name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,79}\.celluloid", package_name), "invalid-exact-package-name")
    png = receipt["png"]
    _keys(png, ("bytes", "sha256", "identity"))
    _need(type(png["bytes"]) is int and 0 < png["bytes"] <= MAX_PNG
          and type(png["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", png["sha256"]), "invalid-initial-png")
    _need(type(deadline) in (int, float) and math.isfinite(deadline), "invalid-read-deadline")
    end = min(deadline, time.monotonic() + MAX_READ_SECONDS)
    _deadline(end)
    docs = receipt["documents_path"]
    with _directory(docs, end, expected_identities=receipt["path_identity"]) as fd:
        _need(_identity(os.fstat(fd)) == receipt["documents_identity"], "documents-identity-changed")
        before = _fingerprint(os.fstat(fd))
        names = _inventory(fd, 3, end)
        _need(set(names) in ({PNG_NAME, package_name}, {PNG_NAME, package_name, EXPORT_NAME}), "unexpected-documents-inventory")
        if EXPORT_NAME in names:
            export = os.stat(EXPORT_NAME, dir_fd=fd, follow_symlinks=False)
            _need(stat.S_ISREG(export.st_mode) and export.st_nlink == 1 and 0 < export.st_size <= MAX_PNG, "unexpected-export-entry")
        generated, generated_identity = _read(fd, PNG_NAME, MAX_PNG, end)
        _need(generated_identity == png["identity"] and len(generated) == png["bytes"]
              and _hash(generated) == png["sha256"], "generated-png-changed")
        package_path = str(PurePosixPath(docs) / package_name)
        with _directory(package_path, end) as pfd:
            package_before = _fingerprint(os.fstat(pfd))
            package_names = _inventory(pfd, 2, end)
            _need(len(package_names) == 2 and "recipe.json" in package_names, "unexpected-package-inventory")
            recipe, recipe_identity = _read(pfd, "recipe.json", MAX_RECIPE, end)
            source_id, overlays, canvas, filter_name = _recipe(recipe)
            source_name = source_id + ".image"
            _need(set(package_names) == {"recipe.json", source_name}, "unexpected-package-inventory")
            source, source_identity = _read(pfd, source_name, MAX_PNG, end)
            _need(len(source) == png["bytes"] and _hash(source) == png["sha256"], "package-source-not-generated-png")
            # Re-read both members so a mutation between their first reads fails.
            for name, original, identity, cap in (("recipe.json", recipe, recipe_identity, MAX_RECIPE), (source_name, source, source_identity, MAX_PNG)):
                repeated, observed = _read(pfd, name, cap, end)
                _need(repeated == original and observed == identity, "package-changed-between-reads")
            for name, expected in (("recipe.json", recipe_identity), (source_name, source_identity)):
                _need(_fingerprint(os.stat(name, dir_fd=pfd, follow_symlinks=False)) == expected, "package-member-changed-before-return")
            _need(_fingerprint(os.fstat(pfd)) == package_before and _inventory(pfd, 2, end) == package_names, "package-directory-changed")
            result = {"status": "captured", "package_path": package_path,
                      "documents_identity": receipt["documents_identity"],
                      "package_identity": package_before, "owned_udid": receipt["normalized_udid"],
                      "container_id": receipt["container_id"], "canvas": canvas, "filter": filter_name,
                      "recipe": {"bytes": len(recipe), "sha256": _hash(recipe), "identity": recipe_identity},
                      "sources": [{"id": source_id, "filename": source_name, "bytes": len(source), "sha256": _hash(source), "identity": source_identity}],
                      "overlays": overlays}
        final_png, final_identity = _read(fd, PNG_NAME, MAX_PNG, end)
        _need(final_png == generated and final_identity == generated_identity
              and _fingerprint(os.fstat(fd)) == before and _inventory(fd, 3, end) == names, "documents-changed-during-capture")
    return result


def capture_owned_fixture(receipt, package_name, *, ui_process, process_blocked, deadline):
    """After finalized XCTest, before simulator shutdown/delete; pure reads only.

    package_name is the single exact name emitted by the selected UI method.
    A failure returns only a fixed reason, without leaked names or file content.
    No result is a save-completion receipt or a qualification pass.
    """
    base = {"schema": SCHEMA, "diagnostic_only": True,
            "save_completion_proven": False, "qualification_proven": False}
    try:
        out = {**base, **_capture(receipt, package_name, ui_process, process_blocked, deadline)}
        _need(len(json.dumps(out, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_REPORT, "report-size-cap")
        return out
    except FixtureReadError as error:
        return {**base, "status": "unavailable", "reason": str(error)}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {**base, "status": "unavailable", "reason": "unreadable-or-malformed-fixture"}


def capture_initial_fixture(container, udid, png_fixture, *, deadline):
    """Convenience entry point; container is the exact owned simctl receipt.

    Does not invoke simctl. Raises if the initial directory is not pristine.
    Caller records that bounded failure and never substitutes a new receipt.
    """
    path = _absolute(container)
    _need(len(path.parents) >= 6, "invalid-container-path")
    devices_root = path.parents[5]
    _need(devices_root.parts[-3:] == ("Developer", "CoreSimulator", "Devices"), "invalid-devices-root")
    return prepare_fixture_receipt(devices_root=str(devices_root), owned_udid=udid,
                                   container_path=container, png_fixture=png_fixture, deadline=deadline)


def read_fixture(initial, fixture_marker, *, deadline, ui_process, process_blocked):
    """Read only the exact marked package after a finalized UI command.

    Both markers and the initial receipt come from trusted controller parsing.
    The model marker is deliberately not a prerequisite: mismatches need proof.
    """
    base = {"schema": SCHEMA, "diagnostic_only": True,
            "save_completion_proven": False, "qualification_proven": False}
    try:
        _keys(fixture_marker, ("schema", "document_name", "layer_identifier"))
        _need(fixture_marker["schema"] == "Celluloid.VisionFilesFixture.1"
              and type(fixture_marker["document_name"]) is str
              and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,79}", fixture_marker["document_name"]), "invalid-fixture-marker")
        layer = fixture_marker["layer_identifier"]
        _need(type(layer) is str and layer.startswith("layer."), "invalid-fixture-layer")
        expected_id = _uuid(layer[6:])
        out = capture_owned_fixture(initial, fixture_marker["document_name"] + ".celluloid",
                                    ui_process=ui_process, process_blocked=process_blocked,
                                    deadline=deadline)
        if out["status"] == "captured":
            matching = [v for v in out["overlays"] if v["id"] == expected_id]
            out["expected_layer_identifier"] = "layer." + expected_id
            out["expected_text"] = "Vision 世界"
            out["expected_layer_present"] = bool(matching)
            out["expected_text_matches"] = bool(matching and matching[0]["text"] == "Vision 世界")
            _need(len(json.dumps(out, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_REPORT, "report-size-cap")
        return out
    except FixtureReadError as error:
        return {**base, "status": "unavailable", "reason": str(error)}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {**base, "status": "unavailable", "reason": "unreadable-or-malformed-fixture"}

# END_OWNED_FIXTURE_READER

# Fixed Files-method receipt/attachment projections, inserted into the reviewed driver.
FILES_METHOD='testRealFilesImportBubbleAndPNGExport'
FILES_DIAG_STAGES=('identity','post-redo','reopen-layer','reopen-identity')
FIXTURE_READ_SECONDS=10

def files_marker_receipts(log):
 def marker(prefix,schema,keys,required):
  lines=[line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
  need(len(lines)==1 if required else len(lines)<=1,'files-diagnostic-marker-count-'+prefix)
  if not lines:return None
  need(len(lines[0].encode())<=4096,'files-marker-cap');v=strict_json(lines[0]);need(type(v) is dict and set(v)==keys and v['schema']==schema,'files-marker-schema')
  name=v['document_name'];identity=v['layer_identifier']
  need(type(name) is str and 0<len(name.encode())<=120 and name==Path(name).name and name not in {'.','..'} and not any(c in name for c in ['/', '\\', '\0']) and not name.endswith('.celluloid'),'files-document-name')
  need(type(identity) is str and re.fullmatch(r'layer\.[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',identity),'files-layer-identity')
  return v
 fixture=marker('VISION_FILES_FIXTURE_JSON ','Celluloid.VisionFilesFixture.1',{'schema','document_name','layer_identifier'},True)
 model=marker('VISION_FILES_MODEL_JSON ','Celluloid.VisionFilesModel.1',{'schema','stage','document_name','layer_identifier','expected_text','matched','actual_label'},False)
 if model is not None:
  need(model['stage']=='post-redo' and model['expected_text']=='Vision 世界' and type(model['matched']) is bool and type(model['actual_label']) is str and len(model['actual_label'].encode())<=1024,'files-model-fields')
  need(model['document_name']==fixture['document_name'] and model['layer_identifier']==fixture['layer_identifier'],'files-model-fixture-mismatch')
 return {'fixture':fixture,'post_redo_model':model,'post_redo_model_matched':bool(model and model['matched'] and model['actual_label']=='Select layer: Vision 世界'),'save_completion_proven':False}

def exported_files_diagnostics(folder,manifest):
 need(type(manifest) is list and len(manifest)<=16 and all(type(r) is dict and type(r.get('attachments')) is list for r in manifest),'diagnostic-attachment-records')
 need(sum(len(r['attachments']) for r in manifest)<=1024,'diagnostic-attachment-count')
 names={'vision-files-diag-'+stage+'-'+kind for stage in FILES_DIAG_STAGES for kind in ['ax','screen']};found={};seen=set()
 for record in manifest:
  for item in record['attachments']:
   need(type(item) is dict,'diagnostic-attachment-item');name=item.get('suggestedHumanReadableName','');file=item.get('exportedFileName')
   need(type(file) is str and Path(file).name==file and file not in {'','.','..'} and file not in seen,'diagnostic-attachment-path');seen.add(file)
   matches=[n for n in names if name==n or type(name) is str and name.startswith(n+'_')]
   if not matches:continue
   need(len(matches)==1 and matches[0] not in found and record.get('testIdentifier')=='NativeVisionUITests/'+FILES_METHOD+'()','diagnostic-owner-or-duplicate');key=matches[0]
   ax=key.endswith('-ax');raw=safe_read(folder/file,70000 if ax else 1000000)
   if ax:raw.decode('utf8');ext='.txt'
   else:need(raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff'),'diagnostic-image-type');ext='.png' if raw.startswith(b'\x89PNG') else '.jpg'
   found[key]={'source':str(folder/file),'bytes':len(raw),'sha256':digest(raw),'extension':ext,'attachment_provenance':{'test_identifier':record['testIdentifier'],'attachment_name':name,'exported_file_name':file},'scope':'diagnostic only, never a substitute for original required screenshots'}
 need(len(found)<=2,'at-most-one-failure-stage-pair')
 if found:
  stages={key.removeprefix('vision-files-diag-').rsplit('-',1)[0] for key in found};need(len(stages)==1,'mixed-failure-stages')
 return found

class VisionCommands:
 def __init__(self,temp):self.temp=temp;self.events=[];self.blocked=False
 def run(self,argv,label,*,deadline,seconds,cleanup=15,check_code=True,full=False):
  need(not self.blocked,'earlier-process-uncertain-or-timeout')
  now=time.monotonic();end=min(deadline,now+seconds)
  if full:need(now+seconds<=deadline,'full-command-window-does-not-fit')
  need(end-now>cleanup+0.1,'command-cleanup-reserve')
  need(re.fullmatch('[a-zA-Z0-9_.-]+',label) is not None,'log-label')
  log=self.temp/(label+'.log');need(not log.exists(),'duplicate-invocation-log')
  print_command_receipt('BEGIN',label,argv,now)
  try:result=bounded_optional_process(list(map(str,argv)),end-cleanup,end,cap=MAX_OUTPUT,stop_on_signal_error=True)
  except BaseException as e:
   self.blocked=True;self.events.append({'label':label,'argv':list(map(str,argv)),'begin_monotonic':now,'exception':type(e).__name__,'finalized':False});print_command_receipt('END',label,argv,now,self.events[-1]);raise
  # Latch uncertainty before any output extraction, filesystem write or receipt
  # printing can fail. Diagnostic I/O must never re-enable native dispatch.
  if not result['finalized'] or result['timed_out'] or result['overflow']:self.blocked=True
  output=result.pop('output');log.write_bytes(output)
  event={'label':label,'argv':list(map(str,argv)),'begin_monotonic':now,**result,'log':log.name,'log_bytes':len(output),'log_sha256':digest(output)};self.events.append(event);print_command_receipt('END',label,argv,now,result)
  need(result['finalized'],'process-cleanup-unconfirmed')
  need(not result['timed_out'] and not result['overflow'],'process-timeout-or-output-bound')
  if check_code:need(result['return_code']==0,'command-exit-'+str(result['return_code'])+'-'+label)
  return output.decode('utf8','replace'),result


def xctest_command(temp,udid,bundle,selection):
 return ['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination','platform=visionOS Simulator,id='+udid,'-derivedDataPath',str(temp/'vision-wave-build'),'-resultBundlePath',str(bundle),'CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-concurrent-test-simulator-destinations','1',*selection,'test-without-building']

def validate_inventory(root=ROOT):
 expected={'Platforms/VisionTests/NativeVisionTests.swift':HOSTED,'Platforms/VisionUITests/NativeVisionUITests.swift':UI_METHODS}
 out={}
 for rel,methods in expected.items():
  raw=safe_read(root/rel,200000);text=raw.decode();need(set(re.findall(r'\bfunc\s+(test\w+)\s*\(',text))==set(methods),'declared-original-inventory')
  need('XCTSkip' not in text,'source-skip');out[rel]=digest(raw)
 return out

def exported_images(folder,manifest,method):
 need(type(manifest) is list and len(manifest)<=16,'attachment-record-cap')
 need(all(type(r) is dict and type(r.get('attachments')) is list for r in manifest),'attachment-record')
 need(sum(len(r['attachments']) for r in manifest)<=1024,'attachment-item-cap')
 allowed=SHOTS[method];found={};seen=set()
 for record in manifest:
  for item in record['attachments']:
   need(type(item) is dict,'attachment-item');name=item.get('suggestedHumanReadableName','');path=item.get('exportedFileName')
   need(type(path) is str and Path(path).name==path and path not in {'','.','..'} and path not in seen,'attachment-path');seen.add(path)
   matches=[n for n in allowed if name==n or (type(name) is str and name.startswith(n+'_'))]
   if not matches:continue
   need(len(matches)==1,'ambiguous-shot-name');key=matches[0]
   need(record.get('testIdentifier')=='NativeVisionUITests/'+method+'()' and key not in found,'wrong-or-duplicate-shot-owner')
   raw=safe_read(folder/path,5000000);need(raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff'),'shot-magic')
   found[key]={'source':str(folder/path),'bytes':len(raw),'sha256':digest(raw),'extension':'.png' if raw.startswith(b'\x89PNG') else '.jpg','attachment_provenance':{'test_identifier':record['testIdentifier'],'attachment_name':name,'exported_file_name':path}}
 return found


def execute(env):
 os.chdir(ROOT);temp=Path(env['RUNNER_TEMP']).resolve(strict=True)
 config=validate_config(strict_json(safe_read(ROOT/CONFIG,16384)),env);clock=validate_clock(strict_json(safe_read(temp/CLOCK,16384)),env)
 method=config['selected_method'];key=str(UI_METHODS.index(method)+1);prefix='vision-wave-'+key+'-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']
 commands=VisionCommands(temp);work=clock['started_monotonic']+NATIVE_SECONDS;final=clock['started_monotonic']+FINAL_SECONDS
 report={'schema':'Celluloid.FinalVisionSingleMethodWave.1','test_diagnostics':{'path':DIAGNOSTIC_TEST,'sha256':DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':ORIGINAL_TEST_SHA256,'unchanged_original_files':961,'product_compiled_inputs_unchanged':True},'control_sha':env['GITHUB_SHA'],'product_sha':SOURCE,'product_tree':TREE,'run_id':env['GITHUB_RUN_ID'],'run_attempt':env['GITHUB_RUN_ATTEMPT'],'selected_method':method,'omitted_ui_methods':[m for m in UI_METHODS if m!=method],'original_hosted_inventory':list(HOSTED),'original_ui_inventory':list(UI_METHODS),'retained_hosted_evidence':{'run_id':37909497562,'control_sha':'46fc7a5a41efea647dc27099ab9883187b8814ec','passed_methods':list(HOSTED),'new_execution_claim':False},'retained_release_evidence':{'run_id':37909497562,'binary_sha256':'a03d12bfb39b98a372bf9ea2f7bab01ecef13996fd8ef316e628cb1fcaf21e85','fresh_release_build':False},'fixture_dependency':DEPENDENCIES[method],'fixture_producer_selected':bool(selectors_for(method)['producer']),'clock':clock,'ui_limit_seconds':UI_SECONDS,'selected_method_passed':False,'wave_qualified':False,'all_eight_qualified':False,'archive_qualified':False,'required_screenshots':list(SHOTS[method]),'screenshots':{},'commands':commands.events,'errors':[],'omissions':[]}
 fixture_initial=None
 udid=None;bundle=temp/(prefix+'-ui.xcresult');ui_log=None;ui_result=None;summary=None
 def call(args,label,seconds,**kwargs):return commands.run(args,prefix+'-'+label,deadline=kwargs.pop('deadline',work-CLEANUP_RESERVE),seconds=seconds,**kwargs)
 try:
  report['source_inventory']=validate_inventory()
  v,_=call(['xcodebuild','-version'],'xcode',30);need(v.splitlines()[0]=='Xcode 27.0','xcode-version')
  for script in ['validate_native_sources.py','validate_native_localization.py','test_native_process.py','test_native_evidence.py','test_native_release.py']:
   call([sys.executable,'-B','-S','Scripts/'+script],script.replace('.py',''),90)
  call(['swift','-swift-version','5','Scripts/materialize_native_icons.swift'],'icons',105)
  call([sys.executable,'-B','-S','Scripts/verify_native_icon_inputs.py'],'icon-proof',30)
  call(['xcodebuild','-quiet','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination','generic/platform=visionOS Simulator','-derivedDataPath',temp/'vision-wave-build','CODE_SIGNING_ALLOWED=NO','build-for-testing'],'build',315)
  raw,_=call(['xcrun','simctl','list','runtimes','--json'],'runtimes',45);runtimes=strict_json(raw)['runtimes']
  raw,_=call(['xcrun','simctl','list','devicetypes','--json'],'device-types',45);types=strict_json(raw)['devicetypes']
  possible=[r for r in runtimes if r.get('isAvailable') and ('vision' in r.get('name','').lower() or 'xros' in r.get('identifier','').lower())];need(possible,'no-vision-runtime')
  runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0];supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
  device=next(t for t in types if (not supported or t['identifier'] in supported) and 'Apple Vision Pro' in t['name']);report.update(runtime={k:runtime[k] for k in ('name','version','identifier','buildversion') if k in runtime},device_type={k:device[k] for k in ('name','identifier') if k in device})
  raw,_=call(['xcrun','simctl','create',prefix,device['identifier'],runtime['identifier']],'create',45);udid=raw.strip();need(re.fullmatch(r'[0-9A-Fa-f-]{36}',udid),'invalid-device-id');report['udid']=udid
  call(['xcrun','simctl','boot',udid],'boot',195)
  call(['xcrun','simctl','bootstatus',udid,'-b'],'bootstatus',255)
  app=temp/'vision-wave-build/Build/Products/Debug-xrsimulator/CelluloidVision.app'
  call(['xcrun','simctl','install',udid,app],'install',315)
  # Preserve the existing separate pretest launch/PID/simctl capture. No
  # Chinese XCTest screenshot is removed, replaced, suppressed or deduplicated.
  raw,_=call(['xcrun','simctl','launch',udid,'Mango.Celluloid'],'pretest-launch',195)
  pid=raw.strip().rsplit(':',1)[-1].strip();need(pid.isdigit(),'pretest-launch-pid');time.sleep(4)
  raw,_=call(['ps','-p',pid,'-o','pid=,comm='],'pretest-process',35)
  need('CelluloidVision.app/CelluloidVision' in raw and raw.strip().startswith(pid+' '),'pretest-process-identity');report['pretest_process']=raw
  shot=temp/(prefix+'-native-vision-launch.jpg')
  _,capture_result=call(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',shot],'pretest-screenshot',60,check_code=False)
  if capture_result['return_code']==0:
   raw_image=safe_read(shot,5000000);need(raw_image.startswith(b'\xff\xd8\xff'),'pretest-image-type')
   report['pretest_launch_image']={'path':str(shot),'sha256':digest(raw_image),'bytes':len(raw_image),'scope':'English pretest launch, never a substitute for the unchanged Chinese XCTest launch image'}
  else:report['omissions'].append('Optional pretest simctl launch screenshot exited '+str(capture_result['return_code']))
  call(['xcrun','simctl','terminate',udid,'Mango.Celluloid'],'pretest-terminate',45,check_code=False)
  selection=selectors_for(method)
  if selection['producer']:
   producer_bundle=temp/(prefix+'-producer.xcresult')
   producer_log,_=call(xctest_command(temp,udid,producer_bundle,selection['producer']),'producer-tests',195,full=True)
   raw,_=call(['xcrun','xcresulttool','get','test-results','summary','--path',producer_bundle],'producer-summary',60)
   report['producer_case']=inspect_case(producer_log,PRODUCER,strict_json(raw),'producer',udid,runtime['version'])
   raw,_=call(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data'],'producer-container',195)
   report['producer_fixture']=verify_producer(producer_log,raw.strip())
  elif DEPENDENCIES[method]=='own-generated-png':
   raw,_=call(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data'],'png-container',195);report['png_fixture']=seed_png(raw.strip())
   if method==FILES_METHOD:
    try:
     fixture_initial=capture_initial_fixture(raw.strip(),udid,report['png_fixture'],deadline=min(work-CLEANUP_RESERVE,time.monotonic()+FIXTURE_READ_SECONDS))
     report['fixture_initial_receipt']=fixture_initial
    except (ValueError,OSError,KeyError,TypeError) as e:
     # Failed diagnostic ownership never permits a substitute read and does not
     # erase execution of the original UI method under its unchanged admission.
     report['errors'].append('initial owned fixture diagnostic unavailable: '+type(e).__name__+': '+str(e))
     report['fixture_initial_diagnostic']={'status':'unavailable','save_completion_proven':False,'qualification_proven':False}
  deadline=admit_ui(clock)
  ui_log,ui_result=call(xctest_command(temp,udid,bundle,selection['ui']),'ui-tests',UI_SECONDS+15,deadline=deadline,full=True,check_code=False)
 except BaseException as e:report['errors'].append(type(e).__name__+': '+str(e))
 finally:
  # Pure bounded reads of the one initially-owned fixture, after known UI process
  # completion and before deletion. No read or new native action follows uncertainty.
  if method==FILES_METHOD and fixture_initial is not None and ui_result is not None and not commands.blocked:
   try:
    receipts=files_marker_receipts(ui_log or '');report['files_model_receipts']=receipts
    started=time.monotonic()
    report['fixture_readback']=read_fixture(fixture_initial,receipts['fixture'],deadline=min(work-CLEANUP_RESERVE,started+FIXTURE_READ_SECONDS),ui_process=ui_result,process_blocked=commands.blocked)
    report['fixture_readback_timing']={'after_finalized_ui':True,'started_monotonic':started,'finished_monotonic':time.monotonic(),'save_completion_proven':False}
    observed=report['fixture_readback']
    if observed['status']!='captured':report['errors'].append('owned fixture diagnostic unavailable: '+observed.get('reason','missing'))
    elif not observed.get('expected_layer_present') or not observed.get('expected_text_matches'):report['errors'].append('owned fixture observed layer/text differs from expected; save-completion and cause remain unproven')
    if not receipts['post_redo_model_matched']:report['errors'].append('exact post-Redo model checkpoint is missing or failed')
   except (ValueError,OSError,KeyError,TypeError) as e:report['errors'].append('Files model/package diagnostics: '+type(e).__name__+': '+str(e))
  elif method==FILES_METHOD:report['omissions'].append('No package read without an initial owned fixture and finalized UI command; no save or persisted-content claim.')
  if udid and not commands.blocked:
   for action in ['shutdown','delete']:
    try:call(['xcrun','simctl',action,udid],action,60,deadline=work)
    except BaseException as e:
     report['errors'].append('cleanup '+action+': '+str(e))
     if commands.blocked:break
  elif udid:report['omissions'].append('No further native cleanup/exports after uncertain or timed-out command; disposable runner teardown remains required.')
 # Export only after known process completion. Required screenshots remain mandatory.
 if bundle.is_dir() and not commands.blocked:
  try:
   raw,_=call(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],'ui-summary',60,deadline=final-60)
   summary=strict_json(raw);report['ui_summary']=summary
   need(ui_result is not None and ui_result['return_code']==0,'ui-process-not-successful')
   report['ui_case']=inspect_case(ui_log,method,summary,udid=udid,runtime_version=runtime['version']);report['selected_method_passed']=True
  except BaseException as e:report['errors'].append('case summary: '+str(e))
  if SHOTS[method] and not commands.blocked:
   try:
    folder=temp/(prefix+'-attachments');need(not folder.exists(),'attachment-dir-exists')
    call(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',folder],'attachments',75,deadline=final-45)
    attachment_manifest=strict_json(safe_read(folder/'manifest.json',262144))
    report['screenshots']=exported_images(folder,attachment_manifest,method)
    if method==FILES_METHOD:report['files_diagnostic_attachments']=exported_files_diagnostics(folder,attachment_manifest)
    need(set(report['screenshots'])==set(SHOTS[method]),'required-screenshot-missing')
   except BaseException as e:report['errors'].append('screenshots: '+str(e))
 report['process_blocked']=commands.blocked
 report['elapsed_seconds']=time.monotonic()-clock['started_monotonic']
 report['wave_qualified']=report['selected_method_passed'] and not report['errors'] and set(report['screenshots'])==set(SHOTS[method]) and not commands.blocked
 (temp/'vision-wave-report.json').write_bytes(encoded(report))
 print(json.dumps({'selected_method':method,'passed':report['selected_method_passed'],'wave_qualified':report['wave_qualified'],'errors':report['errors']}))
 return report


def validate_report_identity(report,env):
 need(type(report) is dict and report.get('schema')=='Celluloid.FinalVisionSingleMethodWave.1','report-schema')
 for key,value in [('control_sha',env['GITHUB_SHA']),('product_sha',SOURCE),('product_tree',TREE),('run_id',env['GITHUB_RUN_ID']),('run_attempt',env['GITHUB_RUN_ATTEMPT']),('selected_method',env['VISION_WAVE_METHOD'])]:need(report.get(key)==value,'report-identity-'+key)
 need(report.get('test_diagnostics')=={'path':DIAGNOSTIC_TEST,'sha256':DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':ORIGINAL_TEST_SHA256,'unchanged_original_files':961,'product_compiled_inputs_unchanged':True},'report-test-diagnostic-provenance')
 method=report['selected_method'];need(method in UI_METHODS and report.get('omitted_ui_methods')==[m for m in UI_METHODS if m!=method],'report-scope')
 need(report.get('original_hosted_inventory')==list(HOSTED) and report.get('original_ui_inventory')==list(UI_METHODS),'report-inventory')
 need(report.get('ui_limit_seconds')==UI_SECONDS and report.get('all_eight_qualified') is False and report.get('archive_qualified') is False,'report-claim')
 need(type(report.get('screenshots')) is dict and set(report['screenshots'])<=set(SHOTS[method]),'report-images')
 need(type(report.get('selected_method_passed')) is bool and type(report.get('wave_qualified')) is bool and type(report.get('errors')) is list,'report-status')
 if report['wave_qualified']:need(report['selected_method_passed'] and not report['errors'] and set(report['screenshots'])==set(SHOTS[method]),'unsupported-wave-success')
 return validate_clock(report['clock'],env)


# Public artifacts retain only bounded current-job diagnostics, never complete
# host runtime/device-type discovery or unrelated attachment-enumeration output.
PUBLIC_OPTIONAL_STAGES=frozenset(('xcode','validate_native_sources','validate_native_localization','test_native_process','test_native_evidence','test_native_release','icons','icon-proof','create','boot','bootstatus','install','pretest-launch','pretest-process','pretest-screenshot','pretest-terminate','png-container','shutdown','delete'))

def collect(env):
 temp=Path(env['RUNNER_TEMP']).resolve(strict=True);report=strict_json(safe_read(temp/'vision-wave-report.json',200000));clock=validate_report_identity(report,env)
 need(time.monotonic()<clock['started_monotonic']+FINAL_SECONDS-30,'collection-clock')
 before=strict_json(safe_read(temp/'combined-source-before.json',16384));after=strict_json(safe_read(temp/'combined-source-after.json',16384))
 need(before.get('phase')=='before' and after.get('phase')=='after','source-phases')
 before.pop('phase');after.pop('phase');need(before==after,'source-after-mismatch');need(after['source_sha']==env['GITHUB_SHA'] and after['product_parent_sha']==SOURCE and after['selected_method']==env['VISION_WAVE_METHOD'],'source-report-binding')
 out=temp/'vision-wave-evidence';out.mkdir();manifest={'source_sha':env['GITHUB_SHA'],'run_id':env['GITHUB_RUN_ID'],'selected_method':env['VISION_WAVE_METHOD'],'limit_bytes':MAX_EVIDENCE,'files':[],'omissions':[]};size=0
 def retain(name,raw,required=True):
  nonlocal size
  need(Path(name).name==name and name not in {'.','..'},'retention-name')
  if len(raw)>5000000 or size+len(raw)>MAX_EVIDENCE-150000:
   if required:raise ValueError('required-evidence-byte-cap-'+name)
   manifest['omissions'].append({'name':name,'reason':'byte-cap'});return
  (out/name).write_bytes(raw);size+=len(raw);manifest['files'].append({'name':name,'bytes':len(raw),'sha256':digest(raw)})
 for name in ['combined-source-before.json','combined-source-after.json']:retain(name,safe_read(temp/name,16384))
 for event in report['commands']:
  if 'log' in event and ('ui-tests' in event['label'] or 'producer-tests' in event['label'] or 'summary' in event['label']):
   need(Path(event['log']).name==event['log'],'log-path')
   if event['log_bytes']==0:manifest['omissions'].append({'name':event['log'],'reason':'empty captured output'});continue
   p=temp/event['log'];raw=safe_read(p,MAX_OUTPUT);need(len(raw)==event['log_bytes'] and digest(raw)==event['log_sha256'],'log-identity')
   if event['label'].endswith('-ui-tests'):
    started="Test Case '-[CelluloidVisionUITests.NativeVisionUITests "+report['selected_method']+"]' started."
    if started not in raw.decode('utf8','replace').splitlines():
     report['ui_transcript_retention']={'state':'withheld-before-selected-case','reason':'exact selected Test Case never started; raw pre-test diagnostics may enumerate unrelated destinations','log':p.name,'source_bytes':len(raw),'source_sha256':digest(raw),'original_return_code':event.get('return_code')}
     manifest['omissions'].append({'name':p.name,'reason':'selected-case-never-started'});continue
   retain(p.name,raw)
 if report.get('selected_method_passed') is True:
  try:
   tests=[e for e in report['commands'] if e.get('label','').endswith('-ui-tests')];summaries=[e for e in report['commands'] if e.get('label','').endswith('-ui-summary')]
   need(len(tests)==len(summaries)==1,'one-current-case-and-summary-required')
   for event in tests+summaries:
    need(event.get('finalized') is True and event.get('return_code')==0 and not event.get('timed_out') and not event.get('overflow'),'proof-command-not-passed')
   actual_summary=strict_json(safe_read(temp/summaries[0]['log'],MAX_OUTPUT));need(actual_summary==report['ui_summary'],'summary-replay-mismatch')
   replay=inspect_case(safe_read(temp/tests[0]['log'],MAX_OUTPUT).decode(),report['selected_method'],actual_summary,udid=report['udid'],runtime_version=report['runtime']['version'])
   need(replay==report['ui_case'],'case-replay-mismatch')
  except (ValueError,OSError,KeyError) as error:
   report['wave_qualified']=False;report['selected_method_passed']=False;report['errors'].append('retained proof replay: '+str(error))
 for name,row in report['screenshots'].items():
  expected_folder=temp/('vision-wave-'+str(UI_METHODS.index(env['VISION_WAVE_METHOD'])+1)+'-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']+'-attachments')
  need(Path(row['source']).parent==expected_folder,'image-not-owned-export')
  raw=safe_read(row['source'],5000000);need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'image-identity')
  if size+len(raw)>MAX_EVIDENCE-150000:
   report['wave_qualified']=False;report['errors'].append('required retained screenshot exceeds fixed byte cap: '+name);manifest['omissions'].append({'name':name,'reason':'required-image-byte-cap'})
  else:retain(name+row['extension'],raw)
 for name,row in report.get('files_diagnostic_attachments',{}).items():
  allowed={'vision-files-diag-'+stage+'-'+kind for stage in FILES_DIAG_STAGES for kind in ['ax','screen']}
  need(name in allowed and env['VISION_WAVE_METHOD']==FILES_METHOD,'diagnostic-retention-name')
  expected_folder=temp/('vision-wave-2-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']+'-attachments')
  need(Path(row['source']).parent==expected_folder,'diagnostic-not-owned-export')
  raw=safe_read(row['source'],70000 if name.endswith('-ax') else 1000000);need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'diagnostic-identity')
  if size+len(raw)>MAX_EVIDENCE-150000:
   report['wave_qualified']=False;report['errors'].append('diagnostic attachment exceeds fixed evidence cap: '+name);manifest['omissions'].append({'name':name,'reason':'diagnostic-byte-cap'})
  else:retain(name+row['extension'],raw)
 retain('report.json',encoded(report))
 for event in report['commands']:
  if 'log' in event and not (out/event['log']).exists():
   prefix='vision-wave-'+str(UI_METHODS.index(env['VISION_WAVE_METHOD'])+1)+'-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']+'-'
   stage=event['label'][len(prefix):] if event['label'].startswith(prefix) else ''
   if stage not in PUBLIC_OPTIONAL_STAGES:
    manifest['omissions'].append({'name':event['log'],'reason':'outside-public-diagnostic-allowlist'});continue
   need(Path(event['log']).name==event['log'],'log-path')
   if event['log_bytes']==0:continue
   p=temp/event['log'];raw=safe_read(p,MAX_OUTPUT);need(len(raw)==event['log_bytes'] and digest(raw)==event['log_sha256'],'optional-log-identity');retain(p.name,raw[-24000:],False)
 if 'pretest_launch_image' in report:
  row=report['pretest_launch_image'];p=Path(row['path']);need(p.parent==temp and p.name.endswith('-native-vision-launch.jpg'),'pretest-image-path');raw=safe_read(p,5000000);need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'pretest-image-identity');retain(p.name,raw,False)
 retain('manifest.json',encoded(manifest));need(sum(p.stat().st_size for p in out.iterdir())<=MAX_EVIDENCE,'total-evidence-cap')
 with open(env['GITHUB_OUTPUT'],'a') as f:f.write('evidence_ready=true\n')
 return report


def main():
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['run','collect','admit-upload','finish-upload']);a=parser.parse_args();env=os.environ
 if a.phase=='run':raise SystemExit(0 if execute(env)['wave_qualified'] else 1)
 if a.phase=='collect':raise SystemExit(0 if collect(env)['wave_qualified'] else 1)
 else:
  temp=Path(env['RUNNER_TEMP']).resolve(strict=True);clock=validate_clock(strict_json(safe_read(temp/CLOCK,16384)),env)
  need(time.monotonic()<clock['started_monotonic']+FINAL_SECONDS,'upload-clock')
  if a.phase=='admit-upload':
   need(time.monotonic()+60<=clock['started_monotonic']+FINAL_SECONDS,'full-one-minute-upload-reserve')
   need((temp/'vision-wave-evidence/manifest.json').is_file(),'evidence-missing')
   with open(env['GITHUB_OUTPUT'],'a') as f:f.write('upload_admitted=true\n')
  else:need(env.get('VISION_WAVE_UPLOAD_OUTCOME')=='success','upload-failed')
if __name__=='__main__':main()
