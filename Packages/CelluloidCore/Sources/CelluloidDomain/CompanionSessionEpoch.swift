import Foundation

/// A render started for one activated counterpart must never be sent after deactivation.
/// This is a local lifecycle guard, not a claim about a physical Watch identity.
public struct CompanionSessionEpoch: Sendable {
    private var token = UUID()
    public private(set) var isActive = false
    public init() {}
    public mutating func activate() { token = UUID(); isActive = true }
    public mutating func invalidate() { token = UUID(); isActive = false }
    public var ticket: UUID? { isActive ? token : nil }
    public func canDeliver(_ ticket: UUID?) -> Bool { isActive && ticket == token }
}
