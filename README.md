
![](banner.jpg)

![](https://img.shields.io/badge/iOS-15.0%2B-blue.svg)
![](https://img.shields.io/badge/Swift-5%20language-orange.svg)
![License](https://img.shields.io/github/license/lexrus/VPNOn.svg?style=flat)

[<img src="https://cloud.githubusercontent.com/assets/219689/5575342/963e0ee8-9013-11e4-8091-7ece67d64729.png" width="135" height="40" alt="AppStore"/>](https://itunes.apple.com/app/celluloid/id1124966798)

The Best Photo Extension APP on iOS

## Features

1. Adaptivity:

 Run On iPhone & iPad, Support both portrait and landscape orientations

2. Multitasking:

 Support Slide Over, Split View on iPad & iPad Pro

3. Editable:

 Celluloid can reconstructs the past edits, it can allow users to alter or revert past edits or add new edit.

4. Filter, Bubble, Sticker and Collage features for photo editing.


## Technology

### Cocoa:

1. AutoLayout + StackView

 - layout
 - adaptivity
 - multiasking

2. Core Image

3. PhotoKit

4. Photo Extension

5. Cocoa Touch Framework

 - Code Sharing
 - Code Reuse

### Swift

1. Functional Programming

2. Powerful Enum

3. Strong Typing and Inferred type

## Current development

The modernization branch targets iOS 15 and later and is built with stable Xcode 27. Open `Celluloid.xcworkspace`; Swift Package Manager resolves pinned SnapKit 5.7.1. CocoaPods is no longer part of the build. Existing vendored dependency sources and licenses are retained for attribution only.

`python3 Scripts/generate_project.py` deterministically regenerates the project after source/resource changes. The shared `Celluloid` scheme contains model/rendering/Photos-extension unit tests and simulator UI regression tests. [GitHub Actions](https://github.com/100mango/Celluloid/actions) verifies the exact toolchain, runs iPhone and iPad suites, and builds an unsigned device archive. Simulator fixture setup is included in the workflow.

See [release and validation checklist](RELEASE_CHECKLIST.md) for exact observed runs, preserved adjustment-data compatibility, and remaining real-device, Photos-host, signing and App Store gates. A successful unsigned CI run does not publish the app.
