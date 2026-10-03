import Foundation
import CelluloidDomain

/// Serializes our observed counterpart epoch with the synchronous enqueue call.
/// No asynchronous work belongs in these closures. Actual image-file delivery
/// requires paired hardware; supported immediate-message tests are separate.
final class CompanionDeliveryGate: @unchecked Sendable {
    private let lock = NSLock()
    private var epoch = CompanionSessionEpoch()
    func activate() { lock.lock(); defer { lock.unlock() }; epoch.activate() }
    func ticket(isSessionActive: () -> Bool) -> UUID? {
        lock.lock(); defer { lock.unlock() }
        return isSessionActive() ? epoch.ticket : nil
    }
    @discardableResult func enqueue(_ ticket: UUID?, isSessionActive: () -> Bool, action: () -> Void) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard isSessionActive(), epoch.canDeliver(ticket) else { return false }
        action(); return true
    }
    /// Capture existing owned transfer handles while enqueue is excluded. Cancel
    /// those captured handles afterward; do not re-enumerate a newly active Watch.
    func invalidate<Captured>(capture: () -> Captured) -> Captured {
        lock.lock(); defer { lock.unlock() }
        epoch.invalidate(); return capture()
    }
}
