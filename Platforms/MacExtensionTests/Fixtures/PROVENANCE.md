# Photos 1.0 compatibility fixtures

No archive here is described as a recovered customer photo or a recovered 2016 user archive.

The registered Mac test bundle reuses the source-controlled UIKit-produced bytes at
`Packages/CelluloidCore/Tests/CelluloidDomainTests/Fixtures/`:

- `legacy-points.base64`: SHA-256 `81708fde38d83189bffdb76ca17cc14e3afaf573f729d7ede390f57d286f8e92`
- `reference-canvas.base64`: SHA-256 `10ec7c14e309de8cd100206a082fe2c5222890edec9a57c4b981947c0d2d2d62`

Their JSON sidecars record exact literal fields, runtime and producer hashes. They were actually archived by the original UIKit 1.0 model on iOS 27. The first reproduces the historical dictionary schema; the second includes the later additive canvas field. Neither is manufactured by the new Mac serializer. Test bundle resource references point to these exact files rather than maintaining a drifting duplicate.

## Historical source verification

The historical Swift 3 writer at commit `c4bed2622c165574ec795f861c3a2a7aff5931da`, `CelluloidKit/Model/AdjustmentData.swift`, archives `self.toJSON()` via `NSKeyedArchiver`. Its JSON encoder writes only `bubbles`, `stickers`, and `filterType`; it declares no reference canvas. The corresponding BubbleModel and StickerModel encode `center`, `bounds`, and full affine `transform` as NSValue. Thus absence of canvas metadata is verified from the actual historical writer, not inferred only from a new fixture.

The new native tests retain all literal absolute values but reject editable rendering/writing of a layered archive without its reference canvas. Its current Photos placeholder remains visible, while Done returns a no-change output and Cancel stays silent. This is read-only compatibility, not editable parity for historical absolute-only archives.

## Manufactured writer qualification

`MacPhotoAdjustmentTests.testNewManufacturedValuesKeepUIKitTypesAndAllFields` creates new geometry values on macOS, independently asserts the fields, and emits one `MAC_LAYER_ADJUSTMENT_FIXTURE` JSON record with the adjustment archive, a synthetic 480×640 PNG source and actual native rendered PNG, each with SHA-256. The record must be extracted from an admitted run, source-bound by the parent receipt, delivered as `Documents/mac-layer-fixture.json` to a disposable UIKit validation simulator, and passed through `MacPhotosManufacturedAdjustmentTests`.

That test uses the unchanged UIKit reader and `BaseEditPhotoController.outputImage`, asserts literal affine fields before rendering and requires maximum channel difference ≤2 in an sRGB bitmap. No raw PNG is claimed to exist before that Mac run. A missing input is an explicit unexecuted gate, not equivalence. Any font, text placement, color or geometry failure must be fixed, not hidden by weakening the pixel oracle.

## Observed failure and component diagnosis

The admitted `48502442` run produced these verified bytes:

- Archive: `e6eabfb1a0b20951ddfe62f6648fdf025ef29689b309db5431295279a19814ac`
- Source PNG: `a6eac0f497a5955af962fd6d2fe0fc7b7aff514aa75293285a520d67bd729cce`
- Native PNG: `0b15bc4c2c704e0433c37afb65da4ac243ea64902c837ef592584e7874af4d97`

The archive retained the expected affine fields; the independent full UIKit compositor failed at maximum channel difference 243 on compact iPhone and both iPads. The input PNG is upright 480×640 opaque sRGB with the solid pixel `(51,153,204,255)` throughout. Its orientation cannot explain this specific failure. The native `say1.png` is the exact 800×1000 UIKit @3x asset; UIKit also ships a distinct 533×666 @2x rendition. The original BubbleLabel uses rounded `UIImageView.imageRect` coordinates, whereas the previous native text area used fractional artwork coordinates. That source-proved text-area defect is corrected, but this is not a claim that the remaining raster difference is solved.

New manufactured records add four optional historical-schema-compatible diagnostic components (`filtered-base`, `bubble-artwork`, `sticker-artwork`, `all-artwork`), each fixed at 480×640 and independently SHA-256-bound. A record that includes components must include exactly all four. The existing 500,000-byte total bound, per-PNG bound, source commit and artifact-manifest checks remain mandatory. The original full fixture is still the acceptance oracle; components are additional strict tests, never replacements. Production layered Photos output remains blocked until real native-to-UIKit pixel proof is obtained.

The `d9a9fe00` 2x UIKit run retained native archive `e90f8e63d65c2228aafc93f3796b2c7d8085c3be6f910a39ea3e5cb697592918`, the same original source PNG above, and native full PNG `e5d2f5c145be50e01079db3932077edd719bef310b3fb1e5c06175c1d7dd80d5`. Its full UIKit oracle PNG is `022e2356f64946d66e0fb02c3a2a78b659c1d07f9fb0f0a5828bc20026a97aa3`. Base/sticker components were exactly equal; bubble artwork differed by at most 38 and full/text by 237. These failed independent outputs remain evidence, not replaceable golden values.

The Mac-only candidate adds the original ten UIKit @2x bubble PNGs alongside the untouched canonical @3x assets. `Resources/legacy-bubble-resource-provenance.json` in CelluloidRendering lists every original path and SHA-256; structural validation checks their bytes. The native fallback-font/line metadata and small text-backing attachment are diagnostics. Neither selecting the matching 2x resources nor a favorable 2x run proves equality to an original 3x UIKit output.
