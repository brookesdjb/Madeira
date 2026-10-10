// Host-only stand-ins; the listener under test is the actual app source.
import Foundation
@MainActor final class AutomationGameplayReplay {
    static let shared = AutomationGameplayReplay()
    var status: [String: Any] = ["state": "RUNNING"]
    var heartbeats = 0
    func heartbeat() { heartbeats += 1 }
    func stop(_ reason: String) { status["state"] = reason }
}
func madeira_automation_capture_stop() {}
struct LibraryEntry {}
@MainActor final class AutomationProbe {
    static let enabled = true
    static let shared = AutomationProbe()
    var launch: (LibraryEntry) -> Void = { _ in }
    var snapshot = "{}"
    var commandReply = "{}"
    var sequence = 0
    func refresh(publish: Bool = true) -> String {
        sequence += 1
        snapshot = String(data: try! JSONSerialization.data(withJSONObject: ["schema_version":1,
            "pid":Int(getpid()), "sequence":sequence,
            "replay": AutomationGameplayReplay.shared.status]), encoding:.utf8)!
        return snapshot
    }
    func command(_ text: String, launch: (LibraryEntry) -> Void) {
        let request = try! JSONSerialization.jsonObject(with: Data(text.utf8)) as! [String: Any]
        commandReply = String(data: try! JSONSerialization.data(withJSONObject: ["schema_version":2,
            "pid":Int(getpid()), "request_id":request["request_id"]!, "status":"completed"]), encoding:.utf8)!
    }
}
@main struct Host {
    @MainActor static func main() {
        let transport = AutomationTransport(endpoint: URL(fileURLWithPath: CommandLine.arguments[1]))
        transport.start()
        withExtendedLifetime(transport) { RunLoop.main.run() }
    }
}
