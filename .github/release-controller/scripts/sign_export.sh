#!/bin/bash
# Manual gated signing: requires approved scope, verified setup and exact release evidence.
# Do not source scripts from app-source or extracted products in this runner.
set +x
set -euo pipefail
: "${CONTROLLER_DIR:?}" "${RELEASE_ID:?}" "${RELEASE_MODE:?}" "${ARCHIVE_PATH:?}" "${RUNNER_TEMP:?}"
: "${ASC_PRIVATE_KEY_P8:?Missing protected environment secret}" "${ASC_KEY_ID:?}" "${ASC_ISSUER_ID:?}" "${APPLE_TEAM_ID:?}"
: "${SIGNING_ENABLED:?}" "${TRUSTED_CONTROLLER_SHA:?}" "${GITHUB_WORKFLOW_SHA:?}" "${GITHUB_SHA:?}" "${GITHUB_REF:?}"
test "$SIGNING_ENABLED" = true
test "$GITHUB_REF" = refs/heads/master
test "$GITHUB_WORKFLOW_SHA" = "$TRUSTED_CONTROLLER_SHA"
test "$GITHUB_SHA" = "$TRUSTED_CONTROLLER_SHA"
case "$RELEASE_MODE" in export|upload) ;; *) echo 'Signing mode not explicitly selected' >&2; exit 1 ;; esac
python3 "$CONTROLLER_DIR/scripts/guard.py" validate --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE"
python3 "$CONTROLLER_DIR/scripts/guard.py" verify-credential-metadata --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE"
export DEVELOPER_DIR=/Applications/Xcode_27.app/Contents/Developer
xcodebuild -version
xcodebuild -version | grep -E '^Xcode 27(\.0)?$'
xcodebuild -version | grep -F '27A266a'
# Scope credentials to this script and descendants; never echo or pass key text
# in command arguments. Raw Apple diagnostics stay private; a closed-set
# classifier emits only fixed categories/codes before the raw log is deleted.
umask 077
PRIVATE_ROOT=$(mktemp -d "$RUNNER_TEMP/cloud-signing.XXXXXXXX")
cleanup() {
  set +x
  unset ASC_PRIVATE_KEY_P8
  if [ -n "${PRIVATE_ROOT:-}" ] && [[ "$PRIVATE_ROOT" == "$RUNNER_TEMP"/cloud-signing.* ]]; then rm -rf "$PRIVATE_ROOT"; fi
  rm -rf "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
export PRIVATE_ROOT
# No key content is ever read by an agent. The owner stores the original .p8
# directly in GitHub's environment-secret form after separate approval.
python3 - <<'PY'
import os,re,pathlib
assert re.fullmatch(r'[A-Z0-9]{10}',os.environ['ASC_KEY_ID']), 'Invalid key ID'
assert re.fullmatch(r'[0-9a-fA-F-]{36}',os.environ['ASC_ISSUER_ID']), 'Invalid issuer UUID'
assert re.fullmatch(r'[A-Z0-9]{10}',os.environ['APPLE_TEAM_ID']), 'Invalid team ID'
s=os.environ['ASC_PRIVATE_KEY_P8']
assert s.startswith('-----BEGIN PRIVATE KEY-----\n') and '-----END PRIVATE KEY-----' in s, 'Expected original multiline PKCS8 key'
p=pathlib.Path(os.environ['PRIVATE_ROOT'])/('AuthKey_'+os.environ['ASC_KEY_ID']+'.p8')
with p.open('x') as f: f.write(s if s.endswith('\n') else s+'\n')
p.chmod(0o600)
PY
unset ASC_PRIVATE_KEY_P8
KEY_PATH="$PRIVATE_ROOT/AuthKey_${ASC_KEY_ID}.p8"
python3 "$CONTROLLER_DIR/scripts/guard.py" export-options --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --team "$APPLE_TEAM_ID" --output "$PRIVATE_ROOT/ExportOptions.plist"
# This is a WRITE-CAPABLE integration probe. -allowProvisioningUpdates is broad:
# Apple may manage profiles/certificates. No narrower switch is promised.
# Never add -allowProvisioningDeviceRegistration, explicit create/revoke calls,
# or development-certificate fallbacks without a separate owner decision.
if ! xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" \
  -exportPath "$PRIVATE_ROOT/export" -exportOptionsPlist "$PRIVATE_ROOT/ExportOptions.plist" \
  -authenticationKeyPath "$KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID" -allowProvisioningUpdates \
  >"$PRIVATE_ROOT/export.log" 2>&1; then
  python3 "$CONTROLLER_DIR/scripts/safe_diagnostics.py" --phase export --log "$PRIVATE_ROOT/export.log"
  echo 'Cloud export failed. No upload attempted. Stop for a scoped, redacted diagnosis; do not broaden permissions or generate a developer certificate.' >&2
  exit 1
fi
IPA=$(find "$PRIVATE_ROOT/export" -maxdepth 1 -name '*.ipa' -type f)
test "$(printf '%s\n' "$IPA" | grep -c .)" = 1
test -f "$IPA"
python3 "$CONTROLLER_DIR/scripts/guard.py" inspect-ipa --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --team "$APPLE_TEAM_ID" --path "$IPA" --destination "$PRIVATE_ROOT/ipa"
IPA_SHA=$(shasum -a 256 "$IPA" | cut -d ' ' -f 1)
printf 'Verified exported IPA SHA-256: %s\n' "$IPA_SHA"
if [ "$RELEASE_MODE" = upload ]; then
  # altool must be checked on the installed Xcode 27 runner before credentials.
  # Its current help must support API_PRIVATE_KEYS_DIR, --apiKey/--apiIssuer,
  # and --upload-app. Otherwise STOP and review an official upload alternative.
  export API_PRIVATE_KEYS_DIR="$PRIVATE_ROOT"
  if ! xcrun altool --upload-app --type ios --file "$IPA" --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" >"$PRIVATE_ROOT/upload.log" 2>&1; then
    python3 "$CONTROLLER_DIR/scripts/safe_diagnostics.py" --phase upload --log "$PRIVATE_ROOT/upload.log"
    echo 'Build upload outcome is unverified. Reconcile the existing app/build in App Store Connect before any retry.' >&2; exit 1
  fi
  echo 'App Store Connect build upload command succeeded; processing/acceptance must still be verified. No App Review submission or release performed.'
else
  echo 'Cloud export/signature checks passed; no build uploaded. IPA and signing material are deleted during cleanup.'
fi
