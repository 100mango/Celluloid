# Actual macOS Photos host prerequisite in the existing Mac job

Integration draft based on public `9c9e7fc9c12df342c883e8a1e4462f796469842c`,
tree `f53aa262fb56d31cd0b2f03f3836147c26ff2858`. Rebase the frozen source
snapshot before combining with a later source. This is host registration and
entry coverage only. Every acceptance report retains `complete_host_e2e: false`.

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
is transferred from another job. Only this one app copy is launched and registered.

The job retains its45-minute limit and conservative41-minute first-step clock.
Before preparation and immediately before the host process it still requires
12 minutes for host execution plus5 minutes for evidence/upload. The host step
retains14 minutes and actual process720 seconds. Insufficient/invalid time is an
explicit incomplete stop. Owned xcodebuild timeout cleanup uses the existing
bounded helper; no unrelated process is terminated. This prerequisite does not
claim completed Photos UI teardown or full lifecycle cleanup. The VM is ephemeral.

Host discovery does not require a successful layer-pixel comparison. Exact source,
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

The prior reviewed probe's installed app/extension identities, strict signatures,
minimal entitlements, bundle inventories, unique exact PluginKit path, real Photos
editor controls, and live extension PID/executable hash checks remain mandatory.
The Photos UI test invokes the actual extension; it never instantiates its
controller as a substitute. Missing or ambiguous controls stop with AX evidence.

Unknown permission, account, legal, Gatekeeper, authentication or other system
interruptions abort before XCTest's default handler. Only the previously observed
synthetic first-use Get Started action is accepted. Manage can be opened to inspect
state, but no extension election, checkbox, security preference, TCC database,
Apple account or real signing key is changed.

The verifier requires one finalized, passed, unskipped exact XCTest and all
same-source product/registration/live-process/fixture-ownership receipts. It
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
finalized-test, fixture, registration and live-process receipts before optional
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
