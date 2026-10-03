// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "CelluloidRendering",
    platforms: [.macOS(.v13), .iOS(.v15), .tvOS(.v17), .visionOS(.v1)],
    products: [.library(name: "CelluloidRendering", targets: ["CelluloidRendering"])],
    dependencies: [.package(path: "../CelluloidCore")],
    targets: [
        .target(name: "CelluloidRendering", dependencies: [.product(name: "CelluloidDomain", package: "CelluloidCore")], resources: [.process("Resources")]),
        .testTarget(name: "CelluloidRenderingTests", dependencies: ["CelluloidRendering"])
    ]
)
