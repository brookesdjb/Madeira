import Foundation

#if DEBUG && MADEIRA_AUTOMATION
/// A bounded, local XCTest request. No paths, launch arguments or account operations.
struct AutomationCommand: Decodable {
    enum Operation: String, Decodable {
        case status = "get_status", games = "list_installed_games"
        case launch = "launch_game", stop = "stop_game"
        case game = "get_game_status", runtime = "get_runtime_status"
        case jit = "get_jit_status", diagnostics = "get_diagnostics"
    }
    let schema_version: Int
    let request_id: String
    let operation: Operation
    let library_id: UUID?
    let steam_app_id: Int?

    static func parse(_ text: String) throws -> Self {
        guard let bytes = text.data(using: .utf8), bytes.count <= 4096,
              let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              Set(object.keys).isSubset(of: ["schema_version", "request_id", "operation", "library_id", "steam_app_id"]),
              let request = try? JSONDecoder().decode(Self.self, from: bytes),
              request.schema_version == 2, !request.request_id.isEmpty,
              request.request_id.utf8.count <= 64,
              request.request_id.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95 }),
              request.steam_app_id.map({ $0 > 0 }) ?? true else { throw Failure.invalidRequest }
        let selectors = (request.library_id == nil ? 0 : 1) + (request.steam_app_id == nil ? 0 : 1)
        if request.operation == .launch || request.operation == .stop {
            guard selectors == 1 else { throw Failure.invalidRequest }
        } else if selectors != 0 { throw Failure.invalidRequest }
        return request
    }

    enum Failure: String, Error { case invalidRequest = "invalid_request", duplicate = "duplicate_request", limit = "request_limit_requires_restart" }
}

/// Never evict IDs and thereby allow a late launch replay. Bound memory per process.
struct AutomationRequestLedger {
    private var seen = Set<String>()
    mutating func accept(_ id: String) throws {
        guard !seen.contains(id) else { throw AutomationCommand.Failure.duplicate }
        guard seen.count < 1000 else { throw AutomationCommand.Failure.limit }
        seen.insert(id)
    }
}
#endif
