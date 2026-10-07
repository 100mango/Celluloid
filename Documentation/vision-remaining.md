# Vision editing with a synthetic document input

Exact parent: e20c7ce5fde3300ca4ef13480bed3de19718874a, tree
edee686354ad23fa928c46b6751467fe9ce5b97d, codex/vision-edit-final.
This is a local candidate until separate exact-tree admission. No automatic
rerun follows from this document.

## Current parent: unknown native phase, failed evidence packing

Run37643046041/e20c7ce remains FAILED. Its proof process exited1 at15:27:26;
the following host-only packing step timed out at its self-imposed1minute cap,
and upload was skipped by the pack-success condition. The artifact list is
empty. The retained GitHub job log cannot identify the failed native phase or
establish whether UI started. Its13002 bytes have SHA256
32aeca42e3921898eabbe81fbb6d0e7e178b4401171cb020dd9afe3e9f5df3c6.
Scheduler/log delays were observed, but their root cause is unknown.

This successor changes observability only. Every admitted command phase emits
start/end records with flush=True, its return code, timeout/error, capture
completeness and device barrier. Only failures append the last32KiB of captured
command/UI bytes. Job failures and final outcomes are flushed too. These actual
stdout records survive artifact-packing failure and do not turn a partial test
marker into a successful invocation.

The host-only pack step has2minutes of scheduling allowance inside the same
60minute job, with original work/cleanup/pack/finalization clocks unchanged.
Upload and final verification run in the always path independently of pack
success. Upload names a fixed set of9 bounded phase logs, the bounded report,
uncertainty/icon receipts and optional manifest. Producer caps sum to7751450
bytes, below the original8MB total. No directory glob can add arbitrary files.
The manifest, when available, describes exactly that uploaded set. Local tests
actually time out a host pack process, verify preserved input files and the
independent upload condition, and observe flushed stdout before a real host
child exits. These are local driver tests, not a new native execution.

All Swift, fixtures, single editing assertions, native timeouts and simulator
barrier behavior are unchanged. No new native run is authorized by this patch.

## Earlier failed cohorts and reusable components

Run37637767590 remains FAILED. Its Debug build-for-testing passed69.870s,
icon prerequisites passed and bootstatus completed206.310s. The actual native
fixture writer/readback test passed0.166s at14:44:39 UTC and emitted its own
Documents path, image/recipe sizes and hashes. The xcodebuild process did not
finalize within its original360s budget. Capture recorded duration-limit with
owned process cleanup confirmed; the device-uncertainty barrier then prevented
all container queries, UI and simulator cleanup commands. The native fixture
action passed, while that invocation did not qualify. Editing never started.
Artifact11490979202 ZIP SHA256:
dacfe58716acceb6d1cce8c45c4581a8d0de69c8b50f905906e4353568736970.
Its19 manifest members were retained. No product editing failure was observed.

The prior2cf9160fa043f7ef0f89e42d022240a8b9f77322 / run37612385100 remains
FAILED, but its shared field/Undo/reopen hosted case and Chinese ordinary/
largest-text privacy UI actually passed. The editing case stopped at Recents,
before opening its file. AX showed the exact On My Apple Vision Pro location;
the truncated prefix did not show a file-item role or prove container loss.
The parent added the exact-name, unique-operable-item route and complete
bounded browser evidence, and compiled it successfully. Its behavior is still
unproven because the parent never reached UI.
Original artifact11479451487 ZIP SHA256:
bdd05d117f26f5beedf27f61050fdffd3f91db2d872829d6e900803dabe258c3.

The earlierdb4d719abdf11504e99e211ffc27d7555883acb3 / run37608605492
remains FAILED due to the former lowercased destination. Its unsigned archive,
11 icon inputs and all13 package checks actually passed. Its1.1/build2 arm64
visionOS package is not a signed/exported/uploaded binary.
Artifact11477245993 ZIP SHA256:
126ecef09c9fac1f8d0972071cceb82513c0f2fcba7a113a4da1fbd6fc8aa46d.
These historical identities remain separate in each successor report.

## Remove the unnecessary hosted-XCTest prerequisite

The runner now authors a small, non-personal INPUT rather than asking a second
XCTest invocation to create it. A sorted281-byte recipe is reconstructed from
the actual NativeDocument/EditRecipe encoding. Its source UUID and every byte
produce exactly the native writer's observed SHA256:
3fc3d7275c3e1e802dccb8daa63e688944b70c00a4d636c93d39f32f9b755b6e.
It has one120x80 source, Original filter and no overlay. The matching source
file is a Python-generated solid120x80 RGBA PNG with ordinary PNG chunks,
checksums and deflate. This PNG is synthetic test input, not native-rendered
output. Local tests independently inspect all chunks, CRCs and decompressed
pixels. Neither input contains the final edited text.

After the fresh Debug build and owned simulator boot, the driver checks the
built app's bundle/executable/platform, records its executable hash and installs
that exact CelluloidVision.app. Bounded simctl get_app_container returns only
Mango.Celluloid data on the one created device. Its UUID path must be inside that
owned device's data directory. The driver creates only the fixed, absent
Documents/VisionRemaining.celluloid package; links and existing package names
fail closed. It never reads or overwrites another app's data or an existing file.

The same two-member package hashes, initial empty overlays and120x80 dimensions
are recorded before UI. After a known completed UI invocation, the existing
container observation verifies continuity, preserves the original image hash
and reads the actual app-written recipe. Success requires "Vision 世界" and the
original120x80 dimensions. Python never supplies that final recipe. The initial
recipe's real native hash is an input-format check, not a claimed current
native-writer result. The historical native writer is not rerun.

## One unchanged, real editing UI test

Only testSeededDocumentSequentialTextUndoRedoAndRelaunch is selected. Its Swift
source is byte-identical to the parent. It uses the formal document browser,
the observed Recents-to-On My Apple Vision Pro route when needed, an exact
Celluloid folder if shown, and the unique operable exact seed filename. Cell/
button role is resolved by the runtime query, not assumed from missing AX.

The real assertions stay intact: bubble insertion and palette dismissal,
exactly one field tap, consecutive A/B without refocusing, actual Select All
and Unicode typing, Undo/Redo, termination/relaunch and named-document reopen.
Actual field values and dimensions must pass, followed by physical disk readback.
No final-text fixture or scripted focus substitutes for editing.

Only four paths change: this document, driver, its local tests and workflow
retention conditions/paths. All Swift tests, production, resources, project and mature
capture/retention helpers remain byte-identical. Release archive, passed
functional hosted tests, Chinese privacy, Files-import/PNG-save chains and the
fixture hosted selector are not selected again.

## Same bounds and honest failure retention

One push-only codex/vision-edit-final cohort on standard xcode-27; no matrix,
dispatch or retry. Icon materialization/verification remain build hard
dependencies. XCTest alone launches the app for UI. No redundant simctl launch,
ps, screenshot or focus preflight is introduced. Install uses the existing
repository staging precedent's300s bound and the existing owned container
observations use180s. The UI budget remains900s. No old limit is enlarged.

Original pre-checkout source/workflow/run/attempt1 clock remains:60minute outer
job, work3000s, cleanup3150s, pack3200s and finalization3360s. Every command
checks real remaining wall time and reserves20s. Unknown exit, timeout, output
cap or signal sets the durable barrier before any further device command,
including a container observation or cleanup. A known UI failure keeps its
original verdict if a later observation also fails.

The mature16MiB capture and512KiB labeled prefix/tail retention are unchanged.
Observed XCTest terminals remain distinct from invocation qualification. The
always-run evidence pack reads host files only. Original failed logs remain
available, with8MB total/2MB per-file artifact caps and1day retention. Raw
xcresults, archives and screenshots are not uploaded.

Local checks cannot establish UI success. This change removes an unnecessary
native setup/teardown dependency; it does not claim to repair Xcode's finalizing
behavior. The one real editing case still needs its own admitted execution.
