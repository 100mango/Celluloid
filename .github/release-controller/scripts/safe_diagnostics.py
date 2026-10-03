"""Conservative fixed-output Apple error classification. Never echo log content.

A category is a diagnostic hint, not authority to retry or broaden permissions.
Only finite, reviewed labels/codes below can leave the private runner.
Unknown input, unreadable/oversized logs and all uncaught failures stay redacted.
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys

MAX_LOG_BYTES=8*1024*1024
# Patterns are intentionally restricted to familiar error wording. They have
# no captures, dynamic formatting, URLs, paths or reflected request content.
CATEGORY_PATTERNS={
    'AUTHENTICATION_REJECTED': (
        r'\bauthentication credentials are missing or invalid\b',
        r'\bunable to authenticate\b',
        r'\b(?:http(?: status)?|status code)\s*[:=]?\s*401\b',
    ),
    'PERMISSION_DENIED': (
        r'\binsufficient permissions?\b',
        r'\bnot authorized to (?:access|use|perform)\b',
        r'\b(?:http(?: status)?|status code)\s*[:=]?\s*403\b',
    ),
    'PROVISIONING_PROFILE_UNAVAILABLE': (
        r'\bno profiles for\b',
        r'\bno matching provisioning profiles? found\b',
        r'\brequires a provisioning profile\b',
    ),
    'SIGNING_IDENTITY_UNAVAILABLE': (
        r'\bno signing certificate\b',
        r'\bno valid signing identities\b',
        r'\bcould not find a valid signing identity\b',
    ),
    'CLOUD_CERTIFICATE_ACCESS_DENIED': (
        r'\bpermission to use (?:the )?cloud[- ]managed distribution certificate\b',
        r'\bcloud signing permission error\b',
    ),
    'ARCHIVE_UNSIGNED_OR_UNEXPORTABLE': (
        r'\barchive (?:is not signed|is unsigned|cannot be exported)\b',
        r'\bdoes not contain a single[- ]bundle application\b',
        r'\bnot a valid archive\b',
    ),
    'ENTITLEMENT_PROFILE_MISMATCH': (
        r'\bdoesn.t include the [^\r\n]{1,100} entitlement\b',
        r'\bdoesn.t match the entitlements\b',
        r'\binvalid code signing entitlements\b',
    ),
    'AGREEMENT_OR_MEMBERSHIP_BLOCKED': (
        r'\b(?:agreement|contract) (?:has expired|must be accepted|needs to be accepted)\b',
        r'\b(?:program )?membership (?:has expired|is expired)\b',
    ),
    'NETWORK_OR_SERVICE_UNAVAILABLE': (
        r'\b(?:request|connection) timed out\b',
        r'\bcould not connect to the server\b',
        r'\b(?:http(?: status)?|status code)\s*[:=]?\s*(?:429|500|502|503|504)\b',
    ),
    'BUILD_VERSION_CONFLICT': (
        r'\bduplicate binary upload\b',
        r'\bbundle version (?:must be higher|has already been used)\b',
        r'\bCFBundleVersion\b[^\r\n]{0,120}\b(?:higher|previously uploaded|already been used)\b',
    ),
}
# Codes are returned only if they exactly match this finite allowlist. Unknown
# codes are not repeated, even if they look like familiar Apple identifiers.
CODE_CATEGORIES={
    'ITMS-90161':'PROVISIONING_PROFILE_UNAVAILABLE',
    'ITMS-90035':'SIGNATURE_VALIDATION_FAILED',
    'ITMS-90164':'ENTITLEMENT_PROFILE_MISMATCH',
    'ITMS-90165':'ENTITLEMENT_PROFILE_MISMATCH',
    'ITMS-90186':'BUILD_VERSION_CONFLICT',
    'ITMS-90062':'BUILD_VERSION_CONFLICT',
}
UNKNOWN={'categories':['UNCLASSIFIED_REDACTED'],'codes':[], 'next_step':'STOP_FOR_SCOPED_DIAGNOSTIC_PLAN'}

def classify_text(text):
    categories={name for name,patterns in CATEGORY_PATTERNS.items() if any(re.search(p,text,re.IGNORECASE) for p in patterns)}
    codes={code for code in CODE_CATEGORIES if re.search(r'(?<![A-Z0-9_-])'+re.escape(code)+r'(?![A-Z0-9_-])',text)}
    categories.update(CODE_CATEGORIES[code] for code in codes)
    if not categories:return dict(UNKNOWN)
    return {'categories':sorted(categories),'codes':sorted(codes),'next_step':'STOP_AND_REVIEW_SCOPED_CAUSE'}

def classify_file(path):
    try:
        p=pathlib.Path(path)
        if not p.is_file() or p.is_symlink() or p.stat().st_size>MAX_LOG_BYTES:return dict(UNKNOWN)
        with p.open('rb') as f:data=f.read(MAX_LOG_BYTES+1)
        if len(data)>MAX_LOG_BYTES:return dict(UNKNOWN)
        return classify_text(data.decode('utf-8',errors='replace'))
    except Exception:return dict(UNKNOWN)

def main():
    # Argument-parser errors never show the private log contents. Production
    # callers supply only constant phase names and the runner-local log path.
    p=argparse.ArgumentParser();p.add_argument('--log',required=True);p.add_argument('--phase',choices=['export','upload'],required=True);args=p.parse_args()
    result=classify_file(args.log)
    result['phase']=args.phase
    print('SAFE_APPLE_DIAGNOSTIC '+json.dumps(result,sort_keys=True,separators=(',',':')))

if __name__=='__main__':
    try: main()
    except Exception:
        print('SAFE_APPLE_DIAGNOSTIC '+json.dumps(UNKNOWN,sort_keys=True,separators=(',',':')))
        sys.exit(1)
