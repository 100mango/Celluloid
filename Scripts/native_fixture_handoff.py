#!/usr/bin/env python3
"""Bounded, hash-verified handoff of newly authored synthetic Mac adjustment bytes."""
import base64,hashlib,json,re
from pathlib import Path
FILTERS={'Original','Sepia','Chrome','Fade','Invert','Posterize','Sketch','Comic','Crystal','PixellateFace'}
PATTERN=re.compile(r'MAC_FILTER_ONLY_FIXTURE filter=(\w+) sha256=([0-9a-f]{64}) base64=([A-Za-z0-9+/=]+)')
MAX_BYTES=100_000

def validate_rows(rows):
    if not isinstance(rows,list) or len(rows)!=len(FILTERS):raise ValueError('Expected ten synthetic Mac filter archives')
    if {row['filter'] for row in rows}!=FILTERS:raise ValueError('Missing or duplicate Mac filter identifiers')
    for row in rows:
        data=base64.b64decode(row['base64'],validate=True)
        if not 0<len(data)<=8192 or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Mac synthetic archive byte/hash mismatch')
    return rows

def from_log(path,source_sha):
    rows=[];fallback=[]
    with Path(path).open('r',encoding='utf8',errors='replace') as handle:
        for line in handle:
            match=PATTERN.search(line)
            if match:rows.append(dict(zip(['filter','sha256','base64'],match.groups())))
            if 'MAC_BAKED_BASE_FIXTURE ' in line:fallback.append(json.loads(line.split('MAC_BAKED_BASE_FIXTURE ',1)[1]))
    if len(fallback)!=1:raise ValueError('Expected one baked-base discriminator fixture')
    validate_fallback(fallback[0])
    payload={'fallback':fallback[0],'schema':'Celluloid.SyntheticMacFilterFixtures.1','source_sha':source_sha,'fixtures':validate_rows(rows)}
    data=(json.dumps(payload,sort_keys=True)+'\n').encode()
    if len(data)>MAX_BYTES:raise ValueError('Synthetic fixture handoff exceeded byte limit')
    return data

def load_exact(directory,source_sha):
    directory=Path(directory);path=directory/'mac-filter-fixtures.json';manifest_path=directory/'manifest.json'
    if path.is_symlink() or manifest_path.is_symlink() or path.stat().st_size>MAX_BYTES or manifest_path.stat().st_size>MAX_BYTES:
        raise ValueError('Invalid bounded fixture handoff')
    manifest=json.loads(manifest_path.read_bytes());data=path.read_bytes();payload=json.loads(data)
    if manifest['source_sha']!=source_sha or payload['source_sha']!=source_sha:
        raise ValueError('Mac fixture source is not this exact validation commit')
    if payload['schema']!='Celluloid.SyntheticMacFilterFixtures.1':raise ValueError('Unknown fixture schema')
    records=[row for row in manifest['files'] if row['name']==path.name]
    if len(records)!=1 or records[0]['bytes']!=len(data) or records[0]['sha256']!=hashlib.sha256(data).hexdigest():
        raise ValueError('Mac fixture artifact manifest/hash mismatch')
    validate_rows(payload['fixtures']);validate_fallback(payload['fallback']);return payload

def validate_fallback(row):
    if row['identifier']!='Mango.CelluloidPhotoExtension' or row['version']!='2.0-baked-base':
        raise ValueError('Baked-base output must not advertise legacy editable support')
    data=base64.b64decode(row['base64'],validate=True)
    if not 0<len(data)<=8192 or hashlib.sha256(data).hexdigest()!=row['sha256']:
        raise ValueError('Baked-base synthetic archive byte/hash mismatch')

LAYER_FILE='mac-layer-fixture.json'
LAYER_MAX_BYTES=500_000

def validate_layer(row):
    keys={'name','identifier','version','sha256','base64','sourceSHA256','sourceBase64','renderedSHA256','renderedBase64'}
    if not isinstance(row,dict) or set(row)!=keys or not all(isinstance(v,str) for v in row.values()):raise ValueError('Malformed manufactured-layer fixture')
    if (row['name'],row['identifier'],row['version'])!=('manufactured-affine','Mango.CelluloidPhotoExtension','1.0'):raise ValueError('Unexpected manufactured-layer fixture identity')
    if len(json.dumps(row,separators=(',',':')).encode())>LAYER_MAX_BYTES:raise ValueError('Manufactured-layer fixture exceeds bounded handoff')
    for content,sha,limit in [('base64','sha256',32_768),('sourceBase64','sourceSHA256',150_000),('renderedBase64','renderedSHA256',150_000)]:
        data=base64.b64decode(row[content],validate=True)
        if not 0<len(data)<=limit or hashlib.sha256(data).hexdigest()!=row[sha]:raise ValueError('Manufactured-layer byte/hash mismatch')
        if content!='base64':
            if data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR' or int.from_bytes(data[16:20],'big')!=480 or int.from_bytes(data[20:24],'big')!=640:raise ValueError('Expected fixed synthetic480x640 PNG')
    return row

def layer_from_log(path,source_sha):
    rows=[]
    with Path(path).open('rb') as handle:
        for part in iter(lambda:handle.readline(LAYER_MAX_BYTES+1),b''):
            if b'MAC_LAYER_ADJUSTMENT_FIXTURE ' not in part:continue
            if len(part)>LAYER_MAX_BYTES:raise ValueError('Manufactured-layer log record exceeds bound')
            rows.append(json.loads(part.split(b'MAC_LAYER_ADJUSTMENT_FIXTURE ',1)[1]))
    if len(rows)!=1:raise ValueError('Expected exactly one real Mac-manufactured layer fixture')
    payload={'schema':'Celluloid.SyntheticMacLayerFixture.1','source_sha':source_sha,'fixture':validate_layer(rows[0])}
    data=(json.dumps(payload,sort_keys=True)+'\n').encode()
    if len(data)>LAYER_MAX_BYTES:raise ValueError('Manufactured-layer handoff exceeds bound')
    return data

def load_layer_exact(directory,source_sha):
    directory=Path(directory);path=directory/LAYER_FILE;manifest_path=directory/'manifest.json'
    if path.is_symlink() or manifest_path.is_symlink() or path.stat().st_size>LAYER_MAX_BYTES or manifest_path.stat().st_size>MAX_BYTES:raise ValueError('Invalid bounded layer handoff')
    data=path.read_bytes();payload=json.loads(data);manifest=json.loads(manifest_path.read_bytes())
    if manifest['source_sha']!=source_sha or payload['source_sha']!=source_sha:raise ValueError('Layer fixture is not this exact validation commit')
    if payload['schema']!='Celluloid.SyntheticMacLayerFixture.1':raise ValueError('Unknown layer fixture schema')
    rows=[r for r in manifest['files'] if r['name']==LAYER_FILE]
    if len(rows)!=1 or rows[0]['bytes']!=len(data) or rows[0]['sha256']!=hashlib.sha256(data).hexdigest():raise ValueError('Layer fixture artifact manifest/hash mismatch')
    validate_layer(payload['fixture']);return payload
