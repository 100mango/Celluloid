"""Pure bounded file/summary primitives extracted unchanged from successful Mac capture."""
import json
import math
import stat
MAX_SOURCE=5_000_000

def require(value, message):
    if not value: raise ValueError(message)

def strict_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    def invalid(value): raise ValueError('Nonfinite JSON number')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)

def read_file(path, limit=MAX_SOURCE):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
            'Unsafe or oversized evidence file: ' + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    require((info.st_ino, info.st_size, info.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns),
            'Evidence changed during read')
    return raw

def number(value): return type(value) in (int,float) and math.isfinite(value)
def integer(value, low=0): return type(value) is int and value >= low

def admit_summary(raw, test):
    """Reject impossible one-case summaries before exporting any attachments.

    This is only admission; the original complete receipt/product validator
    still runs after export. No identity or acceptance is inferred here.
    """
    summary=strict_json(raw)
    require(isinstance(summary,dict),'bad-pre-export-summary')
    counts=('passedTests','failedTests','skippedTests','expectedFailures','totalTestCount')
    require(all(integer(summary.get(key)) for key in counts),'invalid-pre-export-counts')
    require(summary['totalTestCount']==1 and summary['skippedTests']==0 and summary['expectedFailures']==0 and
        summary['passedTests']+summary['failedTests']==1,'not-exact-pre-export-case')
    passed=summary['passedTests']==1
    require(summary.get('result')==('Passed' if passed else 'Failed') and test['exit']==(0 if passed else 65),
        'pre-export-outcome-mismatch')
    start,end=summary.get('startTime'),summary.get('finishTime')
    require(number(start) and number(end) and test['startedEpoch']<=start<end<=test['finishedEpoch'],
        'pre-export-summary-outside-test-clock')
