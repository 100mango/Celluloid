#!/bin/bash
# Reuse this Mac job's qualified sandbox app/UI bundle. No rebuild, account or settings change.
set -euo pipefail
python3 Scripts/mac_photos_host_gate.py budget-before-host
status=0
TEST_RUNNER_CELLULOID_MAC_PHOTOS_HOST_PREREQUISITE=1 \
TEST_RUNNER_CELLULOID_MAC_HOST_CONTEXT="$RUNNER_TEMP/mac-host-context.json" \
  python3 Scripts/run_bounded.py --seconds 720 --label actual-mac-photos-host-prerequisite \
  xcodebuild -project CelluloidNative.xcodeproj -scheme CelluloidMacUI \
  -destination 'platform=macOS' -derivedDataPath "$RUNNER_TEMP/celluloid-sandbox" \
  -resultBundlePath "$RUNNER_TEMP/MacPhotosHost.xcresult" \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  -maximum-test-execution-time-allowance 660 \
  -only-testing:CelluloidMacUITests/MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos \
  CODE_SIGNING_ALLOWED=NO CELLULOID_EXPECT_SANDBOX=YES test-without-building \
  2>&1 | tee "$RUNNER_TEMP/mac-host-test.log" || status=$?
python3 -c 'import os,subprocess; from pathlib import Path; p=Path(os.environ["RUNNER_TEMP"]); subprocess.run(["xcrun","xcresulttool","get","test-results","summary","--path",str(p/"MacPhotosHost.xcresult")],stdout=open(p/"mac-host-summary.json","w"),check=True,timeout=30)' || status=$?
python3 Scripts/mac_photos_host_gate.py transport || status=$?
python3 Scripts/mac_photos_host_gate.py product-after || status=$?
python3 Scripts/mac_photos_host_gate.py source-after || status=$?
exit "$status"
