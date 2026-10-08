import Foundation
import CelluloidDomain

/// Reconstruct transfer ownership from the persisted request, without retaining
/// an in-memory WCSessionFileTransfer handle across app launches.
enum WatchRequestTransfer {
    static func matches(_ metadata: [String: Any]?, request: CompanionRequest) -> Bool {
        guard let bytes = metadata?["celluloid.request.v1"] as? Data,
              let candidate = try? CompanionRequest.decode(bytes) else { return false }
        return candidate == request
    }
}
