#!/usr/bin/env python3
"""Fail-closed receipt for real PHPicker input, appearance and app-action clocks.

No PHPicker subclass, swizzle, synthetic lifecycle event, or private hierarchy API.
The native evidence is an unmodified XCTest runner diagnostic notification. Its
payload has a PID but NO picker object address. We match only a unique, serialized
presentation window for that PID, retaining this limitation in the receipt.

Input contract v1 (plain key=value records, UUIDs are canonical, case-insensitive):
  PICKER_APP_TRACE run=UUID instance=UUID event=... picker=none|0xHEX pid=INT
      uptime_seconds=FLOAT wall_seconds=FLOAT
  PICKER_UI_TRACE run=UUID iteration=INT event=... uptime_seconds=FLOAT
      wall_seconds=FLOAT [actual return-state Boolean fields]
  PICKER_AX_QUERY run=UUID iteration=INT property=exists|isEnabled|isHittable
      value=true|false duration_seconds=FLOAT end_uptime_seconds=FLOAT
      wall_seconds=FLOAT
App events: app-beautify-tap, picker-construction-returned,
  picker-cancel-delegate OR picker-selection-delegate, root-cover-dismissal-completed. Additional diagnostics
  may coexist, but identities, pointers and clocks must remain consistent.
UI events: run-begin, run-end, tap-command-start, tap-command-returned,
  cancel-command-start OR selection-command-start,
  home-interactive-after-dismiss OR editor-interactive-after-selection.
Return state must contain home_exists/home_hittable/picker_exists or
  editor_exists/editor_enabled/editor_hittable/picker_candidates_exist (actual bools).
  Home return additionally records via=cancel|editor. Grid candidate absence is
  only auxiliary evidence; genuine native ViewDidDisappear proves teardown.
At least run-begin and run-end MUST be NSLog records with runner timestamp/PID
  prefixes, so wall clocks can be checked against the native log's clock domain.
Each tap window MUST contain exactly one genuine runner "started activity"
  Synthesize event. Acceptance starts there, retaining event delivery and app
  input-queue delay. App-action-to-appearance is a secondary decomposition only.
New AX observations also retain start_uptime_seconds/start_wall_seconds, checked
  against the existing end and duration fields. Original failed observations
  remain failed; missing or ambiguous clocks and identity are never repaired.
Official relevant raw diagnostics and their source/hash manifest are retained
  before parsing, so failed validation cannot destroy the underlying evidence.

Runner identity JSON v1 (generated from the checked checkout/build/artifact):
  schema_version: 1, source_sha: 40 lowercase hex, source_tree: 40 lowercase hex,
  app_binary_sha256: 64 lowercase hex, xcresult_sha256: bundle_digest(bundle),
  runs: [{run_id: UUID, expected_cancel_count: 3, expected_selected_count: 0}, ...]
These fields are checked against independent CLI expectations and actual files.
The identity JSON is an explicit runner attestation, not a code signature: the
runner must bind the build product to its checkout BEFORE executing tests.

Exporter: installed `xcrun xcresulttool help export` is authoritative. Prefer
advertised diagnostics export; otherwise use Apple's documented legacy object
API and diagnosticsRef from the root object. Every command is time-bounded.
Never scrape undocumented xcresult storage or fabricate an appearance event.
Apple command reference: https://developer.apple.com/documentation/xcode-release-notes/xcode-16_3-release-notes
Apple picker restriction: https://developer.apple.com/documentation/photosui/phpickerviewcontroller
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

SCHEMA_VERSION = 1
BUDGET_SECONDS = 3.0
CLOCK_TOLERANCE = 0.050
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_FILES = 10000
MARKER = re.compile(r"\b(PICKER_APP_TRACE|PICKER_UI_TRACE|PICKER_AX_QUERY) (?P<fields>.*)$")
PREFIX = re.compile(r"^(?:(?P<day>\d{4}-\d{2}-\d{2}) )?(?P<clock>\d{2}:\d{2}:\d{2}\.\d{3,6})(?P<zone>[+-]\d{4})? (?P<process>[\w.-]+)\[(?P<pid>\d+):\d+\](?: \[[^\]]*\])? ")
NATIVE = re.compile(r"^(?P<prefix>.*)Received kAXUserTestingNotification from AX element pid: (?P<app_pid>\d+), elementOrHash\.elementID: (?P<ax_id>[\d.]+): \{\n(?P<body>(?:[^\n]*\n){1,12}?)\}", re.MULTILINE)
SYNTHESIS = re.compile(r"^(?P<prefix>.*?)<XCTContext: 0x[0-9a-fA-F]+> started activity <XCActivityRecord: (?P<activity>0x[0-9a-fA-F]+)> \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}: Synthesize event\s*$", re.MULTILINE)
HISTORICAL = re.compile(r"(?:SWIFTUI_PICKER_ENTRY|PICKER_AUTOMATION_DIAGNOSTIC) .*?elapsed_seconds=([0-9.]+)")


class EvidenceError(ValueError):
    """Missing, ambiguous, inconsistent, or unsupported evidence."""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"Invalid numeric field {name}") from exc
    require(math.isfinite(result) and result >= 0, f"Nonfinite/negative {name}")
    return result


def identifier(value, name):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise EvidenceError(f"Invalid UUID {name}") from exc


def sha256_file(path):
    require(path.is_file() and not path.is_symlink(), f"Not a regular file: {path}")
    require(0 < path.stat().st_size <= MAX_TOTAL_BYTES, f"Invalid file size: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundle_digest(bundle):
    """sha256(canonical JSON sorted [{path,bytes,sha256}]); reject symlinks."""
    require(bundle.is_dir() and not bundle.is_symlink(), "Missing xcresult directory")
    manifest, total = [], 0
    for path in sorted(bundle.rglob("*")):
        require(not path.is_symlink(), "Symlink in xcresult")
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        require(total <= MAX_TOTAL_BYTES and len(manifest) < MAX_FILES, "Oversized xcresult")
        # Empty regular files are allowed in the bundle; executables are not.
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest.append({"path": path.relative_to(bundle).as_posix(), "bytes": size, "sha256": digest.hexdigest()})
    require(manifest and (bundle / "Info.plist").is_file(), "Invalid xcresult bundle")
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_identity(identity, bundle, executable, expected_sha, expected_tree, expected_runs):
    require(isinstance(identity, dict), "Identity must be a JSON object")
    require(identity.get("schema_version") == SCHEMA_VERSION, "Unsupported identity schema")
    for key, expected in (("source_sha", expected_sha), ("source_tree", expected_tree)):
        require(bool(re.fullmatch(r"[0-9a-f]{40}", str(expected))), f"Invalid expected {key}")
        require(identity.get(key) == expected, f"Wrong {key}")
    require(identity.get("xcresult_sha256") == bundle_digest(bundle), "xcresult identity/hash mismatch")
    require(identity.get("app_binary_sha256") == sha256_file(executable), "Built executable hash mismatch")
    actual = {}
    require(isinstance(identity.get("runs"), list), "Missing identity runs")
    for item in identity["runs"]:
        require(isinstance(item, dict), "Invalid identity run")
        run = identifier(item.get("run_id"), "run_id")
        require(run not in actual, "Duplicate identity run")
        counts = (item.get("expected_cancel_count"), item.get("expected_selected_count"))
        require(all(type(n) is int and n >= 0 for n in counts) and sum(counts) > 0, "Invalid expected run counts")
        actual[run] = counts
    require(actual == expected_runs and actual, "Run identity/count expectation mismatch")
    return actual


def _run_tool(command, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, "xcresult export total timeout")
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=min(30, remaining), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"xcresult export unavailable/timed out: {exc}") from exc
    require(len(result.stdout) + len(result.stderr) <= MAX_LOG_BYTES, "Oversized xcresulttool output")
    require(result.returncode == 0, f"xcresulttool failed: {' '.join(command)}: {result.stderr.decode(errors='replace')[:1000]}")
    return result.stdout.decode("utf-8", errors="strict")


def export_diagnostics(bundle, destination, run_tool=_run_tool):
    """Only run syntax confirmed by installed help or documented legacy API."""
    require(not destination.exists(), "Diagnostics destination must be fresh")
    deadline = time.monotonic() + 45
    base = ["xcrun", "xcresulttool"]
    export_help = run_tool(base + ["help", "export"], deadline)
    if re.search(r"^\s+diagnostics(?:\s|$)", export_help, re.MULTILINE):
        help_text = run_tool(base + ["help", "export", "diagnostics"], deadline)
        require(all(flag in help_text for flag in ("--path", "--output-path")), "Unsupported diagnostics export syntax")
        run_tool(base + ["export", "diagnostics", "--path", str(bundle), "--output-path", str(destination)], deadline)
        return {"method": "xcresulttool export diagnostics", "help_sha256": hashlib.sha256(help_text.encode()).hexdigest()}
    # Official 16.3 docs enumerate this legacy API. Runtime help must agree.
    get_help = run_tool(base + ["help", "get", "object"], deadline)
    object_help = run_tool(base + ["help", "export", "object"], deadline)
    require(all(flag in get_help for flag in ("--legacy", "--path", "--format")), "Unsupported root object export syntax")
    require(all(flag in object_help for flag in ("--legacy", "--path", "--output-path", "--id", "--type")) and "directory" in object_help, "Unsupported diagnostic object export syntax")
    root = json.loads(run_tool(base + ["get", "object", "--legacy", "--path", str(bundle), "--format", "json"], deadline))
    refs = []
    for action in root.get("actions", {}).get("_values", []):
        ref = action.get("actionResult", {}).get("diagnosticsRef", {}).get("id", {}).get("_value")
        if ref:
            require(isinstance(ref, str) and len(ref) < 512 and not ref.startswith("-"), "Invalid diagnostics reference")
            refs.append(ref)
    require(0 < len(refs) <= 8 and len(set(refs)) == len(refs), "Missing/ambiguous diagnostics references")
    destination.mkdir(parents=True)
    for index, ref in enumerate(refs):
        run_tool(base + ["export", "object", "--legacy", "--path", str(bundle), "--output-path", str(destination / str(index)), "--id", ref, "--type", "directory"], deadline)
    return {"method": "xcresulttool legacy diagnosticsRef directory", "reference_count": len(refs), "help_sha256": hashlib.sha256((get_help + object_help).encode()).hexdigest()}


def read_diagnostics(directory):
    """Read bounded text streams; byte-identical exported copies count once."""
    logs, total, hashes = {}, 0, set()
    paths = sorted(directory.rglob("*"))
    require(len(paths) <= MAX_FILES, "Too many diagnostics files")
    for path in paths:
        require(not path.is_symlink(), "Symlink in exported diagnostics")
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        require(total <= MAX_TOTAL_BYTES, "Diagnostics too large")
        if size == 0 or size > MAX_LOG_BYTES:
            continue
        data = path.read_bytes()
        if b"PICKER_" not in data and b"Received kAXUserTestingNotification" not in data:
            continue
        require(b"\x00" not in data, "Relevant log is binary; unsupported exporter output")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceError("Relevant diagnostic is not UTF-8") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest not in hashes:
            logs[path.relative_to(directory).as_posix()] = content
            hashes.add(digest)
    require(logs, "No native/app trace logs exported")
    return logs


def prefix_info(line):
    match = PREFIX.match(line)
    return match.groupdict() if match else None


def prefix_wall(prefix, near, zone):
    require(prefix is not None, "Missing native runner timestamp prefix")
    clock = datetime.strptime(prefix["clock"], "%H:%M:%S.%f").time()
    if prefix["zone"]:
        z = prefix["zone"]
        minutes = int(z[1:3]) * 60 + int(z[3:5])
        tz = timezone(timedelta(minutes=minutes if z[0] == "+" else -minutes))
    else:
        tz = zone
    if prefix["day"]:
        day = datetime.strptime(prefix["day"], "%Y-%m-%d").date()
        return datetime.combine(day, clock, tz).timestamp()
    day = datetime.fromtimestamp(near, tz).date()
    possibilities = [datetime.combine(day + timedelta(days=d), clock, tz).timestamp() for d in (-1, 0, 1)]
    result = min(possibilities, key=lambda value: abs(value - near))
    require(abs(result - near) < 12 * 3600, "Ambiguous native timestamp day")
    return result


def extract_native_events(logs):
    """Extract genuine syntax without claiming identity, timing or acceptance."""
    native = []
    for path, content in logs.items():
        for match in NATIVE.finditer(content):
            body = match.group("body")
            if not re.search(r"^\s+controllerClass = PHPickerViewController;$", body, re.MULTILINE):
                continue
            events = re.findall(r"^\s+event = (\w+);$", body, re.MULTILINE)
            require(len(events) == 1 and events[0] in ("ViewDidAppear", "ViewDidDisappear"), "Malformed native PHPicker event")
            prefix = prefix_info(match.group("prefix"))
            require(prefix and prefix["process"].endswith("UITests-Runner"), "PHPicker event did not originate in XCTest runner log")
            native.append({"event": events[0], "pid": match.group("app_pid"), "prefix": prefix, "path": path, "line": content.count("\n", 0, match.start()) + 1})
    return native


def parse_logs(logs):
    traces, native, historical = [], extract_native_events(logs), []
    for path, content in logs.items():
        for line_no, line in enumerate(content.splitlines(), 1):
            match = MARKER.search(line)
            if not match:
                continue
            prefix = prefix_info(line)
            require(match.start() == 0 or prefix is not None, f"Unrecognized trace prefix: {path}:{line_no}")
            values = {}
            for token in match.group("fields").split():
                require("=" in token, f"Malformed trace token: {path}:{line_no}")
                key, value = token.split("=", 1)
                require(key not in values and value != "", f"Duplicate/empty trace field: {key}")
                values[key] = value
            values["kind"] = match.group(1)
            values["run"] = identifier(values.get("run"), "trace run")
            values["wall"] = number(values.get("wall_seconds"), "wall_seconds")
            values["uptime"] = number(values.get("end_uptime_seconds") if values["kind"] == "PICKER_AX_QUERY" else values.get("uptime_seconds"), "uptime")
            values["prefix"], values["path"], values["line"] = prefix, path, line_no
            values["source_locations"] = [{"file": path, "line": line_no}]
            if values["kind"] == "PICKER_APP_TRACE":
                values["instance"] = identifier(values.get("instance"), "presentation instance")
                require(re.fullmatch(r"[1-9]\d*", values.get("pid", "")), "Invalid app PID")
                require(re.fullmatch(r"none|0x[0-9a-fA-F]+", values.get("picker", "")), "Invalid picker pointer")
            else:
                require(re.fullmatch(r"\d+", values.get("iteration", "")), "Invalid iteration")
                values["iteration"] = int(values["iteration"])
            if values["kind"] == "PICKER_AX_QUERY":
                require(values.get("property") in ("exists", "isEnabled", "isHittable"), "Unsupported AX query")
                require(values.get("value") in ("true", "false"), "Invalid AX boolean")
                values["duration"] = number(values.get("duration_seconds"), "query duration")
                require(values["duration"] <= values["uptime"], "AX duration exceeds clock")
                if "start_uptime_seconds" in values or "start_wall_seconds" in values:
                    began = number(values.get("start_uptime_seconds"), "query start uptime")
                    began_wall = number(values.get("start_wall_seconds"), "query start wall")
                    require(abs(values["uptime"] - values["duration"] - began) <= 0.000001,
                            "AX start/end/duration clocks disagree")
                    require(began_wall <= values["wall"] and abs((values["wall"]-began_wall)-values["duration"]) <= CLOCK_TOLERANCE,
                            "AX start/end wall clocks disagree")
            traces.append(values)
        historical += [number(value, "historical elapsed") for value in HISTORICAL.findall(content)]
    # Exported console and runner streams can contain the same original NSLog.
    # Scalar copies require identical full wall+uptime+identity fields. Native
    # same-stream duplicate blocks remain ambiguous because clock precision is
    # only milliseconds and cannot distinguish a true repeated notification.
    unique, seen = [], {}
    for record in traces:
        key = tuple(sorted((k, v) for k, v in record.items() if k not in ("prefix", "path", "line", "source_locations")))
        prior = seen.get(key)
        if prior is not None:
            prior["source_locations"].extend(record["source_locations"])
            if record["prefix"] and (not prior["prefix"] or not prior["prefix"]["process"].endswith("UITests-Runner")):
                prior["prefix"] = record["prefix"]
            continue
        seen[key] = record
        unique.append(record)
    native_unique, seen_native = [], {}
    for record in native:
        p = record["prefix"]
        key = (record["event"], record["pid"], p["pid"], p["clock"])
        prior = seen_native.get(key)
        if prior is not None and prior["path"] != record["path"]:
            continue
        seen_native[key] = record
        native_unique.append(record)
    return unique, native_unique, historical


def extract_synthesis_events(logs):
    """Genuine runner activity start, before event delivery and app queue delay.

    Do not use the delayed xcodebuild activity mirror, an elapsed stdout label,
    an app marker, or completion of synthesis as the input start.
    """
    events, seen = [], {}
    for path, content in logs.items():
        for match in SYNTHESIS.finditer(content):
            prefix = prefix_info(match.group("prefix"))
            require(prefix and prefix["process"].endswith("UITests-Runner"), "Input synthesis did not originate in XCTest runner log")
            key = (prefix["pid"], prefix["day"], prefix["clock"], match.group("activity"))
            prior = seen.get(key)
            if prior is not None and prior["path"] != path:
                continue
            record = {"prefix": prefix, "activity": match.group("activity"), "path": path,
                      "line": content.count("\n", 0, match.start()) + 1}
            seen[key] = record
            events.append(record)
    return events


def retain_diagnostics(logs, destination, export, identity):
    """Retain bounded official text before validation, including failed runs."""
    require(not destination.exists(), "Diagnostics evidence destination must be fresh")
    destination.mkdir(parents=True)
    manifest, total = [], 0
    for original, content in sorted(logs.items()):
        path = Path(original)
        require(not path.is_absolute() and ".." not in path.parts, "Unsafe diagnostic path")
        data = content.encode("utf-8"); total += len(data)
        require(total <= MAX_LOG_BYTES, "Relevant diagnostic text exceeds retained bound")
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest.append({"path": original, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    require(manifest, "No diagnostic text to retain")
    record = {"identity": identity, "export": export, "logs": manifest,
              "receipt_acceptance": "not implied by retention"}
    (destination / "retained-manifest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return str(destination)


def one(items, description):
    require(len(items) == 1, f"Expected exactly one {description}; found {len(items)}")
    return items[0]


def event(items, name):
    return one([item for item in items if item.get("event") == name], name)


def assert_return_state(record, selected):
    wanted = {"picker_candidates_exist" if selected else "picker_exists": "false"}
    wanted.update({"editor_exists": "true", "editor_enabled": "true", "editor_hittable": "true"} if selected else {"home_exists": "true", "home_hittable": "true"})
    require(all(record.get(key) == value for key, value in wanted.items()), "Actual return-state booleans did not establish successful return")


def validate_fixture_manifest(manifest, identity):
    require(isinstance(manifest, dict), "Fixture manifest must be a JSON object")
    require(manifest.get("schema") == "celluloid.swiftui.seeded-library.v1", "Unsupported synthetic fixture manifest schema")
    for fixture_key, identity_key in (("source_sha", "source_sha"), ("device_id", "device_id"),
                                     ("run_id", "ci_run_id"), ("run_attempt", "ci_run_attempt")):
        require(identity.get(identity_key) is not None and str(manifest.get(fixture_key)) == str(identity[identity_key]), f"Fixture {fixture_key} identity mismatch")
    fixtures = manifest.get("fixtures", [])
    require(isinstance(fixtures, list) and len(fixtures) == 6 and manifest.get("fixture_count") == 6, "Expected exactly six verified synthetic fixtures")
    require(manifest.get("authorization_read_write") == "authorized", "Synthetic library authorization is not established")
    require(manifest.get("baseline_id_set_preserved") is True, "Baseline preservation is not established")
    sets = {}
    for name in ("baseline_asset_ids", "seeded_asset_ids", "added_asset_ids"):
        values = manifest.get(name)
        require(isinstance(values, list) and all(isinstance(v, str) and v.strip() for v in values), f"Invalid {name}")
        require(values == sorted(set(values)), f"Duplicate/unsorted {name}")
        sets[name] = set(values)
    baseline, seeded, added = (sets[k] for k in ("baseline_asset_ids", "seeded_asset_ids", "added_asset_ids"))
    require(baseline <= seeded and seeded - baseline == added and len(added) == 6, "Synthetic library membership/delta mismatch")
    for field, actual in (("baseline_asset_count", len(baseline)), ("seeded_asset_count", len(seeded))):
        require(type(manifest.get(field)) is int and manifest[field] == actual, f"Invalid actual {field}")
    identifiers = []
    for item in fixtures:
        require(isinstance(item, dict) and isinstance(item.get("identifier"), str) and item["identifier"].strip(), "Missing fixture identifier")
        require(re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))), "Invalid fixture hash")
        require(isinstance(item.get("filename"), str) and item["filename"], "Missing fixture filename")
        require(all(type(item.get(k)) is int and item[k] > 0 for k in ("width", "height")), "Invalid fixture dimensions")
        require(isinstance(item.get("creation_date_utc"), str) and item["creation_date_utc"], "Missing fixture creation date")
        try:
            created = datetime.fromisoformat(item["creation_date_utc"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceError("Invalid fixture creation date") from exc
        require(created.tzinfo is not None and created.utcoffset() == timedelta(0), "Fixture creation date must be UTC")
        identifiers.append(item["identifier"])
    require(len(set(identifiers)) == len(identifiers), "Duplicate fixture identifiers")
    require(set(identifiers) == added, "Fixture identities do not equal verified new assets")
    expected_filenames = {"celluloid-fixture.png", "celluloid-fixture-2.png"} | {f"celluloid-composition-{i}.png" for i in range(4)}
    require({item["filename"] for item in fixtures} == expected_filenames, "Unexpected synthetic fixture filenames")
    return set(identifiers)


def selected_identity(record):
    try:
        encoded = record.get("selection_base64", "")
        require(len(encoded) <= 8192, "Oversized selected identity evidence")
        value = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise EvidenceError("Invalid encoded selected identity evidence") from exc
    require(isinstance(value, list) and len(value) == 1, "Beautify requires exactly one selected identity")
    require(all(isinstance(item, str) and item.strip() for item in value), "Nil/empty selected identity")
    require(len(set(value)) == len(value), "Duplicate selected identity")
    return value


def validate_logs(logs, expected_runs, log_timezone=timezone.utc, fixture_identifiers=None):
    traces, native, historical = parse_logs(logs)
    synthesis = extract_synthesis_events(logs)
    require({t["run"] for t in traces} == set(expected_runs), "Missing/unexpected trace run identity")
    receipts, used_native = [], set()
    for run, expected_counts in expected_runs.items():
        records = [t for t in traces if t["run"] == run]
        app = [t for t in records if t["kind"] == "PICKER_APP_TRACE"]
        ui = [t for t in records if t["kind"] == "PICKER_UI_TRACE"]
        ax = [t for t in records if t["kind"] == "PICKER_AX_QUERY"]
        begin, end = event(ui, "run-begin"), event(ui, "run-end")
        require(begin["uptime"] < end["uptime"] and begin["wall"] < end["wall"], "Invalid run clock ordering")
        require(all(begin["uptime"] <= r["uptime"] <= end["uptime"] for r in records), "Event outside run clock anchors")
        offsets = [r["wall"] - r["uptime"] for r in records]
        drift = max(offsets) - min(offsets)
        require(drift <= CLOCK_TOLERANCE, "App/runner clock skew or drift exceeds 50ms")
        anchor_errors = []
        for anchor in (begin, end):
            prefix = anchor["prefix"]
            require(prefix and prefix["process"].endswith("UITests-Runner"), "Run clocks need timestamped XCTest runner NSLog anchors")
            error = abs(prefix_wall(prefix, anchor["wall"], log_timezone) - anchor["wall"])
            require(error <= CLOCK_TOLERANCE, "Native log clock differs from run wall clock by >50ms")
            anchor_errors.append(error)
        runner_pid = begin["prefix"]["pid"]
        require(end["prefix"]["pid"] == runner_pid, "Runner process changed within run")
        starts = sorted([r for r in ui if r.get("event") == "tap-command-start"], key=lambda r: r["uptime"])
        require(len(starts) == sum(expected_counts), "Missing/extra picker iterations")
        require([r["iteration"] for r in starts] == list(range(1, len(starts) + 1)), "Noncontiguous/ambiguous iteration identities")
        taps = [r for r in app if r.get("event") == "app-beautify-tap"]
        require(len(taps) == len(starts) and len({r["instance"] for r in taps}) == len(taps), "Missing/duplicate app action/presentation UUID")
        require(len({r["pid"] for r in app}) == 1, "App process changed between repeated presentations")
        require({r["instance"] for r in app} == {r["instance"] for r in taps}, "Orphan app presentation instance")
        counts, previous_return = [0, 0], begin["uptime"]
        for start in starts:
            iteration = start["iteration"]
            local = [r for r in ui if r["iteration"] == iteration]
            tap_return = event(local, "tap-command-returned")
            require(previous_return <= start["uptime"] <= tap_return["uptime"], "Overlapping/out-of-order iterations")
            action = one([r for r in taps if start["uptime"] <= r["uptime"] <= tap_return["uptime"]], "app action in tap-command window")
            inputs = [(s, prefix_wall(s["prefix"], start["wall"], log_timezone)) for s in synthesis
                      if s["prefix"]["pid"] == runner_pid]
            input_event, input_wall = one([(s, wall) for s, wall in inputs
                        if start["wall"] <= wall <= tap_return["wall"]], "native input synthesis in tap-command window")
            require(input_wall <= action["wall"], "App action precedes native input synthesis")
            instance_records = [r for r in app if r["instance"] == action["instance"]]
            require(len({r["pid"] for r in instance_records}) == 1, "App PID changed within presentation")
            require(all(r["uptime"] >= action["uptime"] for r in instance_records), "App lifecycle precedes its action")
            construction = event(instance_records, "picker-construction-returned")
            delegates = [r for r in instance_records if r.get("event") in ("picker-cancel-delegate", "picker-selection-delegate")]
            delegate = one(delegates, "cancel or selected delegate")
            require(action["picker"] == "none" and construction["picker"] != "none", "Invalid action/construction picker pointer")
            pointers = {int(r["picker"], 16) for r in instance_records if r["picker"] != "none"}
            require(len(pointers) == 1 and next(iter(pointers)) > 0 and delegate["picker"] != "none", "Inconsistent/missing app-side picker pointer")
            selected = delegate["event"] == "picker-selection-delegate"
            counts[int(selected)] += 1
            command = event(local, "selection-command-start" if selected else "cancel-command-start")
            returned = event(local, "editor-interactive-after-selection" if selected else "home-interactive-after-dismiss")
            assert_return_state(returned, selected)
            final_home = event(local, "home-interactive-after-dismiss")
            assert_return_state(final_home, False)
            require(final_home.get("via") == ("editor" if selected else "cancel"), "Return path does not match delegate outcome")
            require(final_home["uptime"] >= returned["uptime"], "Home return precedes editor")
            dismissed = event(instance_records, "root-cover-dismissal-completed")
            require(delegate["uptime"] <= dismissed["uptime"] <= final_home["uptime"], "Root dismissal ordering is invalid")
            selection_proof = None
            if selected:
                require(fixture_identifiers, "Selected run requires verified synthetic fixture manifest")
                picked = event(instance_records, "picker-selected-identities")
                resolved = event(instance_records, "resolved-original-identities")
                picked_ids, resolved_ids = selected_identity(picked), selected_identity(resolved)
                require(picked_ids == resolved_ids, "Picker/resolved original identity mismatch or ordering mismatch")
                require(all(value in fixture_identifiers for value in picked_ids), "Selected identity is outside verified synthetic fixtures")
                require(delegate["uptime"] <= picked["uptime"] <= resolved["uptime"] <= returned["uptime"], "Selected original resolution ordering is invalid")
                selection_proof = {"verified_original_count": len(picked_ids), "synthetic_fixture_membership": True,
                                   "identity_array_sha256": hashlib.sha256(json.dumps(picked_ids, separators=(",", ":")).encode()).hexdigest()}
            require(action["uptime"] <= construction["uptime"] <= command["uptime"] <= delegate["uptime"] <= returned["uptime"], "Invalid app/command/return ordering")
            appearances, disappearances = [], []
            for index, n in enumerate(native):
                if n["pid"] != action["pid"] or n["prefix"]["pid"] != runner_pid:
                    continue
                wall = prefix_wall(n["prefix"], action["wall"], log_timezone)
                if construction["wall"] <= wall <= returned["wall"]:
                    if n["event"] == "ViewDidAppear":
                        appearances.append((index, n, wall))
                    else:
                        disappearances.append((index, n, wall))
            appeared = one(appearances, "native PHPicker ViewDidAppear in presentation")
            disappeared = one(disappearances, "native PHPicker ViewDidDisappear in presentation")
            require(appeared[0] not in used_native and disappeared[0] not in used_native, "Native event reused across presentations")
            require(construction["wall"] <= appeared[2] <= command["wall"] <= delegate["wall"] <= disappeared[2] <= returned["wall"], "Invalid native appearance/delegate/disappearance ordering")
            used_native.update((appeared[0], disappeared[0]))
            queries = sorted([r for r in ax if r["iteration"] == iteration], key=lambda r: r["uptime"])
            require(queries and all(tap_return["uptime"] <= q["uptime"] - q["duration"] <= q["uptime"] <= command["uptime"] for q in queries), "AX query outside observation window")
            # Require the successful consecutive polling evaluation, not three
            # unrelated true values straddling intervening failed evaluations.
            successes = [queries[i:i+3] for i in range(max(0, len(queries)-2))
                         if [q["property"] for q in queries[i:i+3]] == ["exists", "isEnabled", "isHittable"]
                         and all(q["value"] == "true" for q in queries[i:i+3])]
            require(successes, "No real consecutive exists/isEnabled/isHittable success")
            success = successes[0]
            require(all(q["wall"] >= appeared[2] for q in success), "Successful AX observation predates native appearance")
            require(all(success[i]["uptime"] <= success[i+1]["uptime"] - success[i+1]["duration"] for i in range(2)), "Overlapping AX query clocks")
            native_elapsed = appeared[2] - action["wall"]
            uncertainty = drift + max(anchor_errors) + 0.001  # runner milliseconds
            native_upper = native_elapsed + uncertainty
            ax_upper = success[-1]["uptime"] - action["uptime"]
            require(native_elapsed >= 0 and ax_upper >= 0, "Negative measured latency")
            native_lower = max(0, native_elapsed - uncertainty)
            native_status = ("passed" if native_upper <= BUDGET_SECONDS else
                             "over_budget_observation" if native_lower > BUDGET_SECONDS else "inconclusive_clock_budget")
            ax_status = "passed" if ax_upper <= BUDGET_SECONDS else "inconclusive_interactivity_budget"
            input_elapsed = appeared[2] - input_wall
            input_upper = input_elapsed + uncertainty
            input_lower = max(0, input_elapsed - uncertainty)
            input_ax_upper = success[-1]["wall"] - input_wall + uncertainty
            input_status = ("passed" if input_upper <= BUDGET_SECONDS else
                            "over_budget_observation" if input_lower > BUDGET_SECONDS else "inconclusive_clock_budget")
            input_ax_status = "passed" if input_ax_upper <= BUDGET_SECONDS else "inconclusive_interactivity_budget"
            receipts.append({"run_id": run, "iteration": iteration, "presentation_id": action["instance"], "app_pid": int(action["pid"]),
                             "picker_pointer": construction["picker"], "native_instance_binding": "same PID and unique serialized presentation window; native notification has no object pointer",
                             "return": "selected_editor" if selected else "cancel_home", "return_verified": True, "selected_original_proof": selection_proof,
                             "input_synthesis_evidence": {"file": input_event["path"], "line": input_event["line"], "activity": input_event["activity"]},
                             "tap_command_to_input_synthesis_seconds": input_wall - start["wall"],
                             "input_synthesis_to_app_action_seconds": action["wall"] - input_wall,
                             "input_synthesis_to_native_appearance_seconds": input_elapsed,
                             "input_synthesis_to_native_appearance_upper_seconds": input_upper,
                             "input_synthesis_to_native_appearance_lower_seconds": input_lower,
                             "input_synthesis_to_native_appearance_budget": input_status,
                             "input_synthesis_to_successful_hittable_upper_seconds": input_ax_upper,
                             "input_synthesis_ax_observability_budget": input_ax_status,
                             "app_action_evidence": action["source_locations"], "successful_hittable_evidence": success[-1]["source_locations"],
                             "root_dismissal_evidence": dismissed["source_locations"],
                             "app_action_to_native_appearance_seconds": native_elapsed,
                             "native_clock_uncertainty_seconds": uncertainty,
                             "app_action_to_native_appearance_upper_seconds": native_upper,
                             "app_action_to_native_appearance_lower_seconds": native_lower,
                             "native_appearance_budget": native_status,
                             "app_action_to_successful_hittable_upper_seconds": ax_upper,
                             "ax_observability_budget": ax_status,
                             "native_evidence": [{"file": n[1]["path"], "line": n[1]["line"], "event": n[1]["event"]} for n in (appeared, disappeared)]})
            previous_return = final_home["uptime"]
        require(tuple(counts) == tuple(expected_counts), "Cancel/selected coverage mismatch")
        require(all(r["iteration"] in ({0} | {s["iteration"] for s in starts}) for r in ui + ax), "Orphan UI/AX iteration")
        # Extra lifecycle notifications for a validated app PID during the run
        # could signal an unbound presentation. Never silently ignore them.
        for index, n in enumerate(native):
            if n["pid"] in {r["pid"] for r in app} and n["prefix"]["pid"] == runner_pid:
                wall = prefix_wall(n["prefix"], begin["wall"], log_timezone)
                if begin["wall"] <= wall <= end["wall"]:
                    require(index in used_native, "Unmatched native PHPicker event in run")
    require(receipts, "No validated presentations")
    passed = all(r["input_synthesis_to_native_appearance_budget"] == r["input_synthesis_ax_observability_budget"] == "passed" for r in receipts)
    return {"schema_version": SCHEMA_VERSION, "status": "passed" if passed else "not_accepted", "budget_seconds": BUDGET_SECONDS,
            "presentations": receipts, "historical_whole_xctest_seconds": sorted(set(historical)),
            "historical_metric_is_acceptance_gate": False,
            "acceptance_start": "XCTest runner input synthesis start; includes delivery and app input-queue delay",
            "app_action_metrics_are_secondary": True,
            "scope": "Input synthesis + native appearance + actual control queries + delegate/return; not photo-library readiness, frame time, or a freeze diagnosis"}


def parse_expected_run(value):
    fields = value.split(":")
    require(len(fields) == 3, "Expected run must be UUID:CANCEL_COUNT:SELECTED_COUNT")
    run = identifier(fields[0], "expected run")
    require(all(re.fullmatch(r"\d+", v) for v in fields[1:]), "Invalid expected run counts")
    counts = tuple(int(v) for v in fields[1:])
    require(sum(counts) > 0, "Empty expected run")
    return run, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xcresult", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--app-binary", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--expected-run", action="append", required=True, help="UUID:CANCEL_COUNT:SELECTED_COUNT; repeat per launch")
    parser.add_argument("--runner-log-timezone", required=True, choices=["UTC"], help="CI must run native test logging in UTC")
    parser.add_argument("--fixture-manifest", type=Path, help="Verified synthetic fixture manifest, required for selected returns")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnostics-output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = {"schema_version": SCHEMA_VERSION, "status": "invalid_evidence", "budget_seconds": BUDGET_SECONDS}
    try:
        expected = [parse_expected_run(v) for v in args.expected_run]
        require(len(dict(expected)) == len(expected), "Duplicate expected run")
        identity = json.loads(args.identity.read_text())
        runs = verify_identity(identity, args.xcresult, args.app_binary, args.expected_source_sha, args.expected_source_tree, dict(expected))
        fixture_ids = None
        if any(counts[1] for counts in runs.values()):
            require(args.fixture_manifest is not None, "Selected run requires --fixture-manifest")
            require(identity.get("fixture_manifest_sha256") == sha256_file(args.fixture_manifest), "Fixture manifest hash mismatch")
            fixture_ids = validate_fixture_manifest(json.loads(args.fixture_manifest.read_text()), identity)
        with tempfile.TemporaryDirectory(prefix="picker-diagnostics-") as temporary:
            directory = Path(temporary) / "diagnostics"
            export = export_diagnostics(args.xcresult, directory)
            logs = read_diagnostics(directory)
            retain_diagnostics(logs, args.diagnostics_output, export, identity)
            result = validate_logs(logs, runs, fixture_identifiers=fixture_ids)
            result.update({"identity": identity, "export": export, "log_sha256": {path: hashlib.sha256(value.encode()).hexdigest() for path, value in logs.items()}})
        require(identity["xcresult_sha256"] == bundle_digest(args.xcresult), "xcresult changed during validation")
        require(identity["app_binary_sha256"] == sha256_file(args.app_binary), "Built executable changed during validation")
        if fixture_ids is not None:
            require(identity["fixture_manifest_sha256"] == sha256_file(args.fixture_manifest), "Fixture manifest changed during validation")
    except (EvidenceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        result = {"schema_version": SCHEMA_VERSION, "status": "invalid_evidence", "budget_seconds": BUDGET_SECONDS, "error": str(exc)}
    if args.diagnostics_output.exists():
        result["retained_diagnostics"] = str(args.diagnostics_output)
        result["diagnostics_retention_complete"] = (args.diagnostics_output / "retained-manifest.json").is_file()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "receipt": str(args.output), "error": result.get("error")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
