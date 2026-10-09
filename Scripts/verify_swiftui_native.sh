#!/bin/bash
# First migration slice only. Never signs, archives, uploads to Apple, or changes a ref.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -s)" = Darwin
test "${DEVELOPER_DIR:-}" = /Applications/Xcode_27.app/Contents/Developer
mkdir -p build
xcodebuild -version | tee build/swiftui-xcode-version.txt
xcodebuild -version | grep -qx 'Xcode 27.0'
python3 Scripts/verify_swiftui_integration.py > build/swiftui-topology.json
mkdir -p build/swiftui-acceptance
out="$PWD/build/swiftui-acceptance"
device=''
cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "$device" ]]; then
    python3 Scripts/run_bounded.py --seconds 30 --label swiftui-owned-simulator-shutdown xcrun simctl shutdown "$device" > "$out/shutdown.log" 2>&1 || true
    python3 Scripts/run_bounded.py --seconds 30 --label swiftui-owned-simulator-delete xcrun simctl delete "$device" > "$out/delete.log" 2>&1 || true
  fi
  printf '%s\n' "$status" > "$out/process-exit-code.txt"
  exit "$status"
}
trap cleanup EXIT

# The selector creates one new simulator and checks the observed iOS 27 runtime.
python3 Scripts/select_test_devices.py 'iPhone SE (3rd generation)' > "$out/device.txt"
device=$(cut -d' ' -f1 "$out/device.txt")
test -n "$device"
base=(-project Celluloid.xcodeproj -scheme Celluloid -configuration Debug
      -destination "platform=iOS Simulator,id=$device" -derivedDataPath .build/swiftui-ios
      CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO COMPILER_INDEX_STORE_ENABLE=NO)
python3 Scripts/run_bounded.py --seconds 720 --label swiftui-ios-build xcodebuild "${base[@]}" -jobs 2 build-for-testing 2>&1 | tee "$out/build.log"
# Reuse the existing bounded process owner; no parallel matrix or extra job.
python3 Scripts/run_bounded.py --seconds 300 --label swiftui-core-package swift test --package-path Packages/CelluloidCore --scratch-path .build/swiftui-core --jobs 2 2>&1 | tee "$out/core-package.log"
python3 Scripts/run_bounded.py --seconds 300 --label swiftui-rendering-package swift test --package-path Packages/CelluloidRendering --scratch-path .build/swiftui-rendering --jobs 2 2>&1 | tee "$out/rendering-package.log"

python3 Scripts/run_bounded.py --seconds 60 --label swiftui-ios-boot xcrun simctl boot "$device"
python3 Scripts/run_bounded.py --seconds 300 --label swiftui-ios-bootstatus xcrun simctl bootstatus "$device" -b

# New state/cancellation tests and original exact pixel/write oracles are retained.
# Capture a failure status before exporting its genuine summary, then restore it.
set +e
python3 Scripts/run_bounded.py --seconds 420 --label swiftui-ios-units xcodebuild "${base[@]}" \
  -resultBundlePath "$out/units.xcresult" -parallel-testing-enabled NO -collect-test-diagnostics never \
  -only-testing:CelluloidTests/PhotoSelectionIdentityTests \
  -only-testing:CelluloidTests/PhotoSelectionSessionTests \
  -skip-testing:CelluloidTests/PhotoSelectionSessionTests/testRealSelectedLookupPreservesOrderAndIdentity \
  -only-testing:CelluloidTests/SwiftUIEditorSessionTests \
  -only-testing:CelluloidTests/PhoneEntryDesignTests \
  -only-testing:CelluloidTests/SwiftUIOriginalDesignTests \
  -only-testing:CelluloidTests/AsyncImagePipelineTests \
  -only-testing:CelluloidTests/FilterTests \
  -only-testing:CelluloidTests/PhotosOutputWriteTests \
  -only-testing:CelluloidTests/AdjustmentDataTests/testLegacyArchiveRoundTripsWithoutChangingItsDictionary \
  -only-testing:CelluloidTests/AdjustmentDataTests/testResourceBoundariesPreserveEveryLegacyLayerAndTextUnit \
  -only-testing:CelluloidTests/AdjustmentDataTests/testMalformedArchivesAndUnexpectedClassesAreRejected \
  test-without-building 2>&1 | tee "$out/units.log"
units_pipeline_status=("${PIPESTATUS[@]}")
units_status=0
for status in "${units_pipeline_status[@]}"; do
  if [[ "$status" -ne 0 ]]; then units_status=$status; fi
done
set -e
summary_status=0
xcrun xcresulttool get test-results summary --path "$out/units.xcresult" > "$out/units-summary.json" || summary_status=$?
if [[ "$units_status" -ne 0 ]]; then exit "$units_status"; fi
if [[ "$summary_status" -ne 0 ]]; then exit "$summary_status"; fi

# Fresh simulator, no seeded photos: this gate does not establish library readiness.
# Keep both the original 3-second interaction failure and post-budget diagnostics.
set +e
python3 Scripts/run_bounded.py --seconds 240 --label swiftui-picker-entry-ui xcodebuild "${base[@]}" \
  -resultBundlePath "$out/picker-entry.xcresult" -parallel-testing-enabled NO -collect-test-diagnostics never \
  -only-testing:CelluloidUITests/CelluloidUITests/testBeautifyOpensSystemPickerAndCancelsRepeatedly \
  -only-testing:CelluloidUITests/CelluloidUITests/testPrivacyPolicyEntryRemainsAccessibleAndCanClose \
  -only-testing:CelluloidUITests/PhoneEntryDesignUITests \
  test-without-building 2>&1 | tee "$out/picker-entry.log"
ui_pipeline_status=("${PIPESTATUS[@]}")
ui_status=0
for status in "${ui_pipeline_status[@]}"; do
  if [[ "$status" -ne 0 ]]; then ui_status=$status; fi
done
set -e
summary_status=0
xcrun xcresulttool get test-results summary --path "$out/picker-entry.xcresult" > "$out/picker-entry-summary.json" || summary_status=$?
# Export after all measured UI work; this cannot contaminate a tap measurement.
# No private Photos hierarchy, library enumeration, fixture or prewarming is added.
python3 Scripts/run_bounded.py --seconds 45 --label swiftui-picker-attachments \
  xcrun xcresulttool export attachments --path "$out/picker-entry.xcresult" \
  --output-path "$out/picker-attachments" > "$out/picker-attachments-export.log" 2>&1 || true
if [[ "$ui_status" -ne 0 ]]; then exit "$ui_status"; fi
if [[ "$summary_status" -ne 0 ]]; then exit "$summary_status"; fi
python3 - "$out/units-summary.json" "$out/picker-entry-summary.json" <<'PYCOUNT'
import json, sys
for path, expected in zip(sys.argv[1:], [57, 4]):
    data = json.load(open(path))
    for key, value in {'totalTestCount': expected, 'passedTests': expected, 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0}.items():
        assert type(data.get(key)) is int and data[key] == value, (path, key, data.get(key), value)
    assert data.get('result') == 'Passed' and not data.get('testFailures'), path
    print('VERIFIED_TEST_COUNTS', path, expected)
PYCOUNT
printf '%s\n' 'First slice finished. Seeded Photos save/reopen, extension-host, all-platform and device acceptance remain separate gates.' > "$out/scope.txt"
