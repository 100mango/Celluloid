import Foundation

/// Photos explicitly forbids calling its finish completion after cancellation.
/// This host callback lifecycle is separate from the renderer task's cancellation.
@MainActor final class PhotosHostFinishCoordinator<Output> {
    private var generation = UUID()
    private var task: Task<Void, Never>?
    private var preparing: ((Bool) -> Void)?

    func finish(preparing: @escaping (Bool) -> Void,
                failed: @escaping (Error) -> Void,
                operation: @escaping () async throws -> Output,
                completion: @escaping (Output?) -> Void) {
        cancel()
        let token = generation
        self.preparing = preparing; preparing(true)
        guard token == generation else { return }
        task = Task {
            guard token == generation, !Task.isCancelled else { return }
            do {
                let output = try await operation()
                guard token == generation, !Task.isCancelled else { return }
                self.task = nil; self.preparing = nil; preparing(false)
                guard token == generation, !Task.isCancelled else { return }
                completion(output)
            } catch {
                guard token == generation, !Task.isCancelled else { return }
                self.task = nil; self.preparing = nil; preparing(false)
                failed(error)
                guard token == generation, !Task.isCancelled else { return }
                completion(nil)
            }
        }
    }
    func cancel() {
        generation = UUID(); task?.cancel(); task = nil
        let update = preparing; preparing = nil; update?(false)
    }
}
