# Celluloid modernization and release gates

## Preserved shipping contract

- App `Mango.Celluloid`, extension `Mango.Celluloid.CelluloidPhotoExtension`, framework `Mango.CelluloidKit`; historical Apple ID 1124966798
- Image editing, all original filters, editable bubbles/stickers, two/three/four-photo collage layouts, photo saving/sharing, iPhone/iPad portrait and landscape, and Photos editing extension
- Non-destructive Photos adjustment identifier `Mango.CelluloidPhotoExtension`, version `1.0`; same keyed-archive dictionary, raw preset names and NSValue geometry; absent empty arrays supported
- SnapKit 5.7.1 via SwiftPM replaces the active CocoaPods graph. Obsolete picker/presentation/dispatch/color/serialization dependencies use system frameworks or narrow local code. Historical vendored sources/licenses remain attribution-only and are not linked

## Reproducible validation

Run `python3 Scripts/generate_project.py` after adding source/resources. Open the workspace; no pod install is needed. The shared Celluloid scheme includes unit and UI regression targets.

The GitHub workflow verifies stable Xcode 27.0 and the iOS 27.0 runtime before building. One job runs unit/UI tests serially on an available iPhone and iPad simulator, seeds a generated RGB fixture into Photos, grants simulator Photos access, and builds an unsigned device archive including the extension. Logs, xcresult bundles and an xcresult summary are generated on the runner. No artifact/cache upload or paid runner is configured.

Coverage includes legacy archive compatibility, malformed archive rejection, all presets/assets, filter pixels/orientation, repeat state restoration, rendering, extension adjustment validation/cancel, direct seeded-Photo start/render/finish/error handling without library mutation, collage polygons, permission-denied recovery, limited/empty library management, repeat cancel, background/foreground, rotation, seeded photo edit/save/reopen and two-photo collage zoom/rotate/save. Collage source images are loaded/coalesced at up to 1600×1600 before export; the historical final collage size remains 800×800. Permission-denied/limited UI states use DEBUG-only injected authorization states; they do not prove the system limited-library picker itself works.

## Remaining release gates

- Passing CI for the exact final commit; Linux source checks are not an Apple build or runtime test
- Physical devices: large images, memory pressure, EXIF orientation, iCloud failures/offline recovery, save failure/retry, camera-originated photos, iPad multitasking and accessible text sizes
- Real Photos host: enable extension, edit/cancel/save, reopen old v1 edits and revert to original; unit tests do not establish host integration
- App Store Connect record verified: historical release 1.0/build 1. This candidate is 1.1/build 2 for app and extension; adjustment archive format remains 1.0. Confirm release signing/team/entitlements and Developer membership before upload
- Marketing icon now uses the verified Apple-served 1024px rendition of the existing published identity, with opaque alpha stripped losslessly. All required small catalog renditions are generated unmasked and opaque from that same artwork; this is not a recovered original design-source file. Source: https://is1-ssl.mzstatic.com/image/thumb/Purple20/v4/42/4f/a6/424fa61d-10d0-64c3-6c76-757ea707d4da/pr_source.png/1024x1024bb.png (source SHA-256 e8741149fe7f2cfc57ce0f7dcef1ce21cbc121c3fe05b697bd54739a9a506cea)
- Audit app/dependency privacy declarations against final code. No tracking/collection claims are inferred from the repository alone; no sensitive credentials or signing material belong in source
- App Store metadata, privacy/support URL, age rating, encryption/export declarations, review credentials if applicable, distribution signing and final authorized submission

No merge, signing, TestFlight upload, App Store submission or release is performed by this workflow.

## Observed pre-release validation

Commit `5b6f0a4ca4a4d4316bfc7e48959eb960374752e2` passed [run 37093925564](https://github.com/100mango/Celluloid/actions/runs/37093925564), job 111119852942, on macOS 27.0 / Xcode 27.0 (27A266a) / iOS 27.0 (24A434): 23 unit and 4 UI tests on iPhone 18 Pro, then the same 27 on iPad Pro 13-inch (M5), with zero failures or skips. Unsigned generic-iOS Release archive succeeded. Two bounded synthetic-data screenshots confirmed a visible sepia edit/sticker and populated collage after zoom/rotation.

The 1.1/build 2 metadata, Chinese permission/error translations, and recovered marketing artwork must pass the next exact-commit run before that candidate inherits this validation. Shipping deployment target remains iOS 15; test bundles target iOS 17+ because Xcode 27's XCTest runtime requires it. Only iOS 27 runtime execution is established by this CI job.

Candidate `ba50ccf88a03ab203644b2a205a2ce3940fdadd8` (1.1/build 2 with Chinese copy and marketing artwork) subsequently passed [run 37094983300](https://github.com/100mango/Celluloid/actions/runs/37094983300), job 111122966442, with the same 54 test executions and unsigned archive. The additional direct-extension output tests and opaque small-icon set require their own exact-commit CI result.


## Approved privacy-policy destination

The in-app localized Privacy Policy entry uses https://100mango.github.io/app-privacy/ (verified HTTP 200, unchanged final URL, bilingual approved content). Unit coverage checks the exact HTTPS URL and minimum hit target; UI coverage checks reachability after rotation and closing the in-app browser. The release workflow also emits `ARCHIVE_INVENTORY_BEGIN`/`END` JSON containing each app/extension/framework bundle identifier, versions, Mach-O architectures and linked libraries for independent signing allowlist review.


## Exact-source release proof

The fixed `codex/ios-modernization` branch has an unsigned push-triggered run. Checkout is pinned to the official action commit and explicitly to `github.sha`, with persisted checkout credentials disabled. Named beginning/end provenance steps check the exact commit and clean tracked source; the beginning also requires the fixed same-repository branch and `GITHUB_WORKFLOW_SHA == GITHUB_SHA`. Both ends log the reviewed workflow digest. This modernization workflow runs only on the fixed branch push or manual dispatch; it has no duplicate PR trigger. Historic PR merge runs remain regression evidence, not release-source proof. No source merge, secrets, signing or upload is included.


## Bundled dependency notice

The exact MIT notice from official SnapKit revision `2842e6e84e82eb9a8dac0100ca90d9444b0307f4` is bundled as `CelluloidKit.framework/SnapKit-LICENSE.txt`; source and archive checks enforce SHA-256 `7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b`. The source is https://github.com/SnapKit/SnapKit/blob/2842e6e84e82eb9a8dac0100ca90d9444b0307f4/LICENSE. This packaging correction adds the notice resource/project membership and validation only; it does not change app behavior, UI, build settings, or the visuals captured from `738b45f0c53f724d6f782d6346bb43c19c2f69d7`. The new candidate still requires a full source-bound CI pass.


## Visual home-layout correction

Native Release store-capture review caught a collapsed home layout that simple hittability assertions missed: the privacy footer's minimum-only height could absorb the available area. The footer now has a definite Dynamic-Type-aware height. New model geometry and simulator UI checks cover usable, non-overlapping primary choices in phone/iPad portrait/landscape and English/Chinese. The two rejected home images from the earlier capture run must be replaced; screenshot and release-source provenance must be refreshed for this behavioral fix.
