#!/bin/bash
# Exercise the actual selector with a stub: no simulator creation or Python work.
set -euo pipefail
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
cat > "$fixture/python3" <<'STUB'
#!/bin/bash
set -euo pipefail
separator=''
for value in "$@"; do
  printf '%s%s' "$separator" "$value"
  separator='|'
done
printf '\n'
STUB
chmod +x "$fixture/python3"
/bin/bash --version | head -1
for device in 'iPhone SE (3rd generation)' 'iPhone 18 Pro Max' 'iPad mini (A17 Pro)' 'iPad Pro 13-inch (M5)'; do
  actual=$(PATH="$fixture:$PATH" /bin/bash Scripts/select_matrix_device.sh "$device")
  expected="Scripts/select_test_devices.py|$device"
  if [[ "$device" != 'iPhone SE (3rd generation)' ]]; then expected="$expected|--pre-provisioned"; fi
  if [[ "$actual" != "$expected" ]]; then
    printf 'DEVICE_SELECTION_ARGUMENT_MISMATCH expected=%s actual=%s\n' "$expected" "$actual" >&2
    exit 1
  fi
  printf 'DEVICE_SELECTION_SHELL_PASS %s\n' "$actual"
done
if PATH="$fixture:$PATH" /bin/bash Scripts/select_matrix_device.sh 'unsupported fixture device'; then
  printf '%s\n' 'Unsupported device was incorrectly accepted' >&2
  exit 1
fi
if PATH="$fixture:$PATH" /bin/bash Scripts/select_matrix_device.sh; then
  printf '%s\n' 'Missing device was incorrectly accepted' >&2
  exit 1
fi
printf '%s\n' 'DEVICE_SELECTION_PREFLIGHT_PASS four supported branches and two invalid-input cases'
