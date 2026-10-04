# Actual macOS Photos host prerequisite in the existing Mac job

Integration draft based on public `9c9e7fc9c12df342c883e8a1e4462f796469842c`,
tree `f53aa262fb56d31cd0b2f03f3836147c26ff2858`. Rebase the frozen source
snapshot before combining with a later source. This is host registration and
entry coverage only. Every acceptance report retains `complete_host_e2e: false`.

## Execution and ownership

There is no new workflow or runner. The existing serial native Mac job remains
bounded to 45 minutes. After its ordinary UI stages, sandbox child checks, and
Release compile/package prerequisites,
a 14-minute step reuses the exact minimally signed `celluloid-sandbox` app and
external UI bundle. The actual Photos test retains its 12-minute bound. No
second app copy or re-sign occurs: that would risk duplicate same-ID extension
registration after ordinary UI already launched the original product.

The existing Mac pixel probe uses one build and sequential 2x/3x devices, with
an 18-minute active budget inside a 20-minute step. Observed prior Mac stages
outside that probe took about 16.5 minutes; the first pixel probe took 5.5 minutes,
including a 50.6-second build and a 38.4-second consumer. Two such device cycles
plus the 12-minute host cap fit approximately 39 minutes. These are measured
planning inputs, not a guarantee. A timeout remains a failed gate. The first job step records a source-bound
monotonic clock with a conservative 41-minute execution budget, leaving four
minutes outside that clock for runner/action setup. Before preparation and again
immediately before the host process, the gate requires at least 17 minutes:
12 for host execution plus five reserved for teardown, proof collection and
artifact upload. Optional Mac evidence exporters share at most three minutes,
shortened further if the source-bound job clock requires preserving the final
two minutes. Required source/host/consumer/fixture/diagnostic records are admitted
first; timeout or unknown exporter cleanup is an explicit omission and stops
later optional exporters. A missing/invalid clock or insufficient remaining time stops
before launch with explicit incomplete/false evidence. It does not shorten the
required host scenario or manufacture a prerequisite pass.

Host discovery does not require a successful layer-pixel comparison, but its
signed sandbox product and child must pass first. Layered edits remain protected;
this phase never saves, cancels a modified photo, or invokes Revert.

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
and two explicitly SHA-pinned diagnostic-only test files;
the full combined source contract independently binds the resulting candidate.

## Shared evidence budget and remaining work

Host evidence is a bounded 1,000,000-byte subset of the existing Mac 3,000,000-byte
allocation, merged before optional logs and screenshots. Overall eleven-job
allocation stays 19,500,000 bytes, retained one day. Hash mismatches or required
host evidence exceeding the shared cap fail collection. Mandatory outcome, source,
product, finalized-test, fixture, registration and live-process receipts reserve
space before optional screenshots or AX dumps. Both collectors replay complete
accepted proof and verify every hash; a JSON acceptance flag alone is insufficient.
Missing or oversized required proof fails collection of a claimed acceptance.
Failed-discovery bundles may retain incomplete diagnostics, explicitly marked
`prerequisite_accepted: false` and `diagnostic-only-incomplete`, including the
observed failure and every available source/ownership receipt. No extra artifact,
raw xcresult, Photos library, build product or account data is uploaded.

A passed prerequisite is followed by separately reviewed real save/reopen/cancel/
Revert, exact original/current/adjustment resource preservation, filter/layer/text/
geometry readback, localization, accessibility and lifecycle scenarios. Those
remain unexecuted by this draft, and layered saves require the strict renderer
gate and removal of the temporary protection before final qualification.

Primary references:
- [Apple extension creation and testing](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/ExtensionCreation.html)
- [Edit in Photos with extensions](https://support.apple.com/en-euro/guide/photos/pht820c5ba8a/mac)
- [See photo information in Photos](https://support.apple.com/en-euro/guide/photos/phta8b25fa42/mac)
