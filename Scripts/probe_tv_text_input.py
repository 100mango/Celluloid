#!/usr/bin/env python3
"""Bounded SDK availability probe; never equates a compile with keyboard E2E."""
import json,os,subprocess,sys
from pathlib import Path
temp=Path(os.environ['RUNNER_TEMP'])
sdk=subprocess.check_output(['xcrun','--sdk','appletvsimulator','--show-sdk-path'],text=True).strip()
platform=Path(subprocess.check_output(['xcrun','--sdk','appletvsimulator','--show-sdk-platform-path'],text=True).strip())
source=temp/'CelluloidTVTextInputProbe.swift'
source.write_text('import XCTest\n@MainActor func probe(_ field: XCUIElement) { if #available(tvOS 27.0, *) { field.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:5)+"TV 世界") } }\n')
command=['xcrun','--sdk','appletvsimulator','swiftc','-typecheck','-swift-version','5','-sdk',sdk,'-target','arm64-apple-tvos17.0-simulator','-F',str(platform/'Developer/Library/Frameworks'),'-I',str(platform/'Developer/usr/lib'),str(source)]
try:
 result=subprocess.run(command,capture_output=True,text=True,timeout=90)
 report={'compiled':result.returncode==0,'exit_code':result.returncode,'command':command,'diagnostic':(result.stdout+result.stderr)[-6000:],'runtime_keyboard_coverage':False}
except subprocess.TimeoutExpired:
 report={'compiled':False,'error':'bounded typecheck exceeded90 seconds','runtime_keyboard_coverage':False}
(temp/'tv-text-input-probe.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,ensure_ascii=False))
if report['compiled']:(temp/'tv-typetext-supported').write_text('SDK typecheck passed; actual focused-field execution is still required\n')

if not report['compiled']:
 diagnostic=report.get('diagnostic','')
 if 'typeText' in diagnostic and 'unavailable' in diagnostic and 'tvOS' in diagnostic:
  print('TV_NATIVE_TEXT_INPUT unsupported SDK API; a real remote-keyboard route remains a required separate gate')
 else:
  raise SystemExit('TV keyboard SDK probe failed for an unclassified build/infrastructure reason')
