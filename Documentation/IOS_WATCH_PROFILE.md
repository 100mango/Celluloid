# Celluloid: later iOS + Watch package preparation

This additive projection starts at the qualified original-iOS commit baea0ae3b3c9d9911937e9dd95a9fba6cbdf9d73. All 907 existing repository files, the original project, signer and current review submission stay unchanged. Nothing in this candidate replaces or withdraws the submitted iOS build.

## Minimum shipping integration

Run `python3 Scripts/generate_ios_watch_project.py` to reproduce Celluloid-iOS-Watch.xcodeproj and two Swift input projections. SHA-256-pinned current AppDelegate and EntranceViewController inputs receive only the historical iPhone-only activation, Watch Photos button and navigation action. The current offline privacy page and all unrelated original iOS fixes are preserved byte-for-byte. The iPad retains the privacy-only footer and no companion activation.

The real shipping parent links the six existing Platforms/Companion Swift files plus existing CelluloidDomain and CelluloidRendering products. Existing request/hash/size validation, transaction/cancellation, recovery and explicit Photos save remain unchanged. CelluloidPhoneCompanion is a separate validation harness and is neither substituted for the parent nor admitted to the archive.

The new project restores one exact cross-project CelluloidNative.xcodeproj → CelluloidWatch dependency and Embed Watch Content phase. The original CelluloidKit framework, Photos extension and pinned SnapKit product remain present. Watch remains a dependent companion: WKCompanionAppBundleIdentifier=Mango.Celluloid and WKRunsIndependentlyOfCompanionApp stays absent. Parent and Watch use 1.1 (2), phone floor 15 and Watch floor 9. These current values qualify only an unsigned source observation; distribution needs a separately frozen unused successor, tentatively 1.2 (3).

## Bounded native candidate

The new ios-watch-unsigned-archive.yml workflow has one fixed push branch, one standard xcode-27 job and a 20-minute outer cap. The exact non-quiet generic iOS device archive command has signing disabled, no architecture override, and DEBUG_INFORMATION_FORMAT=dwarf-with-dsym for all five code products. It does not boot simulators, run UI tests, export, sign, call a portal or submit a build. It has no native retry path.

The capture and owned-group cleanup helpers are exact copies of the successfully qualified QR archive collector. Full archive capture is capped at 16 MiB; at most 512 KiB is retained after a complete error scan, with separate full-capture and retained-log hashes. The original monotonic clock bounds preparation, the single archive, proof, report and upload retention. Evidence retention is not App Store upload.

Policy fixes five code bundles: the real phone app, its nested CelluloidWatch app, CelluloidKit, CelluloidPhotoExtension and the existing exact SnapKit framework. Every product has platform/slices/minimum-OS, actual Mach-O UUID and matching dSYM checks. Runtime dependencies and framework install names are exact. SnapKit's SDK load-command value is pinned to the previously observed 15.0 in baea's real archive; other products use SDK 27.0. The existing exact 5.7.1/revision pin is copied to the new project, Xcode is restricted to the resolved version, and the actual checkout revision/cleanliness is checked after the build.

Resources are product-specific. Parent and Watch compiled icons are checked; the Watch icon is only an exact copy of the existing hash-pinned original brand. Existing original assets, storyboards, Photos strings and offline privacy localizations are retained. Three SnapKit privacy bundles plus three explicitly located local-package resource bundles are checked. The current phone and Watch do not have standalone PrivacyInfo.xcprivacy resources; the verifier records this source-matching absence and does not infer Store privacy approval. Localizations, notices and every local package resource are bound to source. No arbitrary framework, extension, resource bundle, executable, profile, signing material, test/harness, extra app or symlink is allowed.

The actual embedded Watch is compared against its exact producer under this invocation's fresh DerivedData. Only an exact copy or the already witnessed deterministic Release strip transform can pass. The full source tree is bound before and after, including original files and the fixed additive projection. Existing original regression tests remain for their unchanged project; none of their runtime results is relabelled as the new shipping-companion pass.

## Evidence and remaining scope

The earlier 52bf source is checked by fresh GitHub commit/tree/blob reads. The Watch production closure, its reachable project objects and the six companion sources match the candidate exactly. This preserves the earlier actual passed Watch cases, without converting the outstanding narrow 40mm unavailable-companion/cancel/relaunch/delete/privacy case into a pass. The current task does not rerun it.

Shipping iPhone companion entry/results, request validation/cancel/no silent Photos save and iPad entry absence still need their separate runtime evidence. Physical file delivery and real Watch photo selection are not established by a portable test or unsigned archive. Current review submissions remain intact; Watch screenshots, final successor version/build and exact signer/profile authorization remain separate. Independent review and a root exact-tree GO are mandatory before publication or one native run.
