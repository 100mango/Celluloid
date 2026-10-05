# Actual macOS Photos host prerequisite in the existing Mac job

Current contract: `Celluloid.PhotosHostEntry.2`. This explicitly versioned test
qualifies real Photos UI entry and a contemporaneous exact executable observation.
It retires registry inventory claims; it does not reinterpret a failed v1 probe.
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
bundle inventories, and live extension PID/executable hash checks remain mandatory.
V2 observes the real Photos menu and editor instead of querying PluginKit:

1. Verify the fixed system Photos bundle/executable and retain its PID. Select
   only the sole owned synthetic asset with its exact observed label and hash.
2. Require one exact `Celluloid` menu item that is enabled and hittable. Require
   zero `Celluloid photo editor` elements before clicking that exact menu item.
3. Require one editor containing exactly one `Edited photo preview`, one enabled
   `photos-extension.filter`, no placeholder, no preparing indicator, no read-only
   state and no error. Initial absence/loading may wait up to30 seconds before the
   process probe; any observed ambiguous controls, read-only or error state is
   latched as failure instead of being forgotten when the UI later changes. Each
   readiness poll also rejects a changed or ambiguous Photos identity.
4. Observe the mandatory live extension PID, canonical executable and actual hash
   with the existing read-only child. Immediately observe the ready editor again,
   without a recovery wait, and reverify the same Photos PID/executable on both
   sides of the child observation. Missing/ambiguous/replaced/loading state rejects.

This is an observational association of UI and executable, not an OS audit-token
attribution of the view, exhaustive global registry inventory, or proof of exact
`PHContentEditingInput` resource bytes. The two ready snapshots do not detect an
unobserved disappear/reappear interval during the process helper. The Photos UI
test invokes the actual
extension; it never instantiates its controller as a substitute. Missing or
ambiguous controls stop with AX evidence.

Unknown permission, account, legal, Gatekeeper, authentication or other system
interruptions abort before XCTest's default handler. Only the previously observed
synthetic first-use Get Started action is accepted. The current title-scoped probe opens no settings UI. No extension election, checkbox, security preference, TCC database,
Apple account or real signing key is changed.

The verifier requires one finalized, passed, unskipped exact XCTest and all
same-source product/UI-transition/live-process/fixture-ownership receipts. It
rejects optimized Python before any action. Source verification freezes the base
files except the reviewed project membership, ordinary test receipt addition,
two explicitly SHA-pinned diagnostic-only test files, and separately reviewed
native text renderer/tests, TV picker/title/tests, and Watch/phone traversal test
files (six individually SHA-pinned candidate files);
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
finalized-test, fixture, UI-transition and live-process receipts before optional
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
the finalized xcresult summary, actual live-process/executable receipts, unchanged
source/product checks and the fixture/UI-transition checks. Echoed source
values or a transport-success flag alone cannot grant acceptance. Every collected
accepted packet reruns the complete transport and host proof.

The context, first payload, proof envelopes, replay report, acceptance and collected
manifest carry the v2 identity. The exact ordered stdout names are `transport.json`,
`containing-process.json`, `photos-process.json`, `fixture.json`,
`fixture-ownership.json`, `host-selection.json`, `host-editor-before-process.json`,
`extension-process.json`, `host-editor-after-process.json`, `prerequisite.json`,
`outcome.json`. A v1 or registry-only packet cannot qualify as v2. The collector
requires exact UI schema keys, primitive types, expected counts, labels, phases,
Photos PID/path, fixture and source identity, and independently replays these
checks from the actual transport bytes. Nonfinite JSON, duplicate keys and
contradictory timeout/success evidence reject even after payload rehashing.
A structured first blocked operation also vetoes acceptance even if a textual
failure marker is missing.

The Python live-process child is read-only and returns its JSON receipt on stdout;
it never writes the external evidence directory. Bounded AX text and the two
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
The real editor transition, same Photos PID, actual extension executable, source,
owned input and finalized test/process evidence remain mandatory.

[Apple's public XCTest attributes](https://developer.apple.com/documentation/xcuiautomation/xcuielementattributes)
include distinct title and label values and support their use in query matching.
