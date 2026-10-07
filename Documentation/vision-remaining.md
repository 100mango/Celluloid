# Vision editing with a synthetic document input

## Local-only model and browser-reopen candidate after abe9fc5

Exact candidate parent: abe9fc5560b230edc93b0312ef78b26b3d3dab55, tree
01b378b2c0c27191774ddb7619fb4d4091bca407, ref codex/vision-edit-final.
Run37658179493 remains FAILED. Artifact11501200900 ZIP SHA256:
4b3bcba40b249c09b17dd077ad763d46c29f4c63532f2082e9b65b4eca61f615.
All11 manifest members verify. Actual Files opening, AHello→ABHello,
multilingual replacement and UI Undo/Redo assertions passed. After force
termination/relaunch, the expected layer was absent; independently read recipe
text was ABHello, not Vision 世界. Original image bytes and120x80 remained intact.

Those text assertions observed TextEditor's local draft, not its independent
recipe-backed layer label. Vision uses draft.onChange to commit live, not a
blur-only design. Evidence does not distinguish missing model commit, Undo
routing, autosave latency, or termination before write completion. Documents
synthesis was t=438.43s, idle returned440.79s, and terminate started443.44s.
No normal-close or save-completion barrier was observed before that termination.
This is not established ordinary-close data loss.

This candidate changes no product Swift or shared Mac/Vision Undo implementation.
Its only selected case is testSeededDocumentSequentialTextUndoRedoAndBrowserReopen.
It captures one layer UUID and checks the recipe-backed label after initial,
sequential, replacement, Undo, Redo and browser-reopen stages. Undo uses the
observed field value rather than assuming one framework undo grouping. Empty
Undo is explicitly unobservable through the fallback label and stops with that
accurate diagnostic, not a false model-divergence assertion.

After the existing Documents action, one bounded full AX snapshot retains the
actual window hierarchy. Editor exposure and No Document existence are only
observations. The latter appeared in a non-main window in old evidence and is
NOT a required UI state or a close/save proof. No new normal-close behavior is
invented. The test reselects the same file via the already observed exact Files
Cell route and verifies dimensions, layer identity and full text. That UI
reselection may use framework caching; it is not labeled a close/save-completion
receipt. The unchanged independent runner disk gate still requires exact final
Vision 世界 plus original source contents. That disk read occurs after normal UI
reselection checks and test teardown; the teardown still terminates the app.
There is no forced-restart UI leg, fixed sleep, manual save, direct app access to
SwiftUI-managed file URLs, synthetic final-text fixture, or relaxed disk gate.

The previous forced-restart failure remains preserved. Browser reselection,
actual persisted disk contents and genuine normal-close semantics are distinct
claims; this candidate must not be marketed as proof of all three by a green UI
marker alone. If model checkpoints fail, no reopen is attempted and that earlier
boundary becomes the concrete next fix. Shared framework/custom Undo ownership
is a candidate cause only, not proved by the previous hosted variable-only tests.
Sources: https://developer.apple.com/documentation/swiftui/filedocumentconfiguration/document
and https://developer.apple.com/documentation/SwiftUI/DocumentGroup .

No native execution/publication follows automatically. Apple compilation and
runtime remain unverified until one separately admitted exact-tree cohort.

## Previous frozen cohort

Exact parent: 59d1d38f1519c6a8a1395ae11156cdade0c9f01f, tree
95d15a28cb487611a6a13b9b2005259a29011af8, codex/vision-edit-final.
This is a local candidate until separate exact-tree admission. No automatic
rerun follows from this document.

## Current parent: exact file Cell now observed, contents preserved

Run37654222192/59d1d38 remains FAILED. The direct "Celluloid, Container" folder
query actually passed and the real folder was tapped. The remaining generic
20s document predicate then expired while doing serial queries. Its subsequent
query found the operable file, but the earlier wait result was already false.
Full AX identifies exactly one Cell with identifier "VisionRemaining, celluloid"
and descendant StaticText "VisionRemaining". Its display label also contains a
variable time and548-byte size, which must not be hard-coded into a selector.
The editor was not opened and no editing assertion executed. The case failed
285.931s; xcodebuild returned65 normally. Cleanup and pack/upload succeeded.
Artifact11498233960,11 manifest members, ZIP SHA256:
b320d6a07ed0797f208c30b40017960bc36549c9546d5800812eba1dd5312d4f.

The owned container changed1915D6DB-ED7A-4E95-9B38-2EBAD6750BDC to
8A15F278-77AF-4CDF-AEC2-14154F80BC5A. Actual reads in the new container verified
the same fixed package,267-byte original image and281-byte recipe hashes, zero
overlays and120x80 dimensions. Fixture preservation across that relocation is
now demonstrated; it is no longer an unobserved assumption.

This successor only replaces the document's broad matcher with the observed
exact Cell identifier, requires one match and its exact static title, and checks
operability. The same20s existence bound remains. Generic cell/button enumeration
and the block predicate are removed from this path. All actual editing, Undo,
relaunch, content verification, workflow and native budgets remain unchanged.

## Earlier folder route and changed container identity

Run37648299628/45bad07 remains FAILED. Debug82.877s, bootstatus192.095s,
install215.203s and both owned-container queries completed. The one UI case
actually ran and failed357.324s before bubble insertion/editing. The20s block
predicate consumed its opportunity in serial broad queries. Retained full AX
then showed the exact Cell identifier "Celluloid, Container", label "Celluloid,
1 item" and descendant title "Celluloid". The browser had selected On My Apple
Vision Pro. No file-item role was established because the app folder was not
opened. Artifact11495359210,11 manifest members, ZIP SHA256:
c73886fa81b1739974ba60bc8e4ff5187bb1f74ef357d1412715bef042aef58a.
There was no uncertain process; shutdown/delete and pack/upload succeeded.

The fixed-device/fixed-bundle lookup returned data UUID C021EF16-2FA6-412D-
8040-19A1F30EF1CA before UI, then5F4DF0C5-5F2A-4E09-BC2E-CC54286A6D3D.
The old equality guard refused before reading the new location's package.
Consequently this evidence does not prove the seed was lost or preserved there.

The prior successor made two targeted corrections. The browser always navigates
through the observed local root and exact unique "Celluloid, Container" Cell,
checking its displayed label/title and operability. It replaces the broad folder
probe with a direct20s existence query; failure AX is retained. The actual file now uses its subsequently observed exact Cell identifier and
requires one operable match plus its exact title.
All typing, single-tap A/B, Unicode, Undo/Redo and real restart assertions remain.

After the completed UI invocation, the same owned-device/bundle query remains
the sole authority for the current container. A changed UUID is recorded as
same_container=false, not silently relabeled or treated as a product failure.
No alternative directories are searched. The fixed package must actually exist,
be non-linked with exactly its two expected children, retain the original image
hash/size, and contain a valid recipe referring to that same source and120x80
geometry. Final success still needs actual "Vision 世界" text. Missing, changed,
linked or foreign data fails. Container change alone never establishes seed
continuity: fixture_contents_verified is recorded only after all content reads.

## Earlier observability gap, preserved as failed

Run37643046041/e20c7ce remains FAILED. Its proof process exited1 at15:27:26;
the following host-only packing step timed out at its self-imposed1minute cap,
and upload was skipped by the pack-success condition. The artifact list is
empty. The retained GitHub job log cannot identify the failed native phase or
establish whether UI started. Its13002 bytes have SHA256
32aeca42e3921898eabbe81fbb6d0e7e178b4401171cb020dd9afe3e9f5df3c6.
Scheduler/log delays were observed, but their root cause is unknown.

The prior successor changed observability only. Every admitted command phase emits
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

That observability change preserved all Swift, fixtures, editing assertions,
native timeouts and simulator barriers; those protections remain here. No new native run is authorized by this patch.

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

Only testSeededDocumentSequentialTextUndoRedoAndRelaunch is selected. Its actual
editing/relaunch assertions are byte-identical; only the browser routing helper
changes. It uses the formal document browser,
the observed Recents-to-On My Apple Vision Pro route when needed, an exact
Celluloid folder if shown, and the unique operable exact seed filename. Cell/
button role is resolved by the runtime query, not assumed from missing AX.

The real assertions stay intact: bubble insertion and palette dismissal,
exactly one field tap, consecutive A/B without refocusing, actual Select All
and Unicode typing, Undo/Redo, termination/relaunch and named-document reopen.
Actual field values and dimensions must pass, followed by physical disk readback.
No final-text fixture or scripted focus substitutes for editing.

Only four paths change: this document, driver, its local tests and the Vision
UI browser helper. Production, other Swift tests, resources, project, workflow
and mature capture/retention helpers remain byte-identical. Release archive, passed
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
