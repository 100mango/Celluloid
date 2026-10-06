# Fixed Store screenshot capture candidate

This separate `codex/store-screenshots` push route captures the original app on
one disposable Mac, serially on the exact observed iPhone 17 Pro (1206×2622)
and iPad Pro 13-inch (M5) (2064×2752), both on iOS27.0. It creates fresh owned
instances from those exact observed device types; precreated instances are not
required or used. A missing or ambiguous type, different runtime, wrong image size, unknown process state, or command
failure stops the capture. There is no model fallback, rescaling, retry,
release qualification, archive work, or Store submission in this route.

The product source remains da9d4abd6484ddaff469677d96caf24362645d7c,
tree 304ee9c0e4197e4a282ae3933c9f510219b2106d. The successor's exact direct parent
must be public 91580d8453d47612fb1f83e075951acc763b0157,
tree 4613b47d2699bdbe5608635c8716ab2db4b0ff82. A different parent with the same
tree or an arbitrary ancestor does not satisfy this identity check.
The capture source has its own actual commit/tree and workflow identity.
Its source proof is 545 unchanged protected inputs plus one precisely hashed
UI-test helper insertion. It does not claim all 546 inputs unchanged or source
equivalence with the release test target. Removing the exact insertion restores
the original UI-test hash, proving both existing method bodies and assertions
remain byte-for-byte unchanged. Every product/project/resource input is unchanged.

The inherited capture overlay changes only `emitScreenshot(_:)` within protected inputs. With
`TEST_RUNNER_CELLULOID_STORE_CAPTURE=1`, its existing editor/collage checkpoints
attach `app.screenshot().pngRepresentation` unchanged as `public.png`. The
existing compact-phone JPEG path remains intact without the opt-in. No pixels
are drawn, resized, converted, composited or generated for the capture.

The earlier owned-device successor changed only the runner, its tests and this
document. It addressed the observed first attempt 37454490760/job 112238635892,
which completed toolchain/runtime/type/device discovery but stopped before build
because iPhone 17 Pro was not precreated. The complete retained devices JSON was
10470 bytes. That attempt passed the unique 17 Pro device-type check; its complete
type inventory was not retained, only a 20KB log tail, so no complete type-log
claim is made.

Discovery still requires exactly one available iOS27.0 runtime, exactly one
observed type for each fixed model, and an idle host. The runner retains the
selected raw runtime/type rows. It issues one `simctl create` per model with a
run/attempt/row-specific name and those exact type/runtime identifiers. It records
the actual successful command output, rejects noncanonical, repeated or initially
preexisting UUIDs, then reads back available devices. Exactly one matching UUID
must belong to the selected runtime/type, have the owned name, be available and
Shutdown, with no simulator booted. Only after that readback is the instance
eligible for boot, shutdown or deletion. No failed/unknown create is retried or
followed by speculative cleanup. The second instance is not created until the
first owned instance's cleanup is confirmed. Existing instances remain untouched.

The current narrow successor retains every protected input, including the
screenshot helper, byte-for-byte from 91580. Attempt 37456436117/job 112245086351
successfully created/read back the exact 17 Pro, built and installed the actual
product, and passed the original Photos readiness method. Before its first
fixture import, the optional `ps -axo pid=,ppid=,rss=,comm=` host probe exceeded
its 15-second allowance. PID/PGID 24006 was reaped after SIGTERM with code -15,
but group exit remained unconfirmed. That attempt remains failed: no imports,
reconcile, UI cases, PNGs or second-device creation followed. No receipt from
that host is retroactively accepted or relabeled as successful.

Only on a fully validated STORE_SCREENSHOTS route/context, bootstrap.host now
omits its five nonessential probes: vm_stat, memory_pressure, sysctl, df and ps.
It first requires a clear existing process guard and matching current row clock,
then emits a source/run/row-bound BOOTSTRAP_HOST_DIAGNOSTICS_NOT_COLLECTED record
with diagnostics_not_collected=true and the exact omitted command list. It does
not catch an already-running probe's timeout and continue, clear a failure,
change a command allowance or expand a deadline. Original/release/UIKit and
other valid routes retain the original host behavior. A future capture must
start as a fresh cohort; the failed 91580 host cannot resume under this change.
Actual necessary commands, their timing/ownership receipts and failure logs
remain collected within the same artifact caps.

Per device the unchanged required bootstrap sequence runs these two setup methods, imports its
existing six synthetic PNG fixtures, and verifies their original resource hashes:

- `EditorRegressionTests/testPhotosLibraryBootstrapReadiness`
- `EditorRegressionTests/testReconcileSyntheticPhotosAfterImport`

Then the unchanged UI methods run with dark system appearance:

- `CelluloidUITests/testSeededPhotoEditingSaveAndReopen`
- `CelluloidUITests/testTwoPhotoCollageZoomRotateAndSave`

That is two setup and two UI invocations per device, eight normally completed
invocations total. No 412-case cohort or Mac producer is run. The `ui` process
phase is intentional: the original large-phone row does not admit `dark`.
The bootstrap is called in process so its existing owned inner commands remain
the sole owners, with no nested outer process wrapper.

The workflow has one 60-minute Mac job. Both row clocks preserve the same first
step's source/run/attempt and monotonic/wall start. Native work ends by 2700s;
the existing 660s tail and final 240s outer margin stay bounded. Build is at most
900s; boot 60s; bootstatus 600s; install 300s; installed-app lookup 120s; permission 60s;
each setup test 360s; first import 480s and later imports 180s; selected UI command
900s. Each full fixed command allowance plus 15s for cleanup and 5s for finalization
must fit its immutable phase/work deadline before dispatch. Test body allowances
are not shortened to the remaining time. The capture-only native-process bridge
rechecks the actual route, source/run/row clock and full reserve immediately before
spawning, after owner setup. Spawn/setup consumes a frozen command deadline;
cleanup waits are clipped to the fixed cleanup deadline. Canonical callers keep
their existing behavior.
Checkout has a two-minute ceiling and capture a 52-minute ceiling, leaving
one minute for file-only failure retention and one for upload inside 56 minutes.
Exporter and summary each have 45s ceilings. No second device starts until the
first simulator's shutdown, deletion, and observed absence have all succeeded.
After that cleanup, the second device still must fit the same first clock's
2700-second work deadline. It never receives a fresh 2700-second allocation.
No later native command, including cleanup or exporters, runs after an unknown
owned process outcome or a denied signal. Failure retention is file-only.

Fixed command allowances (seconds), shared by both devices under that clock:

| Operation | Command allowance |
| --- | ---: |
| Xcode/version and each simulator inventory read |30 |
| Fresh owned create / exact created identity readback |60 /30 |
| Build once |900 |
| Boot / bootstatus |60 /600 |
| Install / initial owned container lookup |300 /120 |
| Photos grant / dark appearance |60 /60 |
| Bootstrap prepared-registration lookup |45 |
| Each original readiness/reconcile test |360 |
| First fixture import / each later import |480 /180 |
| Bootstrap host observations on Store capture |Not collected; explicit marker |
| Two existing UI cases together |900 |
| Finalized summary / attachment export |45 /45 |
| Post-test installed identity lookup |60 |
| Shutdown / observed shutdown check |45 /15 |
| Delete / observed absence check |45 /15 |

Every listed command requires the same 15+5-second reserve before admission. The absolute work endpoint
is 2700s from the first step. Existing tail endpoints are 2940s for product readbacks,
3000s for shutdown, 3060s for deletion, 3120s for source checks, 3300s for collection,
and 3360s for upload. They are shared endpoints, not per-device durations.

The built app, framework and Photos extension are fingerprinted and compared to
the actual installed product before/after execution. Selected attachments bind
the exact existing test, observed device UDID/model/runtime, capture source,
qualified product source and product fingerprint. PNG header, chunk integrity,
dimensions, bit depth, color type and presence of alpha/transparency are reported
from the original bytes. Alpha is not stripped. Actual image format/alpha and
visual quality are not predeclared successful before native capture.

The Xcode27 manifest parser accepts the verified flat array of test rows and
their attachments, at most 1MB, 32 rows, 256 attachments per row and 512 total.
The outer row's testIdentifier owns the attachment; an item's own similarly
named field cannot override it. Retained 04d18 native evidence proves the owned
simulator UUID was a direct item string value, but its key name was not retained.
Therefore capture requires an exact direct scalar match to the owned UUID,
records the actual matching key(s) and value(s), and rejects any conflicting
deviceId. Substrings, nested-only values and foreign outer cases are rejected.
The raw export manifest is retained, so this historical evidence limit is
explicit rather than resolved by guessing a field spelling. All incoming JSON
uses the existing strict duplicate-key/nonfinite-number parser.

Initial app paths must resolve inside that exact simulator's
Devices/UDID/data/Containers/Bundle/Application tree and end in Celluloid.app.
Post-test identity uses the existing uikit_installed_identity readback/validator,
including its relocation, metadata and executable checks; full bundle bytes
must still match the captured build. Command deadline timing receipts survive
success and failure retention.

Selected runtime/type rows and per-device create/readback receipts are included
in the existing bounded progress/report packet, including unsuccessful attempts.
This does not expand the four-image, 5MB-per-file, 20MB-total artifact limits.

The artifact contains exactly four raw candidate PNGs on success, each at most
5MB, with receipts, full bounded UI/setup logs, and other log tails within 20MB total. No xcresult bundle is uploaded.
Images and all other files are hashed or bound in the retained packet. Exceeding
the limits fails retention; it does not authorize resizing or recompression.
Review is pending even when capture succeeds. These remain synthetic diagnostic
fixtures. The root must inspect the four actual images and approve their use
before any separate Store action.

Expected categories come from Apple's screenshot specification: Dynamic Island
medium-display iPhone and 13-inch iPad. Native capture must establish the actual
pixel sizes, and alpha/transparency can prevent direct Store use.
https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/

Local checks (no Xcode/simulator/network):

```
PYTHONPATH=Scripts python3 -m unittest -v test_store_screenshots test_store_screenshots_route test_store_screenshots_deadline test_original_ios_process_guard test_original_ios_supervision_integration test_uikit_full_shipping_bootstrap test_uikit_full_shipping_gate.ClockAdmissionTests test_uikit_full_shipping_gate.CommandLineTests test_uikit_installed_identity
PYTHONPATH=Scripts python3 -O -m unittest -v test_store_screenshots test_store_screenshots_route test_store_screenshots_deadline
python3 Scripts/store_screenshots.py verify-source
```
