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
