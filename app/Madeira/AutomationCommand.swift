import Foundation

#if DEBUG && MADEIRA_AUTOMATION
/// A bounded, local XCTest request. No paths, launch arguments or account operations.
struct AutomationCommand: Decodable {
    enum Operation: String, Decodable {
        case status = "get_status", games = "list_installed_games"
        case launch = "launch_game", stop = "stop_game"
        case game = "get_game_status", runtime = "get_runtime_status"
        case benchmarkStart = "start_benchmark"
        case inputReserve = "reserve_input", replayStart = "start_replay", replayStop = "stop_replay", replayStatus = "get_replay_status"
        case captureStart = "start_frame_capture", captureStop = "stop_frame_capture"
        case jit = "get_jit_status", diagnostics = "get_diagnostics"
    }
    let schema_version: Int
    let request_id: String
    let operation: Operation
    let library_id: UUID?
    let steam_app_id: Int?
    let replay: AutomationReplayPlan?
    let warmup_ms: Int?
    let capture_ms: Int?

    static func parse(_ text: String) throws -> Self {
        guard let bytes = text.data(using: .utf8), bytes.count <= 4096,
              let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              Set(object.keys).isSubset(of: ["schema_version", "request_id", "operation", "library_id", "steam_app_id", "replay", "warmup_ms", "capture_ms"]),
              let request = try? JSONDecoder().decode(Self.self, from: bytes),
              request.schema_version == 2, !request.request_id.isEmpty,
              request.request_id.utf8.count <= 64,
              request.request_id.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95 }),
              request.steam_app_id.map({ $0 > 0 }) ?? true else { throw Failure.invalidRequest }
        let selectors = (request.library_id == nil ? 0 : 1) + (request.steam_app_id == nil ? 0 : 1)
        if request.operation == .launch || request.operation == .stop {
            guard selectors == 1 else { throw Failure.invalidRequest }
        } else if selectors != 0 { throw Failure.invalidRequest }
        if request.operation == .replayStart || request.operation == .benchmarkStart {
            guard let plan = request.replay, plan.valid(), let raw = object["replay"] as? [String: Any],
                  Set(raw.keys) == Set(["duration_ms", "events"]),
                  let events = raw["events"] as? [[String: Any]],
                  events.allSatisfy({ Set($0.keys).isSubset(of: ["at_ms", "keys", "dx", "dy", "buttons", "lx", "ly", "rx", "ry"]) }) else { throw Failure.invalidRequest }
        } else if request.replay != nil { throw Failure.invalidRequest }
        if request.operation == .benchmarkStart {
            guard let warmup = request.warmup_ms, let duration = request.capture_ms,
                  (0...900000).contains(warmup), (1...900000).contains(duration),
                  warmup + duration == request.replay?.duration_ms else { throw Failure.invalidRequest }
        } else if request.warmup_ms != nil || request.capture_ms != nil { throw Failure.invalidRequest }
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

#if DEBUG && MADEIRA_AUTOMATION
struct AutomationReplayEvent: Decodable {
    let at_ms: Int
    let keys: [Int]
    let dx: Int32?
    let dy: Int32?
    let buttons: UInt16?
    let lx: Int16?
    let ly: Int16?
    let rx: Int16?
    let ry: Int16?
}
struct AutomationReplayPlan: Decodable {
    let duration_ms: Int
    let events: [AutomationReplayEvent]
    func valid() -> Bool {
        guard (1...900000).contains(duration_ms), (1...64).contains(events.count) else { return false }
        let allowed = Set([0x0D,0x1B,0x10,0x11,0x20,0x25,0x26,0x27,0x28] + Array(0x30...0x5A))
        var previous = -1
        for event in events {
            guard event.at_ms > previous, event.at_ms < duration_ms,
                  Set(event.keys).isSubset(of: allowed), event.keys.count <= 16,
                  Set(event.keys).count == event.keys.count,
                  abs(Int64(event.dx ?? 0)) <= 1000, abs(Int64(event.dy ?? 0)) <= 1000 else { return false }
            previous = event.at_ms
        }
        return true
    }
}
#endif
