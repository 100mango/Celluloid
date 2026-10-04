# Celluloid modernization and release gates

## Preserved product and data contract

- App `Mango.Celluloid`, Photos extension `Mango.Celluloid.CelluloidPhotoExtension`, framework `Mango.CelluloidKit`; historical Apple ID **1124966798**
- Release candidate **1.1 / build 2**; historical release 1.0 / build 1. Shipping deployment floor remains iOS 15; Xcode 27 test bundles require iOS 17+
- Original features: photo loading, all filter presets, editable speech bubbles/stickers with move/rotate/resize/delete, all two/three/four-photo collage templates, saving/sharing, and the non-destructive Photos editing extension
- Original English/Chinese UI and artwork identity are preserved. Scene lifecycle supports modern iOS launch/foreground/background behavior. Both phone and tablet layouts remain supported
- Photos adjustment identifier **`Mango.CelluloidPhotoExtension`**, format version **`1.0`** remain unchanged. The keyed dictionary retains preset raw values and NSValue geometry. Optional `referenceCanvasSize` permits new edits to preserve positions and affine transforms across viewports; old archives without it keep absolute point semantics on the first valid canvas. Their missing historical viewport cannot be reconstructed
- Native Mac→UIKit archive fixtures preserve exact decoded semantics in observed simulator tests. These are contemporary compatibility fixtures, not recovered historical user archives. A float32 NSValue constructor normalized to64-bit before archiving, so it does not prove genuine armv7 archive compatibility

## Dependency and packaging integrity

SnapKit **5.7.1**, revision `2842e6e84e82eb9a8dac0100ca90d9444b0307f4`, is pinned through SwiftPM. The exact upstream MIT notice is bundled in `CelluloidKit.framework/SnapKit-LICENSE.txt`; source/archive validation requires SHA-256 `7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b`. Historical Pods sources/licenses remain attribution-only and are not linked. [Upstream notice](https://github.com/SnapKit/SnapKit/blob/2842e6e84e82eb9a8dac0100ca90d9444b0307f4/LICENSE)

The marketing icon and18 required opaque, unmasked renditions use the existing published identity recovered from an [Apple-served1024px rendition](https://is1-ssl.mzstatic.com/image/thumb/Purple20/v4/42/4f/a6/424fa61d-10d0-64c3-6c76-757ea707d4da/pr_source.png/1024x1024bb.png). Original rendition SHA-256: `e8741149fe7f2cfc57ce0f7dcef1ce21cbc121c3fe05b697bd54739a9a506cea`. This is not a recovered design-source file.

The localized in-app Privacy Policy opens the approved HTTPS destination https://100mango.github.io/app-privacy/ . Tests verify URL wiring, accessible reachability and closing the browser. Privacy declarations must remain truthful to final code; dependency inclusion alone does not establish required-reason API usage or tracking.

## Reproducible unsigned qualification

Run `python3 Scripts/generate_project.py` after changing source/resources and `python3 Scripts/validate_release.py` for static packaging checks. Open the workspace; no pod install is required. Linux validation is not an Apple build or runtime test.

The push/manual workflow on `codex/ios-modernization` uses standard `xcode-27` VMs and `/Applications/Xcode_27.app/Contents/Developer`. It logs and verifies Xcode27.0, actual SDK/runtime versions and observed device identifiers. Four fresh device jobs run serially (`max-parallel: 1`, `fail-fast: false`):

- iPhone SE (3rd generation): compact current-runtime phone, not the smallest historical iOS15 screen
- iPhone18 Pro Max: large phone
- iPad mini (A17 Pro): small tablet
- iPad Pro13-inch (M5): large tablet

Observed pre-provisioned shutdown devices are used where available; SE3 is created only from an observed compatible type/runtime. Each VM builds the same exact source with bounded parallelism and indexing disabled. Pure units run before any media prerequisite. XCTest installs its test host; actual app registration and Photos authorization are then verified. Read-only PhotoKit readiness precedes six single synthetic imports, and original resource hashes/unique asset IDs are reconciled before integration/UI tests.

The first cold import has a480s setup ceiling based on observed exact-asset recovery by approximately365–412s; subsequent imports retain180s bounds. No timed-out import is blindly retried. A recovered timeout still fails that run, while independently verified resources allow remaining tests to execute. App-test deadlines and strict assertions are unchanged. Device jobs have a60-minute outer limit; shell steps and child commands have independent bounds. Missing live browser output alone is not a stall diagnosis.

Pinned checkout uses explicit `github.sha` without persisted credentials. Beginning/end source-proof steps require the fixed same-repository branch, matching workflow SHA, exact commit/tree and clean tracked files, and log the workflow digest. New pushes do not cancel active runs. An unsigned generic-iOS Release archive and bundle/version/architecture/license inventory run only after all four device jobs succeed. No merge, signing, upload or publication is performed. No paid runner, artifact or cache upload is configured. Named screenshot evidence is synthetic and bounded; xcresult bundles remain local to each runner and summaries are logged.

## Regression scope

- Legacy/current adjustment decode, malformed type/range/overflow rejection, exact Mac-authored archive semantics, repeat restore and extension session reset
- Every original preset/asset/template; image orientation and UIImage scale1/2/3; affine decoration position/pixels across rotation, compact/resized windows and canvas persistence
- Full label containment and usable controls at normal/largest Dynamic Type in English/Chinese, including320×568 and568×320 historical geometry, compact phones and resized/tablet layouts
- Genuine Photos grant/revoke/limited selection/management/pruning on SE3, separate from DEBUG denied/limited-empty states. Granted flows handle only the exact expected Celluloid Photos alert and assert real asset availability with no limited/denied UI
- Photo load/edit/save/reopen, two-photo collage zoom/rotation/save, distinct asymmetric two/three/four-source composition and reorder, empty/error states, foreground/background and cancellation
- Collage requests coalesce and complete before save, including failures. Source requests are bounded at1600×1600; historical final collage output remains800×800, an explicit quality tradeoff
- Official XCTest accessibility audits on home, picker, decorated editor, full-screen caption editor and Saved, with normal semantic taps. Caption editing supports Dynamic Type and exact edit/Cancel persistence. Fixed image typography is exposed as editable artwork with text content; only the exact legacy BubbleLabel Dynamic Type issue on the artwork canvas is excepted, not clipping/contrast/detection/hit regions
- Light/dark editor/collage checks. Physical VoiceOver and device interaction remain separate gates

## Renderer fidelity and measured checkpoint

App and extension saves snapshot immutable adjustments and use generation-safe, exactly-once asynchronous completion. File loading, orientation/filter preparation, pixel copying and JPEG encoding run on a serial background queue. UIKit records one full-height, fixed-pixel-budget vertical strip at a time, with the complete original layer stack and source crop at global pixel coordinates. Warmed source-provider copies are released before composition. No per-decoration raster array is retained; output is not downsampled or forced to SDR/opaque. The original synchronous full-canvas renderer remains an independent test oracle.

At [68d0907 / run37148524992](https://github.com/100mango/Celluloid/actions/runs/37148524992), on Xcode27.0/iOS27.0 Pro13, **all74 test executions passed**:66 pure units,3 readiness/reconciliation executions including a timeout probe,3 Photos integrations and2 accessibility UI cases. The run is nevertheless **red** because the first fixture import exceeded180s; exact read-only reconciliation then proved one correct asset and all six distinct source hashes. This is a focused application-test checkpoint, not a final matrix pass.

Strict whole-output comparisons had zero differences for12 overlapping decorations, uneven1603×1207 dimensions, rotated/scaled canvases, alpha/P3 and multi-strip extended-float source values. Dimensions, bitmap properties, original handle-exclusion PNG bytes and adjustment data remain asserted. Horizontal tiling had changed three text-edge pixels; full-height strips corrected that observed failure without tolerances.

Measured48MP fallback-UIImage export: **455,286,144B sampled peak**, **27.98ms maximum main-queue latency**,1.290s completion. The warming-release-only control measured636,100,288B /71.81ms; full-canvas controls were over811MB on the same run. The earlier original full-canvas baseline was approximately686MB /500ms. These are sampled simulator observations, not universal performance limits.

With12 oversized overlapping decorations on12MP, peak was183,245,696B and max main latency180.41ms. One strip batch was8,448,000B with a48,000,000B output canvas; after1s footprint recovered to111,024,960B from63,134,848B baseline. Cancellation after a consumed strip completed exactly once and recovered to its pre-cancel baseline. This residual and worst-case label rasterization remain visible risks, not hidden by storage counters.

## Remaining release gates

- Full four-device **exact final-head** regression, unsigned archive, dependency inventory and final source proof; no earlier or focused result grants this automatically
- Actual Photos-host extension edit→save→reopen→choose Original→save with original-pixel comparison, plus Photos’ own Revert to Original with cleared adjustment data. Direct extension-class tests do not prove host integration
- URL-backed48MP measurement using `PHContentEditingInput.fullSizeImageURL` plus display preview, repeated save/cancel recovery, and physical Photos-extension memory limits. The fallback-UIImage benchmark is not the extension process budget
- Physical iPhone/iPad, large panoramas, camera-originated/HEIF/HDR/gain-map inputs, iCloud/offline failures, save failure/retry, multitasking, assistive technology and older supported runtimes. No claim that all hardware or historical32-bit archives are verified
- Six corrected, visually accepted native Chinese App Store captures from the frozen shipping source. Rejected/provisional images stay outside any upload-ready package
- Final App Store metadata/privacy/support/age/export declarations, authorized signing/team/entitlements and submission. The app record’s historical release is1.0/build1; this candidate remains1.1/build2 while adjustment format stays1.0
