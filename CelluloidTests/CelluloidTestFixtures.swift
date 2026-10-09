import Foundation
import Photos

/// Resolves only a fixture identity reconciled by the owned-simulator bootstrap.
/// Stock Photos images can share dimensions/dates and must never be test targets.
enum CelluloidTestFixtures {
    static func syntheticAsset(width: Int = 640, height: Int = 480) -> PHAsset? {
        #if targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        guard let source = environment["CELLULOID_EXPECTED_SOURCE_SHA"], source.count == 40,
              source.allSatisfy({ "0123456789abcdef".contains($0) }),
              let serialized = environment["CELLULOID_FIXTURE_MANIFEST_JSON"],
              let bytes = serialized.data(using: .utf8), bytes.count <= 24_000,
              let manifest = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              manifest["source_sha"] as? String == source,
              let fixtures = manifest["fixtures"] as? [[String: Any]], fixtures.count == 6 else { return nil }
        let filename: String
        if width == 640, height == 480 { filename = "celluloid-fixture.png" }
        else if (800...803).contains(width), height == 600 { filename = "celluloid-composition-\(width - 800).png" }
        else { return nil }
        let matching = fixtures.filter { $0["filename"] as? String == filename }
        guard matching.count == 1, let item = matching.first,
              item["width"] as? Int == width, item["height"] as? Int == height,
              let identifier = item["identifier"] as? String,
              let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              asset.localIdentifier == identifier, asset.pixelWidth == width, asset.pixelHeight == height,
              PHAssetResource.assetResources(for: asset).contains(where: {
                  $0.type == .photo && $0.originalFilename == filename
              }) else { return nil }
        return asset
        #else
        return nil
        #endif
    }
}
