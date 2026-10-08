#!/usr/bin/env python3
"""Require catalog entries for native UI literals; persisted IDs and user data are excluded."""
from pathlib import Path
import re,json
ROOT=Path(__file__).resolve().parents[1]
pattern=re.compile(r'"((?:\\.|[^"\\])*)"\s*=\s*"((?:\\.|[^"\\])*)"\s*;')
def catalog(language):
    text=(ROOT/f'Platforms/Resources/{language}.lproj/Localizable.strings').read_text()
    entries=pattern.findall(text);keys=[x[0] for x in entries]
    assert len(keys)==len(set(keys)),f'Duplicate keys in {language}'
    return set(keys)
english,chinese=catalog('en'),catalog('zh-Hans')
assert english==chinese,f'Catalog mismatch: {english^chinese}'
# Integer SwiftUI interpolation uses the extracted Int format; user-photo data rows
# contain only data and punctuation, with no translatable prose.
formats={r'Edit Selected Photos (\(selected.count))':'Edit Selected Photos (%lld)',r'\(index + 1). \(source.displayName)':None}
literal=re.compile(r'(?:Text|Button|Picker|NavigationLink|Label|TextField|Toggle|NSLocalizedString|accessibilityLabel|navigationTitle|confirmationDialog|alert|help|Menu|number|cropSlider)\(\s*"((?:\\.|[^"\\])*)"')
missing=[]
for path in (ROOT/'Platforms').rglob('*.swift'):
    if any('Tests' in part for part in path.parts):continue
    values=literal.findall(path.read_text())+re.findall(r'TVAdjustButtons\(title:\s*"((?:\\.|[^"\\])*)"',path.read_text())
    for raw in values:
        key=formats.get(raw,raw)
        if key is None or not key or key in ['←','↑','↓','→','−','+'] or key.startswith('https://'):continue
        if key not in chinese:missing.append((str(path.relative_to(ROOT)),key))
if missing:
    print(json.dumps({'missing':sorted(set(missing))},ensure_ascii=False,indent=2));raise SystemExit(1)
print(json.dumps({'catalog_keys':len(english),'native_literal_catalog_check':'passed'}))
