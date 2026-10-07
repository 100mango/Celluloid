"""Exact output-retention function from the qualified Celluloid Mac v3 adapter.
Source: mac_unsigned_archive.py at ee04acc4a98a07ff050b73e478c9165feab3867b.
The original function is unchanged; all command captures use its established
16 MiB raw / 512 KiB retained bounds. This helper performs no native commands.
"""
import hashlib
import re
ARCHIVE_RAW_CAP = 16 * 1024 ** 2
ARCHIVE_RETAIN_CAP = 512 * 1024

def need(ok, reason):
    if not ok: raise ValueError(reason)

def retain_archive_output(receipt, stdout, stderr, *, capture_complete):
    """Scan the full bounded capture before retaining only labelled prefix/tail text.

    A stopped producer has only captured-prefix hashes, never a claimed full log.
    Full hashes use original bytes. Retention is bounded after UTF-8 replacement.
    """
    encoded=[raw.decode('utf-8','replace').encode('utf-8') for raw in (stdout,stderr)]
    first=min(len(encoded[0]),ARCHIVE_RETAIN_CAP//2)
    second=min(len(encoded[1]),ARCHIVE_RETAIN_CAP-first)
    budgets=[min(len(encoded[0]),ARCHIVE_RETAIN_CAP-second),second]
    marker=b'\n[... ARCHIVE LOG TRUNCATED: PREFIX + TAIL ...]\n'
    streams={}
    for name,raw,text,budget in zip(('stdout','stderr'),(stdout,stderr),encoded,budgets):
        truncated=len(text)>budget
        if not truncated:retained=text.decode('utf-8');prefix_bytes=len(text);tail_bytes=0
        elif budget<len(marker):retained='';prefix_bytes=tail_bytes=0
        else:
            prefix=(budget-len(marker))//2;tail=budget-len(marker)-prefix
            start=text[:prefix].decode('utf-8','ignore');end=text[-tail:].decode('utf-8','ignore') if tail else ''
            retained=start+marker.decode()+end;prefix_bytes=len(start.encode());tail_bytes=len(end.encode())
        receipt[name]=retained
        streams[name]={'captured_bytes':len(raw),'full_bytes':len(raw) if capture_complete else None,
            'full_sha256':hashlib.sha256(raw).hexdigest() if capture_complete else None,
            'captured_sha256':hashlib.sha256(raw).hexdigest(),'truncated':truncated,
            'retained_utf8_bytes':len(retained.encode()),'prefix_utf8_bytes':prefix_bytes,'tail_utf8_bytes':tail_bytes}
    complete=stdout+b'\n'+stderr
    error_found=re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',complete) is not None
    digest=hashlib.sha256();digest.update(stdout);digest.update(stderr)
    receipt['archive_log']={'capture_complete':capture_complete,'raw_capture_limit_bytes':ARCHIVE_RAW_CAP,
        'retention_limit_bytes':ARCHIVE_RETAIN_CAP,'captured_total_bytes':len(stdout)+len(stderr),
        'full_total_bytes':len(stdout)+len(stderr) if capture_complete else None,
        'full_sha256':digest.hexdigest() if capture_complete else None,'hash_order':'stdout bytes followed by stderr bytes; individual lengths and hashes retained',
        'retained_utf8_bytes':sum(row['retained_utf8_bytes'] for row in streams.values()),
        'truncated':any(row['truncated'] for row in streams.values()),'streams':streams,
        'error_marker_found':error_found,'error_scan_complete':capture_complete,
        'error_scan_scope':'all captured original stdout and stderr bytes, before retention truncation'}
    need(receipt['archive_log']['retained_utf8_bytes']<=ARCHIVE_RETAIN_CAP,'archive-retention-byte-limit')

