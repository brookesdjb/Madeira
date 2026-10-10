#if DEBUG && MADEIRA_AUTOMATION
import Foundation
import Network

/// One authenticated, bounded, serial command stream through paired-device forwarding.
/// The listener is loopback-only; no Bonjour advertisement or LAN command endpoint.
@MainActor final class AutomationTransport {
    static let shared = AutomationTransport()
    private var listener: NWListener?
    private var connection: NWConnection?
    private var buffer = Data()
    private var authenticated = false
    private var deadline: DispatchWorkItem?
    private let token = UUID().uuidString + UUID().uuidString
    private let endpoint: URL
    init(endpoint: URL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("automation-transport.private.json")) { self.endpoint = endpoint }

    func start() {
        guard AutomationProbe.enabled, listener == nil else { return }
        try? FileManager.default.removeItem(at: endpoint)
        do {
            let parameters = NWParameters.tcp
            parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
            let server = try NWListener(using: parameters)
            listener = server
            server.stateUpdateHandler = { [weak self] state in
                MainActor.assumeIsolated {
                    guard let self else { return }
                    switch state {
                    case .ready:
                        guard let port = server.port else { return }
                        do {
                            let bytes = try JSONSerialization.data(withJSONObject: ["schema_version": 1,
                                "pid": Int(getpid()), "port": Int(port.rawValue), "token": self.token])
                            try bytes.write(to: self.endpoint, options: .atomic)
                            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: self.endpoint.path)
                        } catch { server.cancel() }
                    case .failed, .cancelled:
                        try? FileManager.default.removeItem(at: self.endpoint)
                        self.disconnect()
                    default: break
                    }
                }
            }
            server.newConnectionHandler = { [weak self] incoming in
                MainActor.assumeIsolated {
                    guard let self, self.connection == nil else { incoming.cancel(); return }
                    self.connection = incoming
                    self.buffer.removeAll(keepingCapacity: false)
                    self.authenticated = false
                    incoming.stateUpdateHandler = { [weak self, weak incoming] state in
                        MainActor.assumeIsolated {
                            guard let self, let incoming, self.connection === incoming else { return }
                            switch state {
                            case .failed, .cancelled: self.disconnect()
                            default: break
                            }
                        }
                    }
                    incoming.start(queue: .main)
                    self.armDeadline(seconds: 5)
                    self.receive(incoming)
                }
            }
            server.start(queue: .main)
        } catch { listener = nil }
    }

    private func armDeadline(seconds: Double) {
        deadline?.cancel()
        let item = DispatchWorkItem { [weak self] in MainActor.assumeIsolated { self?.disconnect() } }
        deadline = item
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: item)
    }

    private func disconnect() {
        let owned = authenticated
        authenticated = false
        deadline?.cancel(); deadline = nil
        let old = connection; connection = nil
        old?.cancel(); buffer.removeAll(keepingCapacity: false)
        if owned {
            let replay = AutomationGameplayReplay.shared
            if replay.status["state"] as? String == "RUNNING" { replay.stop("TRANSPORT_DISCONNECTED") }
            // Also stop a standalone capture, without exporting it as successful.
            madeira_automation_capture_stop()
        }
    }

    private func receive(_ stream: NWConnection) {
        stream.receive(minimumIncompleteLength: 1, maximumLength: 8193) { [weak self, weak stream] bytes, _, complete, error in
            MainActor.assumeIsolated {
                guard let self, let stream, self.connection === stream else { return }
                guard error == nil, !complete, let bytes, !bytes.isEmpty else { self.disconnect(); return }
                self.buffer.append(bytes)
                guard self.buffer.count <= 8192 else { self.disconnect(); return }
                guard let newline = self.buffer.firstIndex(of: 10) else { self.receive(stream); return }
                // No pipelining: one request, one response. Never replay an uncertain mutation.
                guard newline == self.buffer.count - 1 else { self.disconnect(); return }
                let frame = self.buffer.prefix(upTo: newline)
                self.buffer.removeAll(keepingCapacity: true)
                guard let reply = self.handle(Data(frame)) else { self.disconnect(); return }
                self.armDeadline(seconds: 15)
                stream.send(content: reply + Data([10]), completion: .contentProcessed { [weak self, weak stream] error in
                    MainActor.assumeIsolated {
                        guard let self, let stream, self.connection === stream else { return }
                        if error != nil { self.disconnect() } else { self.receive(stream) }
                    }
                })
            }
        }
    }

    private func handle(_ bytes: Data) -> Data? {
        guard let message = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any],
              message["token"] as? String == token, let kind = message["kind"] as? String else { return nil }
        let probe = AutomationProbe.shared
        if kind == "snapshot", Set(message.keys) == ["token", "kind"] {
            authenticated = true
            AutomationGameplayReplay.shared.heartbeat()
            return Data(probe.refresh(publish: false).utf8)
        }
        if kind == "command", Set(message.keys) == ["token", "kind", "request"],
           let request = message["request"] as? [String: Any],
           let data = try? JSONSerialization.data(withJSONObject: request), data.count <= 4096,
           let text = String(data: data, encoding: .utf8) {
            authenticated = true
            AutomationGameplayReplay.shared.heartbeat()
            probe.command(text, launch: probe.launch)
            return Data(probe.commandReply.utf8)
        }
        return nil
    }
}
#endif
