# Isolated native Fade/JPEG control

Prepared locally from public parent `a940bcdf8a92811210bcfacf84141dceb6c3fcd3`. Not published. No Apple CI was started. Swift compilation and native XCTest execution are unrun; Linux checks below are source/resource contracts only.

The existing `CelluloidMacPhotosExtensionTests` target compiles the production `MacPhotoRenderQueue` and `MacPhotoRenderer` directly. One new test creates its own queue, previews Original then Fade on that same renderer/context, and exports Fade once through the production JPEG codec. At 1200×800, the existing preview maximum of 1400 does not downsample. No new production API, instrumentation, IPC, entitlement, Photos logging, Photos-host changes, or workflow is needed.

The reference is the literal `expectedFade` implementation in the a940 `MacPhotosHostUITests.swift`, with its independent Core Image graph, opaque sRGB composition, and ImageIO JPEG quality 0.95. The copied PNG admission, bitmap, raster, and maximum-delta helpers retain the host contract. Only host deadline calls are removed. Three marked capture lines retain the reference pre-JPEG PNG and JPEG and expose that same reference JPEG to test-only format/profile validation. The existing host oracle file is unchanged. A portable contract verifies the copied helpers against the hash-pinned original. No production filter map, renderer, or codec is used by the reference.

`lifecycle-source.png` is copied byte-for-byte from the retained synthetic fixture in the run 37397207817 manifest:

- Public source: `a940bcdf8a92811210bcfacf84141dceb6c3fcd3`
- Retained path: `mac-host-observed/lifecycle-source.png`
- File SHA-256: `6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772`
- Bytes: 19,268; dimensions: 1200×800; 8-bit, upright, opaque sRGB PNG
- Decoded RGBA SHA-256: `a9424d913bfa4b18a70063fec1e05cdb4d679f5619d12897571e6b5868d22717`
- Historical expected PNG: `lifecycle-expected-save.png`, SHA-256 `4ff9356c945d26d5feb3c7254a5181b17fb10692f15fa0f529375b3568da9979`
- Historical reference JPEG SHA-256: `1f6b8bb3ea7963c0663965da27c9b41e717335b3d4a6f011a70e83762c1904ba`

The historical expected PNG/JPEG hashes are supplemental context only. Neither is a pass criterion or substitute for the same-run reference. The bundled source is test-only; no asset is copied into a production target.

The test requires the exact fixture hash before decoding. Its copied host checks require 1200×800, orientation 1, 8-bit RGB, opaque alpha and admitted sRGB PNG structure/profile. Both JPEGs additionally require one JPEG image, those dimensions/orientation/depth, a named profile, and the independent system sRGB ICC bytes. Pixel acceptance is the unchanged maximum channel delta ≤2, with no geometry, scale, pixel exclusions, or tolerance fitting. The same-run reference must also differ from the original by >2.

On a native run, the single XCTest retains only these fixed names, once each:

- `codec-actual.jpg`, `codec-reference.jpg`: ≤128 KiB each
- `codec-actual-decoded.png`, `codec-reference-decoded.png`, `codec-reference-prejpeg.png`: ≤128 KiB each
- `codec-control.json`: ≤16 KiB

The fixed aggregate attachment budget is 512 KiB, admitted before every attachment. Exceeding any per-file or aggregate cap is a diagnostic failure for this synthetic flat-color 1200×800 source; it never permits expanding the output budget. The report records hashes, metadata, max delta, changed pixels, pixels and RGBA channels over 2, RGB RMSE, and scope limitations before the pixel assertion. Attachments are kept even if pixel comparison fails. An earlier admission/encode failure may leave only the attachments captured before that failure.

The reference pre-JPEG raster is observable within its independent test code. The actual export raster is private to the existing queue and is deliberately not exposed. The preview is not relabeled as the actual export raster. This control does not observe the actual Photos `PHContentEditingInput`, submitted JPEG bytes, or Save/Cancel/Revert. Even a pass cannot establish Photos-host parity. A failure only establishes a pre-host difference on this synthetic source and runtime.

## Portable review checks

```sh
python3 -m unittest discover -s Scripts -p 'test_mac_native_codec_control.py' -v
python3 -m unittest discover -s Scripts -p 'test_mac_photos_extension.py' -v
python3 Scripts/validate_native_sources.py
git diff --check
```

## Smallest future native invocation

Run only after separately admitting native execution on a Mac with the repository's supported Xcode. This command has not been run:

```sh
xcodebuild -project CelluloidNative.xcodeproj \
  -scheme CelluloidMacPhotosExtension -configuration Debug \
  -destination 'platform=macOS' -parallel-testing-enabled NO \
  -only-testing:CelluloidMacPhotosExtensionTests/MacPhotoNativeCodecControlTests/testRetainedSourceFadeExportAfterOriginalAndFadePreviews \
  -resultBundlePath /tmp/CelluloidNativeCodecControl.xcresult \
  CODE_SIGNING_ALLOWED=NO test
```

Use a fresh result-bundle path. Inspect the six fixed attachments in that isolated test's xcresult. No Photos app launch or host UI test is selected. The original 42 native extension cases, the UIKit selection/count (412 across four rows), the admitted full-shipping candidate, and every existing workflow remain unchanged.

## Local-only fixed cloud diagnostic route

The route candidate adds `mac-native-codec-control.yml` and a single-purpose
`run_mac_native_codec_control.py`. It has not been published or executed.
Publishing the synthetic PNG as a new public Git blob is a separate action;
the historical artifact and this local draft do not supply that approval.

The proposed route responds only to a push on
`codex/mac-native-codec-control` in `100mango/Celluloid`. It has one `xcode-27`
job, no matrix or dispatch inputs, read-only repository permission, pinned
checkout/upload actions, disabled credential persistence, no cancellation of
other runs, and the existing shared native concurrency group. None of the
older workflow branch selectors matches this new branch.

Admission requires a clean checkout whose HEAD and workflow SHA equal the event
SHA, exactly one parent equal to a940, and all 887 non-manifest source files
matching the full path/mode/size/SHA-256 manifest. The manifest's own hash and
Git tree are captured separately to avoid self-reference. Source fingerprints
are checked again after portable tests and after the native attempt. No original
source-verifier contract, existing workflow, production renderer, host test,
oracle, tolerance or Swift diagnostic is modified by this route delta.

The only native operations are an unsigned `CelluloidMacPhotosExtension`
build-for-testing followed, only if that succeeds, by test-without-building
with the exact single-case selector. It compiles the existing test target but
does not execute the other 42 cases. Fixed one-iteration/nonparallel settings
disable fan-out; there is no retry or fallback route, Photos UI call, extension
registration, provisioning, signing, archive, simulator, or iOS command.

Budgets: 20-minute job, 15-minute driver step, 870-second internal clock with
30 seconds reserved for finalization, then at most 3 minutes for artifact upload.
Command limits are 10 seconds for Xcode version, 60 for the focused portable
contracts, 480 for build-only, 120 for the native command (90-second XCTest
allowance), 30 for summary, and 60 for attachment export. Each subprocess uses
the existing `native_process.run` with its at-most-15-second owned-process-group
cleanup. A timeout stops subsequent native/export processes; cleanup is explicitly
unconfirmed rather than silently retried. Fresh fixed derived-data/result/export
paths reject stale evidence before execution.

The extractor uses the existing xcresulttool attachment export and bounded
no-follow/stable-span file reader. Only the six exact names belonging to the
single testcase are retained; unknown ordinary XCTest attachments stay local.
Duplicate, wrong-owner, malformed, symlinked, hardlinked, oversized or escaping
codec attachments fail. Existing 128 KiB image/JPEG, 16 KiB metrics, and 512 KiB
aggregate attachment limits remain unchanged. A separate 1 MiB total evidence
limit includes receipts, the exact at-most-128 KiB test transcript, at-most-32 KiB
build tail, at-most-32 KiB summary/export inventory each, and bounded failure
tails. Raw xcresult, products and exported unselected attachments are excluded.

The outer replay requires one actual non-skipped testcase, matching raw XCTest
identity/counts/terminal and finalized single macOS 27 arm64 summary. It verifies
artifact hashes, source binding, PNG profile/dimensions/opacity, native-versus-
outer decoded hashes, maximum delta, changed-pixel count, above-two counts and
RGB RMSE. The unchanged independent PNG decoder compares every channel without
masks, geometry changes or fitted offsets. A failed pixel result retains the
diagnostic artifacts but never becomes a passing run. Even a complete passing
control always reports `complete_host_e2e: false`.

Local-only validation commands for the route:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Scripts -p 'test_mac_native_codec*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s Scripts -p 'test_mac_native_codec*.py' -v
```
