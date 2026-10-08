// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CelluloidCore",
    defaultLocalization: "en",
    platforms: [.iOS(.v15), .macOS(.v13), .watchOS(.v9), .tvOS(.v17), .visionOS(.v1)],
    products: [.library(name: "CelluloidDomain", targets: ["CelluloidDomain"])],
    targets: [
        .target(name: "CelluloidDomain", resources: [.process("Resources")]),
        .testTarget(name: "CelluloidDomainTests", dependencies: ["CelluloidDomain"], resources: [.process("Fixtures")])
    ]
)
