#!/bin/bash
# No signing credentials may be present in this job. Invoke with bash.
set -euo pipefail
set +x
: "${APP_SOURCE:?}" "${RELEASE_JSON:?}" "${OUTPUT_DIR:?}" "${CONTROLLER_DIR:?}"
if [ -n "${ASC_PRIVATE_KEY_P8:-}" ]; then echo 'Unexpected signing secret in build job' >&2; exit 1; fi
export DEVELOPER_DIR=/Applications/Xcode_27.app/Contents/Developer
sw_vers
xcodebuild -version
xcodebuild -showsdks
xcodebuild -version | grep -E '^Xcode 27(\.0)?$'
xcodebuild -version | grep -F '27A266a'
xcodebuild -showsdks | grep -F 'iphoneos27.0'
APP=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["app"])' "$RELEASE_JSON")
SHA=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$RELEASE_JSON")
case "$APP" in
  Celluloid) PROJECT=Celluloid.xcodeproj; SCHEME=Celluloid ;;
  QRCatcher) PROJECT=QRCatcher.xcodeproj; SCHEME=QRCatcher ;;
  ColorPicker) PROJECT=TouchColor.xcodeproj; SCHEME=TouchColor ;;
  *) echo 'App not allowed' >&2; exit 1 ;;
esac
cd "$APP_SOURCE"
python3 "$CONTROLLER_DIR/scripts/guard.py" verify-source-clean --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --path "$APP_SOURCE"
python3 "$CONTROLLER_DIR/scripts/guard.py" verify-source-dependencies --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --path "$APP_SOURCE"
# Do not invoke dependency-install scripts, generated shell supplied by inputs,
# or scripts from an artifact. Final checked-in project must be the tested one.
mkdir -p "$OUTPUT_DIR"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$OUTPUT_DIR/Release.xcarchive" \
  -derivedDataPath "$OUTPUT_DIR/DerivedData" -clonedSourcePackagesDirPath "$OUTPUT_DIR/SourcePackages" -disableAutomaticPackageResolution \
  archive CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=''
python3 "$CONTROLLER_DIR/scripts/guard.py" verify-source-clean --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --path "$APP_SOURCE"
python3 "$CONTROLLER_DIR/scripts/guard.py" inspect-archive \
  --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" \
  --mode "$RELEASE_MODE" --path "$OUTPUT_DIR/Release.xcarchive"
# Archive bridge must contain NO profiles, certificates, keys or signing data.
if find "$OUTPUT_DIR/Release.xcarchive" \( -name '*.mobileprovision' -o -name '*.p8' -o -name '*.p12' -o -name '*.pem' -o -name '*.cer' -o -name '_CodeSignature' \) -print | grep .; then
  echo 'Unexpected signing material in unsigned archive' >&2; exit 1
fi
if find "$OUTPUT_DIR/Release.xcarchive" -type l -print | grep .; then
  echo 'Archive symlinks require separate reviewed handling' >&2; exit 1
fi
COPYFILE_DISABLE=1 tar -czf "$OUTPUT_DIR/unsigned-archive.tar.gz" -C "$OUTPUT_DIR" Release.xcarchive
# Enforce compressed/expanded size, member and path limits before upload.
python3 "$CONTROLLER_DIR/scripts/guard.py" check-unsigned-artifact --manifest "$CONTROLLER_DIR/release-manifest.json" --release "$RELEASE_ID" --mode "$RELEASE_MODE" --path "$OUTPUT_DIR/unsigned-archive.tar.gz"
DIGEST=$(shasum -a 256 "$OUTPUT_DIR/unsigned-archive.tar.gz" | cut -d ' ' -f 1)
echo "archive_sha256=$DIGEST" >> "$GITHUB_OUTPUT"
