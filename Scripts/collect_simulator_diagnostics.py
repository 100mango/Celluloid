#!/usr/bin/env python3
"""Bounded app-only diagnostics for this synthetic-data CI runner, no broad sysdiagnose."""
import pathlib, subprocess, time
from original_ios_process_guard import active,StagedDiagnosticCommands
STAGED=active()
diagnostic=StagedDiagnosticCommands('diagnostics') if STAGED else None
marker = pathlib.Path('/tmp/current-celluloid-simulator')
if marker.exists():
    device = marker.read_text().strip()
    try:
        command=['xcrun', 'simctl', 'spawn', device, 'log', 'show', '--last', '3m', '--style', 'compact',
            '--predicate', 'process == "Celluloid" OR eventMessage CONTAINS "Mango.Celluloid"']
        output=diagnostic.run(command) if diagnostic is not None else subprocess.run(command,capture_output=True,text=True,timeout=45)
        print('CELLULOID_RUNTIME_DIAGNOSTICS_BEGIN')
        print('\n'.join(output.stdout.splitlines()[-250:])[-45000:])
        print(output.stderr[-2000:])
        print('CELLULOID_RUNTIME_DIAGNOSTICS_END')
    except subprocess.TimeoutExpired:
        print('App-only runtime diagnostics timed out after 45s')
    if not STAGED:
        subprocess.run(['xcrun', 'simctl', 'shutdown', device], timeout=30, check=False)
reports = pathlib.Path.home() / 'Library/Logs/DiagnosticReports'
for report in sorted(reports.glob('Celluloid*.ips'), key=lambda p:p.stat().st_mtime, reverse=True)[:3]:
    if time.time() - report.stat().st_mtime < 1800:
        print('CELLULOID_CRASH_REPORT_BEGIN', report.name)
        print(report.read_text(errors='replace')[:18000])
        print('CELLULOID_CRASH_REPORT_END')

if diagnostic is not None:diagnostic.finish()
