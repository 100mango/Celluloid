# Manual cloud release controller

This controller is installed disabled: `release-manifest.json` contains `enabled: false` and an empty allowlist. Default workflow mode is `dry-run`. No signing or upload can pass until explicit reviewed release evidence and approved secure setup are supplied.

## Boundaries

- Manual dispatch on this repository's `master` only; protected environment `appstore-release`
- A reviewed full controller commit is bound by `TRUSTED_CONTROLLER_SHA`; `SIGNING_ENABLED` must explicitly be `true`
- App source must be an exact approved commit of Celluloid, QRCatcher or ColorPicker, verified against successful same-repository CI and reviewed workflow bytes
- Qualifying app CI uses exact-head push/manual runs on `codex/ios-modernization`, with unchanged-source provenance; pull-request merge evidence is rejected
- App archive builds run without signing credentials on a separate runner; a fresh protected runner performs export and optional build upload
- All jobs require standard `xcode-27`, Xcode 27.0 build 27A266a and the iPhoneOS27.0 SDK
- Signing refuses non-GitHub-hosted/non-macOS environments. Cleanup removes only its newly created marked temporary workspace; it never deletes HOME provisioning-profile directories. Remaining runner caches disappear with disposal of the ephemeral hosted VM
- `export` never uploads; `upload` requires separate explicit build-upload approval. Neither mode submits App Review or publishes an app

## Protected environment fields

- Secret: `ASC_PRIVATE_KEY_P8`, entered by the owner through the secure GitHub environment-secret UI
- Variables: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `APPLE_TEAM_ID`, `TRUSTED_CONTROLLER_SHA`, `SIGNING_ENABLED`

The credential policy is a dedicated `iOS Release CI` **Admin TEAM key with all-app scope**. It is not app-scoped. Creation, persistent storage, use and acknowledgement of that scope require explicit owner approval. Manifest key metadata must match the protected variables. Never store the private key in the repository, logs, artifacts, cache, issue text or workflow inputs. Examples deliberately contain no actual key/team identifiers and no granted approvals.

Environment protection must require owner review, exact `master` branch policy and restricted bypass. For a sole-owner account, do not disable the owner's ability to approve their own manual run. Review every workflow eligible to use the environment; branch policy alone does not bind a single workflow path.

## Evidence and resource limits

Each allowlist entry requires exact source/tree/workflow hashes, successful CI run/attempt/jobs/required steps, fixed toolchain evidence, app/version identity, approved privacy basics, exact entitlements and observed framework inventory. App Review questionnaires and rights decisions are separate later gates, not prerequisites for an export-only integration probe. Optional build upload needs its own metadata review and approval reference. Export requires an approved HTTPS privacy-policy URL and `privacy_review_reference` (an existing combined `privacy_support_review_reference` also qualifies). It does not require a Support URL or support-page review and does not submit App Store metadata. Preserve known legacy `support_url` values exactly, including HTTP values; do not rewrite them to make an export probe pass. Upload retains the existing HTTPS Support URL and combined privacy/support-review gates, plus its separate build-upload review and approval.

The main app's `UIDeviceFamily` must preserve shipped scope exactly: Celluloid `[1, 2]`, QRCatcher `[1]`, and ColorPicker/TouchColor `[1]`. Framework and extension plists are not assumed to contain this app-only field.

Celluloid requires first-party CelluloidKit and exact observed metadata for the synthesized SnapKit package framework. SnapKit is pinned to its official repository, version 5.7.1, revision `2842e6e84e82eb9a8dac0100ca90d9444b0307f4`; both tracked lockfiles are checked. Unknown framework metadata blocks release. No wildcard IDs or app-version defaults are accepted for frameworks.

Unsigned artifacts require explicit quota approval, at most 100 MiB compressed, 512 MiB expanded, 10,000 members and one-day retention. No paid overage is authorized. Keys, profiles, signed IPAs and raw signing logs are never uploaded as GitHub artifacts. Archive source checks reject tracked changes and ordinary/ignored untracked files; build outputs and package clones remain outside the checkout.

The complete tar size/member/path/type preflight runs both before artifact upload and before signer extraction. Provenance requests authenticate only to Celluloid; the fixed public QRCatcher/ColorPicker repositories use unauthenticated GETs. API failures and rate limits stop validation without credential fallback.

Cloud export of an unsigned archive remains an integration test. `-allowProvisioningUpdates` is write-capable and may manage profiles/certificates; its broad effects require explicit scope. No automatic certificate fallback, revocation, device registration or role escalation is implemented. Failures emit only reviewed fixed diagnostic categories and a finite error-code whitelist before private logs are deleted. Unknown errors stay redacted and stop for a scoped diagnostic plan. An upload error requires reconciliation before retry.

## Local validation

Run `python3 -m unittest discover -s .github/release-controller/tests -v` with Python and PyYAML available, plus `bash -n` on both shell scripts. The controller's runtime Python logic uses the standard library; PyYAML is used only by the static workflow test. Synthetic fixtures are not production release evidence.

Official guidance: [Apple cloud signing](https://developer.apple.com/videos/play/wwdc2021/10204/), [cloud-managed certificates](https://developer.apple.com/help/account/certificates/cloud-managed-certificates/), [GitHub workflow security](https://docs.github.com/en/actions/reference/security/secure-use)
