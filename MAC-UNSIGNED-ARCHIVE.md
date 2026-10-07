# Celluloid fixed unsigned native Mac archive proof

One Xcode 27.0 archive, Release macOS 13, arm64 + x86_64, with CODE_SIGNING_ALLOWED=NO and explicit dwarf-with-dsym. No launch, UI tests, signing, notarization, export, Apple account, or binary upload. The additive local cohort preserves all 906 b8b6aa890df8b4f16f5627c965d01585a21fe97b source files; exact source hashing occurs before and after.

The archive verifier inventories complete bounded files before semantic checks and retains all five archive/app/extension/dSYM plists. It checks both products, compiled binaries and matching universal UUIDs, exact EN/ZH strings/license/privacy text, linked package resources, committed icon provenance and compiled AppIcon renditions. Unsigned entitlements are observed separately from source declarations. No sandbox/signing/Store claim follows.

Native Mac contains no PrivacyInfo.xcprivacy in this source. Required Reason API platform scope and absence of direct listed Release uses were independently reviewed. Privacy text is not a manifest. Retain the actual archive manifest inventory and linked-symbol observations; Store validation remains separate.

Historical standalone UI raw failures remain 2 pass/7 fail/1 skip; same-source sandbox is 5 pass/0 fail/5 skip. Accepted scoped functional disposition does not claim a new b8 runtime, universal accessibility, or extension functional equivalence.

Only bounded report.json is retained, for one day. The app, archive, dSYMs, IPA and PKG remain on the ephemeral runner. The proof report remains upload_qualified=false; final workflow log receipt separately qualifies retention. A local preparation is not execution authorization.
