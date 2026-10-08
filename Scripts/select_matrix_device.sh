#!/bin/bash
# Keep this compatible with the system Bash shipped on the macOS runner.
set -euo pipefail
if [[ $# -ne 1 ]]; then
  printf '%s\n' 'Expected exactly one matrix device name' >&2
  exit 64
fi
case "$1" in
  'iPhone SE (3rd generation)')
    exec python3 Scripts/select_test_devices.py "$1"
    ;;
  'iPhone 18 Pro Max'|'iPad mini (A17 Pro)'|'iPad Pro 13-inch (M5)')
    exec python3 Scripts/select_test_devices.py "$1" --pre-provisioned
    ;;
  *)
    printf '%s\n' 'Unsupported matrix device name' >&2
    exit 64
    ;;
esac
