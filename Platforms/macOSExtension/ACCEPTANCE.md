# Native macOS Photos extension acceptance

## Scope and current qualification

The native adapter is for the original single-photo extension's filters, stickers and speech bubbles. It retains `Mango.Celluloid.CelluloidPhotoExtension`, `com.apple.photo-editing`, and adjustment identifier/version `Mango.CelluloidPhotoExtension` / `1.0`. It adds no entitlements, credentials, keys, app groups, subscription, network use, collage extension mode, or new document format.

`CelluloidMac` now depends on the actual existing extension target and embeds its `.appex` in `Contents/PlugIns`. Its principal class is an NSViewController containing an NSHostingController. The native UI edits full affine values without converting them to normalized document overlays. The exact c587 reviewed output writer is compiled by reference, not independently forked.

The following are source changes and test definitions, not executed Apple evidence. Linux static checks cover generator graph/resource registration, hash-exact fixture inventory and existing repository Python regressions. Apple compilation, manufactured-writer UIKit compatibility, raster typography equivalence and actual Photos-host consumption remain open until their own source-bound runs pass.

## Required deterministic gates

Run the native Mac or extension scheme's `CelluloidMacPhotosExtensionTests` on the admitted standard Mac runner. It compiles the same production adapter sources and reviewed `PhotosOutputWriteTests.swift`. The suite covers:

1. Actual UIKit archives: literal center/bounds/affine/canvas preservation, original dictionary names, filter identity, grouping order, invalid/unknown data and budget rejection
2. Newly manufactured Mac NSValue geometry, securely redecoded locally and separately exported for the original UIKit reader
3. Immediate host Done during an observed paused source load (no-change/no render preparation), session cancellation/replacement during observed source work, immutable source snapshots, orientation mismatch, freeze-before-finish and damaged/historical no-canvas read-only handling
4. Raw reflected/sheared/translated sticker pixels against a separately calculated affine matrix, historical 16pt artwork inset, bounds origin, filter/orientation against independent CoreImage and bounded nontruncating text
5. Principal-controller native child containment and pure format probes; canceled-controller finish produces no callback
6. Reviewed output writer's existing cancel-before-write, observed prewrite cancellation, replacement, no-overwrite, ownership, staging cleanup and reentrant delivery tests

The main native suite retains PhotosHostFinishCoordinator's repeated finish, cancellation, synchronous observer cancellation and exactly-once/error coverage. Neither controller tests nor the direct PhotoKit tests below are Photos-host E2E.

Transfer only the source/hash-bound manufactured record described in `../MacExtensionTests/Fixtures/PROVENANCE.md`, then run `MacPhotosManufacturedAdjustmentTests` in the original UIKit test app. A missing/skip/failing fixture blocks a parity claim. Do not substitute a same-serializer roundtrip.

## Installed package / host gate

Use a disposable test account/library and the exact admitted build. No code in this change installs an extension, changes persistent security settings, grants Photos access, or signs a product. Use existing authorized build/test flow; keep strict deep verification. Confirm actual nested executable, Info.plist, product version, identifier, minimum OS, resource bundles and unchanged sandbox-only extension entitlement set. Do not infer a correct child signature from the parent alone.

Install/open the actual containing app through a supported, explicitly authorized route. In Photos' extension management, enable the existing Celluloid photo-editing extension only with appropriate permission. Record that the launched extension executable and containing app match the qualified commit. Do not count opening the document app or directly instantiating the controller as this gate.

Seed only named synthetic assets through supported Photos import/PhotoKit, after the exact known access prompt is manually approved. Keep fail-closed unexpected-interruption monitors; no broad Allow/OK/CAPTCHA/autohandler. Before editing, enumerate and hash all relevant asset resources using PhotoKit: original photo, current full-size photo, adjustment base (if present), adjustment data and format ID/version. Record asset identifier, pixel dimensions, orientation/color metadata, pixel digest and source fixture hash. Never seed or change a personal library.

## Actual Photos-host scenarios

1. Fresh asymmetric oriented photo: launch Celluloid from Photos → Edit → Extensions; select a nondefault filter; add both a sticker and bubble, type full multilingual text through the real text field; change position, size and rotation. Capture actual controls and output. Click the host Done, then Photos Done. Refetch the same asset; require original bytes unchanged and distinct verified current/adjustment resources. Reopen from Photos and prove editable filter, text and exact geometry. Modify again and recheck. Run normal and sandbox-qualified builds.
2. Actual UIKit 1.0 reference-canvas fixture: import source and install its independently generated current raster/adjustment in the disposable library. Confirm host input is the source and adjustment actually associated with that asset. Native reopen must retain all fields, appearance and source orientation; native modification must decode/render through the original UIKit reader. Verify current/original resources before and after. Test both orientations and wide-gamut source; do not loosen the color/geometry/text oracle.
3. Historical-schema missing-canvas fixture: use actual UIKit fixture bytes with their literal geometry and an independently supplied current raster. Host must show the current appearance and the read-only explanation. Host Done must consume the no-change output without changing any original/current/adjustment digest. Repeat with host Cancel. Retaining files in a direct-controller test is not evidence that Photos consumed no-change correctly.
4. Over-budget, corrupt and unsupported associated metadata: same unchanged-resource proof and read-only behavior, including switching from an earlier valid asset and back. Unsupported foreign-format input follows Photos' selected current base; never infer the system original or borrow a prior canHandle probe. Verify Photos retains the correct base and Revert behavior using actual resource inventories.
5. Lifecycle: start A → slow preview → switch/cancel → start B; repeated host Done; cancel during render; cancel after writer preparation but before delivery; close/reopen Photos; repeated text edits/IME composition while previews publish. Require no stale preview, callback after cancel, cross-asset output, abandoned output file, truncated text, or controls left disabled. Use synthetic barriers only in deterministic tests; host tests exercise real UI/lifecycle.
6. Revert: after verified saved layered edit(s), invoke the host's actual Revert action after explicit approval appropriate to the test asset. Refetch and compare original and current pixels/resources against the seeded original. Do not infer Revert from a controller return value.
7. Accessibility/localization: keyboard-only traversal, actual AppKit popup/palette/layer/text control focus, narrow host window, full text-entry retention, VoiceOver labels, English and Simplified Chinese. Run the official audit without suppressing categories or issues.

## Evidence / stopping conditions

A gate is passed only for its exact tested source, OS/runtime, architecture, sandbox mode and host. Retain small structured receipts and selected bounded screenshots/log excerpts under the existing whole-workflow ≤20MB and one-day policy; no raw xcresult caches/video. Keep personal photos and metadata out of fixtures/artifacts. Stop on unexpected permission/security prompts, unknown provenance, any changed original digest, unsupported host/no-change behavior, or missing signing authorization. Report blockers precisely; do not publish, sign with real keys, change scripts under hold, or launch a new CI workflow without the coordinator's admission.
