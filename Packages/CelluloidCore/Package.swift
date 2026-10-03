// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CelluloidCore",
    platforms: [.iOS(.v15), .macOS(.v13), .watchOS(.v9), .tvOS(.v17), .visionOS(.v1)],
    products: [.library(name: "CelluloidDomain", targets: ["CelluloidDomain"])],
    targets: [
        .target(name: "CelluloidDomain"),
        .testTarget(name: "CelluloidDomainTests", dependencies: ["CelluloidDomain"], resources: [.process("Fixtures")])
    ]
)
