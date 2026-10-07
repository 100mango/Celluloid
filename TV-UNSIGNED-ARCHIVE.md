# Celluloid TV unsigned Release archive candidate

Local preparation only. No remote publication, native execution, signing, export, Apple upload or UI rerun is authorized by this document.

Parent: da446a1bb869baf95499c2a057bb627d3d73d3b0
Parent tree: 6325ef9470ffbb03dce3ebd82b104a0b2e1eb82c
Proposed branch: codex/tv-unsigned-archive

One Release archive uses CelluloidNative.xcodeproj / CelluloidTV, generic tvOS, arm64, version 1.1 (2), unsigned, dwarf-with-dsym. PNG compression is explicitly disabled so copied rendering resources must remain byte-identical to their reviewed source. Both localized string tables are compared semantically. Package resources are fully enumerated from the pinned source.

All 905 existing tracked files, including shipping Swift, package resources, Info plists, native project/scheme, the complete asset catalog and common icon materializer remain byte-identical to the parent. A tvOS-only version of the existing hash-bound native icon materializer derives the eight existing TV PNG slots from the original 1024px brand, with the original fit and resampling rules. Existing Small1x/2x, Large1x, TopShelf1x and TopShelfWide1x catalog roles are verified after compilation. Top-shelf2x additions are deferred because they have not been shown to be necessary for this archive. No app screenshots are generated.

Observer: one xcodebuild archive only, no simulator/UI or archive retry; 600-second command maximum with 20-second owned cleanup reserve. Full stdout+stderr capture is bounded at 16MiB. Hashes and error scanning cover all captured bytes; the report retains labelled prefix/tail excerpts up to 512KiB. A stopped producer never claims a complete log. Final report maximum 2MiB; evidence upload is this JSON only, for one day. No application binary or archive is uploaded.

Source identity is checked before and after: exact base tree, sole parent, branch/event/attempt/job/workflow/source SHA, clean checkout, exact path delta, product/resource hashes. Build-derived ignored PNGs are independently hash/dimension checked before and after archive.

Qualification will require exact app resource inventory, compiled icon roles/scales for the unchanged five size/scale slots, app/privacy/localized metadata, tvOS device arm64 Mach-O with floor17 / SDK27, no debug hooks, no signatures or embedded test/extra code, matching executable and DWARF UUID, and stable archive file identities. Native archive success is not established by portable tests. Existing UI evidence is reused from runs37584551671 and37596611181; physical hardware, oldest OS runtime, actual OS text-size setting propagation, distribution signing and Store processing remain separate.
