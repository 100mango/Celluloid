# Actual macOS Photos host prerequisite in the existing Mac job

Current contract: `Celluloid.PhotosHostEntry.3`. This explicitly versioned test
qualifies real Photos UI entry and an in-process own-bundle identity observation.
The extension self-reports its PID and own on-disk executable/debug-dylib hashes;
OS-wide process uniqueness and mapped-code attestation are not claimed. It does
not reinterpret the failed v1 registry or v2 process-enumeration contracts.
Every acceptance report retains `complete_host_e2e: false`. The immutable source
baseline remains `9c9e7fc9c12df342c883e8a1e4462f796469842c`, tree
`f53aa262fb56d31cd0b2f03f3836147c26ff2858`, with individually reviewed changes.

Public run [37259889783](https://github.com/100mango/Celluloid/actions/runs/37259889783)
at `43b07f01c635dccc97593136d33ef055b4d26a2c` reached the sandboxed v1 discovery
query and received `PKDiscoverAll` unauthorized-discovery failure before Photos
launch. That failed result remains failed. V2 neither repeats nor relocates that
query and performs no forced registration, election, or permission change.

## Execution and ownership

The `native-mac-host` row uses a fresh ephemeral standard Mac VM, serialized
between `native-mac` and the native simulator matrix. It waits for Mac diagnostics
to finish, but admission depends on the same successful preflight, not the known
cross-display pixel comparison. Subsequent functional rows wait for host completion
without requiring host success. There is still at most one Celluloid Mac job
running at once. No new current run is launched by this draft.

This separation follows actual evidence from run37220588828 at source52bf7a9:
the Mac row had707.187529333 seconds left when host admission required1020.
It correctly stopped before preparation or host launch. The2x/3x producer/consumer
step had consumed about13m51, so the old same-job planning estimate was insufficient.
The failed budget receipt remains incomplete; it is not retroactively accepted.

The fresh row checks out exact `github.sha`, fetches/verifies the immutable9c
source base with the existing bounded read-only command, verifies combined source,
and materializes/verifies exact-source native icons. It rebuilds the external UI
bundle and ordinary sandbox app locally with600-second and300-second owned-command
bounds. The previously reviewed minimal ephemeral ad-hoc signature and app/extension
entitlement checks are copied unchanged. No binary, Photos library, or user data
is transferred from another job. Only this one app copy is launched through its normal application entry.

The job retains its45-minute limit and conservative41-minute first-step clock.
Before preparation and immediately before the host process it still requires
12 minutes for host execution plus5 minutes for evidence/upload. The host step
retains14 minutes and actual process720 seconds. Insufficient/invalid time is an
explicit incomplete stop. Owned xcodebuild timeout cleanup uses the existing
bounded helper; no unrelated process is terminated. This prerequisite does not
claim completed Photos UI teardown or full lifecycle cleanup. The VM is ephemeral.

Host entry does not require a successful layer-pixel comparison. Exact source,
rebuilt product signatures and child identity are prerequisites. Layered edits
remain protected; this phase never saves, cancels a modified photo, or invokes Revert.

## Exact synthetic asset selection

The ordinary system-picker test previously left one imported synthetic image in
Photos' `Recently Saved – 1 Photo` view. Its AX element is timestamp-labeled,
not filename-labeled. Importing another image and assuming one result is invalid.

The integrated test therefore has two explicit paths:

1. When ordinary Photos UI ran successfully, its seed receipt must bind the
   current source SHA, exact app executable hash, generated PNG hash/bytes and
   1200x800 dimensions. It must prove the observed empty `Welcome to Photos`
   state and zero assets before import, exactly one asset afterward, and the
   existing strict sampled-pixel comparison after actual system-picker import.
   The host probe reuses only that sole asset and checks its exact observed AX
   label and count again. It does not import another image.
2. When the ordinary seed case did not run, the host probe must itself observe
   `Welcome to Photos` and zero assets before importing its generated fixture.

An executed seed case without exactly one successful result and matching receipt
stops before host interaction. Unknown populated library state stops before
import. There is no deletion, library reset, guessed row, or settings change.

The reused ordinary fixture is the existing solid-blue 1200x800 image. The
fresh-host route retains the original asymmetric four-color 1200x800 fixture.
They have separate identity/hash receipts. This prerequisite checks host entry,
not rendition equality; no four-color pixel expectation is applied to the reused
solid image. Full lifecycle qualification will need an explicitly bound target
and independent resource/pixel expectations for that target.

## Unchanged safety and acceptance requirements

The installed app/extension identities, strict signatures, minimal entitlements,
bundle inventories, and independently bound own-bundle identity checks remain mandatory.
V3 observes the real Photos menu and editor instead of querying PluginKit:

1. Verify the fixed system Photos bundle/executable and retain its PID. Select
   only the sole owned synthetic asset with its exact observed label and hash.
2. Require one exact `Celluloid` menu item that is enabled and hittable. Require
   zero `Celluloid photo editor` elements before clicking that exact menu item.
3. Require one editor containing exactly one `Edited photo preview`, one enabled
   `photos-extension.filter`, no placeholder, no preparing indicator, no read-only
   state and no error. Initial absence/loading may wait up to30 seconds before the
   self-observation; any observed ambiguous controls, read-only or error state is
   latched as failure instead of being forgotten when the UI later changes. Each
   readiness poll also rejects a changed or ambiguous Photos identity.
4. Observe the DEBUG-only `photos-extension.self-identity` AX leaf twice inside
   that exact editor. A first missing value may wait up to10 seconds; duplicate,
   malformed or contradictory observations latch failure. The second read is
   immediate and cannot recover a disappeared identity. Both raw UTF-8 values
   must match, including PID, generation and the exact independently hashed
   installed main executable and debug dylib. Reobserve the ready editor without
   a recovery wait, with the same verified Photos PID on both sides.

This associates a self-observation with the ready Photos UI. It is not OS-wide
process uniqueness, audit-token view attribution, mapped-page attestation, registry
inventory, or proof of exact `PHContentEditingInput` resource bytes. The extension
gets no expected path/hash/source from the tester. Fresh VM/builds, no downloaded
products, the absent-to-ready transition and a new start-generation prevent the
supported workflow from replaying a prior editor. The raw identity is cleared
synchronously on start, cancel and finish; generation-checked publication rejects
late work. Two snapshots cannot detect an unobserved disappear/reappear interval.
The test invokes the actual extension and never instantiates its controller as a
substitute. Missing or ambiguous controls stop with evidence.

Unknown permission, account, legal, Gatekeeper, authentication or other system
interruptions abort before XCTest's default handler. Only the previously observed
synthetic first-use Get Started action is accepted. The current title-scoped probe opens no settings UI. No extension election, checkbox, security preference, TCC database,
Apple account or real signing key is changed.

The verifier requires one finalized, passed, unskipped exact XCTest and all
same-source product/UI-transition/self-identity/fixture-ownership receipts. It
rejects optimized Python before any action. Source verification freezes the base
files except the reviewed project membership, ordinary test receipt addition,
two explicitly SHA-pinned diagnostic-only test files, and separately reviewed
native text renderer/tests, TV picker/title/tests, and Watch/phone traversal test
files, plus the two DEBUG-only identity integration files (all individually SHA-pinned);
the full combined source contract independently binds the resulting candidate.

## Fixed evidence budget and remaining work

The existing1,000,000-byte host subset is moved to a dedicated artifact from its
new row. Mac diagnostics now receive2,000,000 bytes; whole-workflow allocation
remains19,500,000 bytes across12 serial jobs, all retained one day. The historical
52bf evidence remains unchanged. Future Mac packets retain typography, exact
consumer/source/fixture receipts and200KB raw runtime/AX tails ahead of optional
screens. Only five optional compiler tails are shortened to20KB; each truncated
prefix is explicitly listed in omissions. Runtime markers and failure assertions
are not relaxed. Any further screenshot omission remains explicit in its manifest.

The dedicated host collector retains mandatory outcome, source, product,
finalized-test, fixture, UI-transition and self-identity receipts before optional
screenshots/AX dumps. Both complete combined-source receipts are mandatory and
must agree with host source tree/workflow, candidate SHA and current contract
fingerprint. They are verified after host execution before acceptance and upload.
The1MB limit includes its manifest; there is no nested second allocation.

The collector replays complete accepted proof and verifies every hash. A JSON
acceptance flag alone is insufficient. Missing or oversized required proof fails
collection of a claimed acceptance. Diagnostic-only incomplete packets preserve
the observed failure and available source/ownership evidence. No raw xcresult,
Photos library, build product or account data is uploaded.

A passed prerequisite is followed by separately reviewed real save/reopen/cancel/
Revert, exact original/current/adjustment resource preservation, filter/layer/text/
geometry readback, localization, accessibility and lifecycle scenarios. Those
remain unexecuted by this draft, and layered saves require the strict renderer
gate and removal of the temporary protection before final qualification.

Primary references:
- [Apple extension creation and testing](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/ExtensionCreation.html)
- [Edit in Photos with extensions](https://support.apple.com/en-euro/guide/photos/pht820c5ba8a/mac)
- [See photo information in Photos](https://support.apple.com/en-euro/guide/photos/phta8b25fa42/mac)

## Sandboxed proof transport

The sandboxed XCTest can read its exact bound input context but cannot write to
an external `RUNNER_TEMP` evidence folder. Receipts therefore use the existing
XCTest stdout path. The first record validates the complete context-byte hash,
source commit, actual test-source/verifier hashes and expected product hashes
before any host UI action. Each subsequent proof record has a fixed name,
strictly ordered sequence, byte count, content hash and the same context binding.
The stdout transport is capped at 160,000 decoded bytes total; individual records
are capped at 16,000 bytes, or 120,000 for the fixture.

Only the outer runner writes the allowlisted receipt files. It waits for the
bounded xcodebuild process to finish, parses the exact testcase enclosure, and
replays all bytes before acceptance. Acceptance additionally requires exactly one
passed testcase, the successful xcodebuild terminal, bounded-process exit zero,
the finalized xcresult summary, raw own-bundle self-identity receipts, unchanged
source/product checks and the fixture/UI-transition checks. Echoed source
values or a transport-success flag alone cannot grant acceptance. Every collected
accepted packet reruns the complete transport and host proof.

The context, first payload, proof envelopes, replay report, acceptance and collected
manifest carry the v3 host-entry identity. The exact ordered stdout names are `transport.json`,
`containing-process.json`, `photos-process.json`, `fixture.json`,
`fixture-ownership.json`, `host-selection.json`, `host-editor-before-process.json`,
`extension-self-identity.json`, `host-editor-after-process.json`, `prerequisite.json`,
`lifecycle.json`, `outcome.json`. A v1, v2 or registry-only packet cannot qualify as v3. The collector
requires exact UI schema keys, primitive types, expected counts, labels, phases,
Photos PID/path, fixture and source identity, and independently replays these
checks from the actual transport bytes. Nonfinite JSON, duplicate keys and
contradictory timeout/success evidence reject even after payload rehashing.
A structured first blocked operation also vetoes acceptance even if a textual
failure marker is missing.

The former Python process-enumeration action now raises an unconditional retired-operation
error before any process query or helper launch. Bounded AX text and the two
fixed screenshot names use XCTest attachments. The outer exporter accepts only
known host diagnostic names from the exact host test, with Xcode27's observed
fixed stem plus iteration/UUID/type suffix (the declared extension is removed
before that suffix is added), direct owned export files, no symlinks, correct file types
and the existing size caps. Transport completion is published only after this
export is finished and validated. Missing, malformed, duplicate, out-of-order,
truncated, over-budget or wrong-context records remain red. On an attachment
manifest parse/matching failure, a fixed optional diagnostic may retain the
manifest hash, original bounded error and the first16 metadata items (160 characters
per field, at most16KB). It reads no metadata-reported paths and cannot grant
transport completion. Omitted metadata is explicit and the total host cap is unchanged.
The outcome is emitted before optional screenshot work; Photos screenshots are
attempted only after its identity has been verified.

This changes neither entitlements nor permissions, privacy settings, registration
preferences, production serialization, rendering goldens or the guarded Photos
save path. Portable parser tests are not an Apple runtime or host-entry pass.

## Observed attachment and menu diagnostic correction

Run [37266677778](https://github.com/100mango/Celluloid/actions/runs/37266677778),
source `2980ebcf179acf092dbd35f29886cb5c44f6204e`, launched actual Photos, imported
its owned synthetic asset and reached Edit → Extensions. It failed before
invocation because Celluloid was not uniquely selectable. The failed export
retained metadata proving the exact Xcode27 spelling, for example
`celluloid-host-diagnostic-last-observed_0_<UUID>.jpg`. The receiver reconstructs
only the fixed `last-observed.jpg` name from that stem and typed suffix. It does
not accept the earlier doubled-extension assumption as a second format. Unknown
stems/types, duplicate selected names, other tests, unsafe paths and existing
caps still reject. That historical run remains failed.

Before optional screenshots, the test now captures the Celluloid menu count once
and, only for one element, its enabled/hittable values. The bounded stdout outcome
retains `absent`, `ambiguous`, `disabled`, `not-hittable` or `selectable`. Properties
not observed for absent/ambiguous matches are null, never invented false values.
No new host UI action is added. A claimed acceptance must agree with the successful
selection receipt; a contradictory outcome cannot be discarded. Failure wording
no longer claims that Manage was captured when that branch was not executed.

## Exact observed Photos menu identity

Run [37270219320](https://github.com/100mango/Celluloid/actions/runs/37270219320)
retained the opened Extensions menu. Celluloid was visibly present; AX recorded a
direct `MenuItem` with `title: Celluloid` and `identifier: editWithPlugin:` beneath
the `Extensions` menu button's child menu. The old `label == Celluloid` predicate
returned zero because title and label are distinct attributes. That is a predicate
miss, not evidence of registration absence or disabled enablement.

The test now requires exactly one Extensions menu button, exactly one nonempty
opened child menu, and a direct item matching the observed title AND identifier.
It repeats those scope checks immediately before the fresh enabled/hittable
selection and click. No label-or-title fallback, global menu search, settings
opening, registration query, or toggle action is added. `HostSelection.3` and
`HostMenuObservation.2` bind the title, identifier, exact parent scope and counts.
The real editor transition, same Photos PID, self-observed own executable identity, source,
owned input and finalized test/process evidence remain mandatory.

[Apple's public XCTest attributes](https://developer.apple.com/documentation/xcuiautomation/xcuielementattributes)
include distinct title and label values and support their use in query matching.

## Bounded owned-extension crash diagnostics

Run [37274931809](https://github.com/100mango/Celluloid/actions/runs/37274931809)
at `8c42255789cd51ecb329a632389ce706d5f77e5d` selected the actual Celluloid menu
item, then the extension process crashed before the ready-editor/live-process
proof. The retained log and summary contain no established exception, termination
reason, stack or dyld cause. This failure remains failed; it does not justify an
actor, entitlement, signing or permission change.

The outer runner now records the exact built extension executable and adjacent
`.debug.dylib` SHA256/size/arm64 UUID independently before host execution. After the
existing product check, it can read only fixed-name `CelluloidMacPhotosExtension-*.ips`
files directly in the runner's `~/Library/Logs/DiagnosticReports`. Diagnostics are
outside the14-minute host step. A predecessor context step performs the existing
budget-before-prepare/source-before/prepare calls in their original order after
successful sandbox-child signature verification, then optionally binds UUIDs.
Its separate outcome gates host launch without suppressing failed-preparation
evidence collection. Crash capture runs in the evidence step after mandatory host,
source and product work. Neither diagnostic changes captured host status or host
acceptance.

Ownership requires the exact executable path, main UUID and bundle ID, together
with a capture/launch time within the actual testcase interval. The interval is
reconstructed from the exact test start/terminal duration and explicit runner
timezone, reconciled with the finalized summary and bounded xcodebuild interval.
The source/context/test/verifier/collector and current product hashes are bound.
The built debug dylib UUID is recorded even when absent from loaded images; its
absence is diagnostic data rather than a reason to discard an early loader crash.
If an owned loaded image exists, its path/UUID must agree.

Apple documents privacy substitutions and shows `/Users/USER/` in macOS reports.
Only the precise current runner username→`USER` substitution is permitted, with
every later component exact and the other ownership checks still mandatory.
Wildcard `*`, suffix-only matches, other placeholders and path normalization are
rejected. Reported image paths are never opened. Symlinks, nonregular files and
replacement during a bounded read reject.

Caps are256 scanned directory entries,16 fixed-prefix candidates,4 matching
incidents,512KiB per input/2MiB total reads,128 frames per retained trace,64 necessary
images and96KiB total projected output. All matching incidents within these limits
are retained. Overflow, duplicate incidents, malformed/nonfinite/duplicate-key
JSON, unknown identity/time and truncated structures are explicit incomplete
capture; no first/latest-incident choice or silent frame/image truncation occurs.

The fixed projection retains exception/termination, exception reason, faulting
and last-exception backtraces, their necessary image metadata and owned-image
observations, bounded report notes, and application-specific `asi` messages.
The latter allow at most8 modules,8 messages per module,128-byte module names,
4096-byte messages and16KiB aggregate, still within the96KiB total. Strings are
diagnostic data. Device/user identifiers, trial metadata, unrelated thread state,
virtual-memory dumps and unrelated process reports are not projected.

These files are optional diagnostics, reserved after required host proof and
before optional screenshots inside the unchanged1MB artifact/one-day retention.
Malformed or unbound diagnostics are explicitly omitted and cannot alter host
acceptance. No raw IPS, xcresult, library or product is uploaded. Actual Photos
invocation, editor transition, self-observed executable identity and source/input checks
remain mandatory; complete host lifecycle qualification remains open.

Official format references:
- [IPS JSON fields](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report)
- [Crash fields and macOS privacy placeholder example](https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report?changes=_3)

### Optional diagnostic time and pre-read admission

The original41-minute monotonic job clock is shared with the mandatory host
budget; its exact hash must still match the host-budget receipt. Immediately
before an optional child starts, its limit is clipped to at most20 seconds of
actual remaining time after reserving1020 seconds (unchanged720 host +300 evidence)
before host launch, or300 evidence seconds after host. Another12 seconds remain
reserved for owned process/pipe cleanup and receipt finalization. Less than one available second produces a bounded incomplete diagnostic
without launching a child. The14-minute host step,720-second host command,
660-second testcase,41-minute execution clock and45-minute job cap do not increase.
No claim is made that the job reserve proves every mandatory maximum fits inside
the separate host-step cap.

The optional boundary starts one direct owned session and reads its combined
stdout/stderr nonblocking, retaining at most8KiB while reading rather than checking
an unbounded buffer afterward. The admitted absolute deadline includes spawn time
and is never renewed. Completion requires actual pipe EOF and a bounded direct-child
wait. The leader is not polled/reaped while descendants may retain its pipe, so
TERM/KILL cleanup targets the still-owned group before its PID can be reused.
Process/pipe cleanup has at most10 seconds, leaving two of the reserved12 seconds
for receipt finalization. Timeout, output-cap pressure and unconfirmed pipe/process
completion remain explicit failures. A printed END marker cannot establish this
boundary. The mandatory host path and existing run_bounded helper are unchanged.

The next capture child also requires finalized host-test/process evidence, the
prior identity child's completion and completed mandatory product/source receipts.
Unknown termination skips further diagnostic execution. Missing or insufficient
spare time cannot reduce a mandatory allowance or become host proof.

Aggregate IPS input allowance is admitted before opening/reading the next file:
`safe_read` receives at most the smaller of512KiB and the remaining2MiB allowance;
an exhausted allowance fails before the next read. Oversized next files fail at
stat before any payload bytes are read. Rejected candidates consume the same read
budget. A five-full-file adversary measures actual reads and proves they stop at
2MiB rather than reading the fifth file and checking afterward.

## Owned path mismatch observation and focused repair route

Run [37291109686](https://github.com/100mango/Celluloid/actions/runs/37291109686)
at `7868de58e41e4d0632befaec1a163d868b508a95` reached the real Photos extension
again. The owned collector completed, but its sole20,648-byte IPS candidate was
rejected as `Wrong executable path`. No stack or actual rejected path survived,
so the crash cause and the path's redaction form remain unknown.

The unchanged matcher still accepts only the exact expected path or the sole
runner-username→`USER` substitution. A bounded mismatch observation is retained
only after exact built UUID, bundle/process, incident and actual capture/launch
window checks pass. It contains observed/expected paths and a fixed comparison
reason. Malformed, nonabsolute, control-character or oversized process paths
are rejected without that observation. `Celluloid.OwnedPathMismatch.2` may also
retain a separate `Celluloid.UUIDBoundPathUnverifiedCrash.1` diagnostic: the same
bounded exception, termination, crashed-thread/last-exception frames, necessary
images and application-specific messages, with `acceptance: false` and
`executable_path_verified: false`. Exact UUIDs remain mandatory for any image
identified as the built executable or debug dylib, and each image's path-match
result stays explicit. The debug dylib need not be present. Contradictory UUIDs,
malformed data or exceeded frame/image/message limits omit this subprojection
with a bounded error; they never yield a partial truncated stack.

These incidents remain only in `rejected`, never `incidents` or `matched_count`.
Accepted and UUID-bound rejected incidents share the existing four-incident cap,
and the unchanged aggregate input/output/time/artifact caps still apply. No
reported path is opened. This diagnostic neither establishes the executable path
nor authorizes broader path matching, filesystem access or host acceptance.

The separate push-only `mac-repair.yml` route uses `codex/mac-repair` and shares
the canonical workflow's concurrency group. The canonical `apple-platforms.yml`
remains byte-identical. Three serial jobs retain all portable tests, selected Mac compile/test-bundle/
package prerequisites, all39 existing native Mac cases plus three identity guard cases, and the real Photos sequence and
source/product/cleanup/evidence guards. This diagnostic route defers the standalone `Native Mac UI launch and editing`
flow and the `External sandbox document UI and container runtime` flow, in
addition to early UIKit continuation and later simulator/UIKit/archive jobs.
The separate Photos job retains its own sandbox seed and product prerequisites.
These omitted Mac UI flows still require the canonical full run; this route is
not full Mac qualification. There is no release qualification, distribution
signing or upload.

Focused execution must match the exact repository, branch, workflow ref, source
SHA and explicit `mac-repair` scope. Source, context and collected host receipts
bind the actual selected workflow hash and a fixed `diagnostic_only: true` route.
Mismatched/missing/relabelled route metadata rejects; a focused prerequisite can
never supply full-E2E or full-release evidence. Existing45/41/14-minute host caps,
720/660-second process/test limits, one-day artifacts and per-platform byte caps
are unchanged. A later canonical full run is still required for complete testing.

The focused preflight uses only the existing `mac-build-for-testing`,
`mac-ui-build-for-testing`, and `mac-release-package` operations. The fixed
`--mac-repair` selection requires the exact focused branch/workflow/source route;
all selected build arguments, compiled-bundle verification, package validation
and time/byte caps remain unchanged. Simulator inventory, TV input capability
and non-Mac build/package operations are deferred. Its receipt enumerates exactly
those three selected prerequisites, reports their separate pass state, and always
keeps `all_prerequisites_passed: false` and `long_matrix_allowed: false`. The
canonical no-option fourteen-stage gate and canonical workflow remain unchanged.

## Public framework-link hypothesis and bounded declared-dependency observation

The UUID-bound/path-unverified diagnostic from run37334004001 records a
SIGTRAP/EXC_BREAKPOINT in ExtensionFoundation's extension-context-class selection.
Both exact owned main/debug UUIDs were loaded. There is no retained assertion
message or evidence that an entitlement, actor isolation or missing debug dylib
caused it. Apple's official Sample Photo Editing Extension explicitly links
PhotosUI.framework and Photos.framework. The production extension now mirrors
those two public SDKROOT framework links; other targets are unchanged. The
linkage hypothesis remains unproven and this may be a runtime no-op.

After the optional identity child has fully completed, the same outer preparation
may inspect only its exact context-derived main/debug files with `/usr/bin/otool
-L`. Current hashes must equal the already UUID-bound same-job identity before
and after the observation. Only PhotosUI/Photos/AppKit declared-dependency
presence, output hashes and bounded process results are retained. This is not
proof that dyld loaded a framework or that context-class resolution succeeded.

The existing20-second absolute preparation deadline is not renewed. Each tool
uses at most two seconds plus one second for confirmed cleanup, all within that
original deadline, and the existing8KiB streaming cap. Insufficient time skips
new tools. A missing fixed otool executable or expiry at the runner’s exact
pre-spawn deadline guard records a not-started observation and preserves the
usable identity; no retry or alternate command is attempted. Other exceptions
remain blocking. Unconfirmed process/pipe completion stops additional observations and
marks preparation unfinalized, preventing later crash capture. No new process
runner, host UI action, private context override, entitlement or permission is
introduced. The same host invocation and acceptance gates still decide success.

## Host-entry v3: own-process observation after the v2 sandbox denial

Run [37342181970](https://github.com/100mango/Celluloid/actions/runs/37342181970)
at `e1ffaa6c3e9c24610dfed3a6c6fc7d7ee63b8da1` passed all39 native cases and
the unchanged independent pixel oracle (maximum difference0), and reached one
ready editor in actual Photos. Its sandboxed XCTest runner then attempted
`/usr/bin/env python3 Scripts/mac_photos_host_gate.py processes` and received
`xcrun: error: cannot be used within an App Sandbox.` The run and v2 contract
remain failed. V3 does not retry that command, substitute interpreters, move the
query to another process, enumerate processes, or change entitlements/permissions.

After real `startContentEditing`, a DEBUG-only background task reads its own
`Bundle.main`, `ProcessInfo.processIdentifier`, and fixed own-bundle main/debug
files through public descriptor-relative no-follow reads. Each file is regular,
single-link, positive and at most32MiB; chunks are at most64KiB. Descriptor and
directory-entry identity/size/timestamps are rechecked after both hashes. The
10-second monotonic cancellation/deadline is cooperative: an OS file call is not
forcibly interruptible. Failures leave the identity absent without blocking edits.
The live AX getter exposes it only while attached, visible, started and fully ready.

`Celluloid.ExtensionSelfIdentity.1` has exactly12 fields: schema, marker,
observation_kind, bundle_identifier, pid, bundle_path, executable_path,
executable_sha256, debug_dylib_path, debug_dylib_sha256, generation and
content_editing_started. Each raw value is at most8192 UTF-8 bytes. The enclosing
`Celluloid.HostSelfIdentity.1` receipt contains two raw values, byte counts and
hashes plus the existing source/Photos/fixture/UI binding; it still must fit the
unchanged16000-byte individual/160000-byte aggregate proof caps. The outer
parser recomputes both raw hashes, rejects duplicate/unknown/missing keys,
nonfinite JSON, wrong primitive types, paths/hashes/PID/generation, changed
observations and legacy contracts. Acceptance waits for the exact completed test,
unchanged actual source/product receipts and strict transport replay.

Release source projection removes the entire identity helper and integrations.
The existing actual Release binary guard rejects both prior renderer hooks and
identity marker/schema/classes/AX identifier in the fixed extension main binary
and fixed debug dylib if one exists. No source/test pass substitutes for native
compilation, actual AX discovery or the Release binary check. Full host
save/reopen/cancel/Revert coverage and release qualification remain open.

Public API references: [Bundle](https://developer.apple.com/documentation/foundation/bundle),
[ProcessInfo](https://developer.apple.com/documentation/foundation/processinfo),
[AppKit accessibility](https://developer.apple.com/documentation/appkit/accessibility-for-appkit),
[AX participation](https://developer.apple.com/documentation/appkit/nsaccessibilityprotocol/isaccessibilityelement()).

## Bounded owned filter lifecycle continuation

Public [run37349739749](https://github.com/100mango/Celluloid/actions/runs/37349739749)
at 8470141a passed all 42 required Mac cases, the unchanged native pixel oracle
(maximum 0), actual Release hook absence, and real HostEntry.3 with two identical
1,013-byte own-process observations. This historical accepted entry proof remains
valid for that source. It did not exercise Save/reopen/Cancel/Revert.

The next source candidate appends `Celluloid.PhotosFilterLifecycle.1` to that
same real host testcase. It retains the original source PNG before import, uses
only the fresh-job sole manufactured asset, and keeps the v3 entry guards.
Required ordered phases are source-retained, fade-ready, saved-export,
reopened-fade, cancelled-export, reverted-export, unmodified-original and
reopened-original. All phases and all actual image bytes must verify before the
new candidate can pass. A failed appended case is never accepted from its earlier
entry marker. No prior successful run is relabelled as having run these phases.

The independent reference uses literal CIPhotoEffectInstant, full-resolution
sRGB composition and ImageIO JPEG quality 0.95 encode/decode, without a production
renderer/filter/codec helper. JPEG loss is included in the reference before the
unchanged 2-level maximum comparison; no fitted offsets, masks or new broad
tolerance are used. The earlier independent native text oracle is unchanged.

After selecting Fade, the test acts only on newly observed unique enabled and
hittable owned Photos controls: Save Changes, Done, normal File/Export, Edit,
Extensions/Celluloid, Cancel without a new edit, and Image/Revert to Original.
Unknown dialogs/confirmations stop with bounded observations; no broad confirmation,
privacy change, registration query or helper process is added. Export uses normal
Photos UI to a freshly created XCTest-owned directory, four fixed per-phase
paths and one fixed filename. An access denial stops without changing locations.
Existing original app/source/product/Photos PID and owned asset checks are repeated.
Both reopened editors require a new editing generation and actual two-read
self-identity binding; restored picker values must be Fade and then Original.

Actual Photos exports are essential: a canHandle=true editing input may be the
original plus an adjustment recipe, so the extension's re-rendered preview does
not prove the stored raster. Saved, cancelled and reverted attachments contain
the exact exported PNG bytes. Cancel without a new edit must preserve exact
canonical RGBA; Revert must restore original canonical RGBA; Export Unmodified
Original must return exact retained source bytes. Dirty-session Cancel rollback
is explicitly `dirty_cancel_tested: false`. No Photos database, private resource
directory or separate PhotoKit authorization is read or requested.

Five fixed required PNGs are `lifecycle-source.png`, `lifecycle-expected-save.png`,
`lifecycle-saved.png`, `lifecycle-cancelled.png` and `lifecycle-reverted.png`. Each
is at most 128 KiB and together at most 640 KiB, inside the unchanged 1 MB host artifact.
They are exact-test XCTest attachments under a separate fixed prefix; no arbitrary
reported path or exporter suffix is admitted. Mandatory pixels/receipts precede
optional screenshots and AX. The lifecycle JSON is at most 16,000 bytes and all
stdout proof remains at most 16,0000 bytes. Raw local export reads are capped at
16 MiB each/64 MiB aggregate, admitted before reading, with nonblocking no-follow
descriptor-relative opens,64 KiB chunks and file/parent metadata rechecks.

PNG replay validates exact 1200 × 800, 8-bit RGB/RGBA, opaque alpha, orientation,
no interlace/animation, chunk CRC/order, bounded decompression and complete image
span. sRGB intent 0 is supported directly; an iCCP profile must match the entire
independently observed public CoreGraphics sRGB profile byte-count and SHA256.
Actual ICC bytes remain in the required PNG and are bounded-inflated before
ImageIO or outer comparison. This is exact byte-equivalence evidence, not generic
ICC/color-profile equivalence. Unknown profiles are a separately described profile
failure, never hidden by loosening the pixel oracle. The compact raw_exports table
references the fixed retained PNG, path, bytes and SHA instead of duplicating
image metadata; no required proof or identity observation is dropped.

All eight phase records have strict fields, indices, monotonic elapsed times and
ordered control occurrences. Identical control tuples may share catalog storage
only after fresh observation; duplicate catalog rows, unused rows, missing or
extra actions, wrong ownership/controls, stale generations, changed actual PNGs
and contradictory reported metrics fail independent replay. Actual hashes and
pixels are recomputed from retained bytes, not accepted from a boolean.

One 600-second shared monotonic test deadline fences every action and bounds every
wait beneath the unchanged 660-second testcase/720-second process,14-minute host
step and41-minute job clocks. No cap, permission or workflow change is included.
Theoretical mandatory pixels 640 KiB plus measured ordinary proof below 200 KiB and
50 KiB manifest reserve fit the existing 1 MB; actual admission still checks every
byte and fails rather than omitting proof.

Even if this one static sRGB filter lifecycle passes, `complete_host_e2e` stays
false: dirty rollback, layered editing/legacy UIKit interoperability, arbitrary
resources/orientations/color spaces and release qualification are not inferred.
Sticker/Bubble controls and layered Photos output remain guarded. Native execution
of this appended lifecycle remains pending until its exact source is admitted.

Public workflow references: [Apple extension editing](https://support.apple.com/en-ie/102259),
[Photos PNG/original export](https://support.apple.com/en-au/guide/photos/-pht6e157c5f/mac),
[Revert to Original](https://support.apple.com/guide/photos/editing-basics-pht304c2ace6/mac),
[original input and adjustment semantics](https://developer.apple.com/documentation/photos/phcontenteditinginputrequestoptions/canhandleadjustmentdata).
The bounded inflater uses Apple's [system zlib module](https://github.com/apple-oss-distributions/zlib/blob/main/zlib.modulemap)
and public uncompress2 input-consumption/output-size contract; no new package is installed.
