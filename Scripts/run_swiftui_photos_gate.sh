#!/bin/bash
# Reuses one caller-created simulator and build. Never creates/deletes/boots a
# device, signs an app, changes a ref, or launches a second build.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -s)" = Darwin
test "$#" -eq 5
phase=$1; device=$2; derived=$3; out=$4; owner=$5
case "$phase" in legacy|bootstrap|pristine|preservation) ;; *) exit 2 ;; esac
test "${DEVELOPER_DIR:-}" = /Applications/Xcode_27.app/Contents/Developer
python3 Scripts/swiftui_photos_gate.py admit "$phase" "$device" "$derived" "$out" "$owner"
finish() {
  local status=$?
  trap - EXIT
  printf '%s\n' "$status" > "$out/$phase-exit-code.txt"
  python3 Scripts/swiftui_photos_gate.py safety "$phase" "$status" "$out" || true
  exit "$status"
}
trap finish EXIT

if [[ "$phase" = bootstrap ]]; then
  bootstrap_deadline=$(python3 Scripts/swiftui_photos_gate.py budget bootstrap "$owner" deadline)
  python3 Scripts/run_bounded.py --seconds 45 --label seeded-fixture-generation \
    python3 Scripts/create_fixture.py > "$out/fixture-generation.log" 2>&1
  # Refuse unexpected leftover fixture files before any library mutation.
  python3 Scripts/swiftui_photos_gate.py fixture-files > "$out/fixture-files.json"
  python3 Scripts/run_bounded.py --seconds 45 --label seeded-owned-registration \
    xcrun simctl get_app_container "$device" Mango.Celluloid app > "$out/registration.log" 2>&1
  # The admission above bound this exact freshly-created simulator to the job.
  python3 Scripts/run_bounded.py --seconds 60 --label seeded-owned-photos-grant \
    xcrun simctl privacy "$device" grant photos Mango.Celluloid > "$out/photos-grant.log" 2>&1
  # Existing bootstrap retains command ceilings, real authorization/readiness,
  # one addmedia per fixture and post-timeout reconciliation without reimport.
  # Its original failure remains failure even if a late committed asset is found.
  RUNNER_TEMP="$out/bootstrap" python3 -u Scripts/probe_photos_bootstrap.py \
    "$device" --already-prepared --derived-data-path "$derived" \
    --deadline-monotonic "$bootstrap_deadline" 2>&1 | tee "$out/bootstrap.log"
  python3 Scripts/swiftui_photos_gate.py finish-bootstrap "$out"
  exit 0
fi

selectors=()
while IFS= read -r selector; do selectors+=("$selector"); done < <(python3 Scripts/swiftui_photos_gate.py selectors "$phase")
test "${#selectors[@]}" -gt 0
base=(-project Celluloid.xcodeproj -scheme Celluloid -configuration Debug
      -destination "platform=iOS Simulator,id=$device" -derivedDataPath "$derived"
      CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO COMPILER_INDEX_STORE_ENABLE=NO)
forwarded=("TEST_RUNNER_CELLULOID_EXPECTED_SOURCE_SHA=$GITHUB_SHA"
           "TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE=" "TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA=")
if [[ "$phase" = pristine || "$phase" = preservation ]]; then
  fixture_payload=$(python3 Scripts/swiftui_photos_gate.py payload "$out")
  forwarded+=("TEST_RUNNER_CELLULOID_FIXTURE_MANIFEST_JSON=$fixture_payload")
fi
if [[ "$phase" = preservation ]]; then
  # Only this single invocation may create/edit its verified test-owned assets.
  forwarded=("TEST_RUNNER_CELLULOID_EXPECTED_SOURCE_SHA=$GITHUB_SHA"
             "TEST_RUNNER_CELLULOID_FIXTURE_MANIFEST_JSON=$fixture_payload"
             "TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE=1"
             "TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA=$GITHUB_SHA")
fi
phase_seconds=$(python3 Scripts/swiftui_photos_gate.py budget "$phase" "$owner" seconds)
set +e
env "${forwarded[@]}" python3 Scripts/run_bounded.py --seconds "$phase_seconds" --label "swiftui-photos-$phase" \
  xcodebuild "${base[@]}" -resultBundlePath "$out/$phase.xcresult" \
  -parallel-testing-enabled NO -collect-test-diagnostics never "${selectors[@]}" \
  test-without-building 2>&1 | tee "$out/$phase.log"
statuses=("${PIPESTATUS[@]}")
native_status=0
for value in "${statuses[@]}"; do
  if [[ "$native_status" -eq 0 && "$value" -ne 0 ]]; then native_status=$value; fi
done
set -e
printf '%s\n' "${statuses[@]}" > "$out/$phase-pipeline-exit-codes.txt"
summary_status=0
python3 Scripts/run_bounded.py --seconds 45 --label "swiftui-photos-$phase-summary" \
  /bin/bash -c 'exec xcrun xcresulttool get test-results summary --path "$1" > "$2"' _ \
  "$out/$phase.xcresult" "$out/$phase-summary.json" > "$out/$phase-summary-collection.log" 2>&1 || summary_status=$?
if [[ "$native_status" -ne 0 ]]; then exit "$native_status"; fi
if [[ "$summary_status" -ne 0 ]]; then exit "$summary_status"; fi
python3 Scripts/swiftui_photos_gate.py verify "$phase" "$out"
