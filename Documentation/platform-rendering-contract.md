# Versioned platform rendering qualification

This is a replacement fixture-specific acceptance contract for the contradictory
universal Mac-to-UIKit pixel comparison. It is not a claim that the candidate has
passed Apple execution, Photos-host preservation, or all-platform acceptance.
The layered Photos safety guard and disabled final archive remain in force.

## Immutable independent controls

`Scripts/fixtures/platform-rendering-controls.json` retains original UIKit full,
bubble-artwork and all-artwork PNGs at genuine2x and3x, plus their exact archive
and source image inputs. These bytes came from public52bf7a9, run37220588828,
artifact11311410428, with recorded source tree, original production fingerprint,
models, iOS27.0 build24A434 and arm64 provenance. The full PNG hashes also match
historical9c. The controls are never regenerated from candidate output.

The packet is staged only beside the synthetic adjustment in an owned disposable
app Documents directory. No shipping UIKit source, resource bundle or project
changes are necessary. Both staging and XCTest verify the exact packet SHA.

## Separate oracles

- Literal decoded archive/content/geometry checks remain, including the original
  text, spaces, reference canvas and full affine components.
- Each current UIKit output must match the immutable control for its own runtime
  and display-scale profile within the original2-channel bound. Unknown profiles
  or runtime builds are not accepted. Additional device models at a known scale
  must still pass their own actual execution against that fixed control.
- Filtered base and sticker components must match each other and the independently
  witnessed original component bytes exactly in normalized sRGB RGBA.
- Artwork placement uses only the union of fixed2x/3x control gradients above2,
  expanded by one output pixel. Outside this fixed band, every RGBA value is exact.
  Every candidate/control gradient edge must have a counterpart within one pixel.
  Inside the band, each channel must stay within the controls' one-pixel-neighbor
  envelope plus the existing2-level quantization bound. Opacity remains255.
  No candidate-derived mask, fitted translation, recoloring or broad image tolerance
  is permitted. Recoloring, transparency and removed-artwork image mutations must
  be rejected by this same oracle.
- Native text requires an actual text-bearing `MacPhotoRenderer.render` result
  against an independent AppKit per-line glyph and literal affine oracle. Its
  source and final PNG hashes must match the separately manufactured fixture.
  Natural baseline, original whitespace spans, intrinsic backing mapping,
  multilingual same-path clipping and live production-path mutation tests remain
  required. Expected pixels do not call candidate text helpers.

The old full/component maximum differences and diagnostic images are still
recorded. Historical failures remain historical failures. A new contract can pass
while `strict_pixel_passed` remains false; these are deliberately separate facts.

## Execution and evidence

The live verifier requires schema `Celluloid.PlatformRendering.1`, a complete
`Celluloid.NativeTextContract.1` producer record, both actually executed consumers,
exact source/binary/fixture/control/runtime bindings, one consistent finalized
XCTest outcome, finite consistent timing and verified owned-device cleanup.
Every current consumer must pass; the later phone and full UIKit routes also read
their actual finalized xcresult summary and bind its owned device/model,27.0 build24A434
and arm64 architecture. Complete raw testcase/suite/terminal/error accounting must
agree with that summary. A consistently failed unrelated case retains a separately
passed renderer-consumer result, but the enclosing aggregate and CLI step stay red.
A Passed summary contradicted by any failed raw record is rejected, not excused.
Known-scale additional approved iPad models retain separate
actual execution checks. The accepted summary is mandatory before optional evidence.
Every completed early consumer also receives one bounded post-test installed-app
readback, because Xcode can relocate the app during test-without-building. Current
product identity/executable must match the built/staged bytes, and a failed readback
preserves its primary test diagnosis while always cleaning up and withholding acceptance.
 the former exception for known failed pixel
assertions is used only by explicit historical parser regression tests, never by
the live CLI. Unrelated assertions, failures, crashes, timeouts, unknown outcomes,
missing records and unverified cleanup reject continuation.

Native and consumer records must occur inside their named executed test cases.
Required source/producer receipts and raw native text observation are retained
before optional logs/images. At most the two named native oracle failure images
are added to bounded Mac evidence; existing aggregate exporter and workflow byte
limits remain. Release packaging separately checks the actual embedded extension
binary for absence of Debug-only text fault hooks.

Passing this fixed fixture does not qualify arbitrary typography, physical-device
transport or actual Photos save/reopen/cancel/Revert and resource preservation.
Those remain separate required gates before removing the protection or release.

## Complete archive graph identity (PlatformRendering.2)

Fresh NSKeyedArchiver processes can emit identical semantic dictionaries with
reordered object tables and different raw hashes. The preserved 52bf archive
and 0685 witness demonstrate this directly. Both original raw archives and
hashes remain retained; neither production serialization nor saved resources
are rewritten.

Before accepting the Mac producer or any UIKit/phone consumer, the required
verifier compares the complete bounded typed archive graph with the immutable
control archive. Only dictionary pair/field ordering and reference numbering
are normalized. Class metadata, primitive types/values, array order, reference
sharing and resource bytes remain exact. Duplicate physical plist or archived
dictionary keys, missing fields, dangling references, cycles, unreachable
objects, unknown classes and resource/type/value mutations fail closed. Each
accepted receipt retains both raw hashes and the canonical graph hash.

Physical binary-plist records are a separate namespace from `$objects` archive
nodes. The two retained Apple archives each have 134 physical records, 35 archive
nodes and 12 detached physical UID scalars pointing to already reachable archive
nodes. The verifier preserves the entire detached UID target multiset after
reference renumbering, including exact multiplicities. A changed, missing, extra
or dangling detached UID fails; any detached non-UID payload fails. No exception
depends on a filename or an archive hash, and no unreachable archive node is
permitted (apart from the required `$null` sentinel).

UIKit still hashes the actual input bytes and runs the existing legacy-reader
content/geometry assertions and pixel oracles. Its record explicitly names the
separate immutable control-archive hash. The mandatory final verifier computes
graph equality from both actual byte strings; a reported boolean is not proof.
The bounded consumer collector repeats this comparison from its fixed actual
handoff directory, checks the complete derived receipt, and retains the actual
archive handoff and manifest before optional evidence can use the byte budget.

## Test-only color-glyph raster comparison

Source `2980ebcf179acf092dbd35f29886cb5c44f6204e` retained the exact oracle backing
and production-helper replay. The emoji uses the same 10pt fallback font, glyph 813,
zero CTRun offset and effective device origin (0,12.48). Isolated alpha still differs;
this does not support a compensating baseline offset or a global color-space change.
The original production path, independent oracle and ≤2 final-image limit stay frozen.

`Celluloid.NativeGlyphObservation.2` adds nine fixed, test-only draw comparisons at
the same frame geometry: default CTFrame drawing; explicit subpixel positioning
on/off; positioning on with quantization on/off; smoothing off; and default CTLine,
CTRun and CTFont glyph drawing. Flags are identified only as explicit overrides,
not inferred default/readback values. The default frame replay must byte-match the
shipping helper. Each result retains public context/text transforms, the explicit
flags, interpolation setting, a small transparent PNG/hash and separate alpha/RGB
metrics against both original backings. The AppKit draw hook also records its public
antialias/interpolation observations. No comparison result grants qualification.

Each experiment PNG is at most 6KB, the complete stdout record remains at most 100KB,
and the collected diagnostic remains at most 160KB inside the existing Mac budget.
The collector rejects changed/missing experiment order, unknown flags/APIs/fields,
nonfinite transforms, changed geometry, corrupt PNGs and a mismatching default replay.
Actual native execution is still needed to distinguish draw-API behavior from state.

Apple references:
- [Subpixel positioning](https://developer.apple.com/documentation/coregraphics/cgcontext/setshouldsubpixelpositionfonts(_:))
- [Allowing subpixel positioning](https://developer.apple.com/documentation/coregraphics/cgcontext/setallowsfontsubpixelpositioning(_:))
- [Font smoothing](https://developer.apple.com/documentation/coregraphics/cgcontext/setshouldsmoothfonts(_:))
- [Public glyph drawing](https://developer.apple.com/documentation/coretext/ctfontdrawglyphs(_:_:_:_:_:))
- [AppKit glyph draw hook](https://developer.apple.com/documentation/appkit/nslayoutmanager/showcgglyphs(_:positions:count:font:textmatrix:attributes:in:))

### Invariant transform decomposition controls

The nine e723 comparisons left the emoji pixels identical across CTFrame, CTLine,
CTRun and CTFont drawing and all tested font flags. This does not yet prove an
inherent AppKit/CoreText difference: their equivalent final geometry is represented
by different CTM/text-position decompositions.

`NativeGlyphObservation.3` adds only two CTFont controls, keeping the original
shaped glyphs and fonts. `glyph-absolute-origin` moves the existing frame translation
into the user-space glyph positions. `glyph-appkit-transform` uses the recorded
AppKit flipped CTM and a reflected copy of each CTFont matrix, with reflected
user-space positions. Each glyph's planned device origin and effective linear
transform, derived from the input CTM, actual draw-font matrix and supplied positions, must differ by no more than floating-point roundoff (1e-9); this is a
transform identity check, not a change to the pixel limit. There are no fitted
baseline offsets. The collector independently recomputes the input transform proof from the retained
per-run glyph/font/size/matrix/position records. Post-call CGContext matrices are
observations only and are not used as evidence of the matrix active during drawing;
PNGs permit independent emoji and Latin/CJK-region comparisons.

[CTFontDrawGlyphs](https://developer.apple.com/documentation/coretext/ctfontdrawglyphs(_:_:_:_:_:))
takes user-space glyph positions and installs size/matrix attributes from its font.
Therefore the reflected case uses
[CTFontCreateCopyWithAttributes](https://developer.apple.com/documentation/coretext/ctfontcreatecopywithattributes(_:_:_:_:)),
preserving the font size and identity while specifying the reflection; it does not
assume that a separately assigned CGContext text matrix survives the draw call.
All original production/oracle geometry, data, thresholds and resource caps remain.
