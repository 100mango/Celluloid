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
