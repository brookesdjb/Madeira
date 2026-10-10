// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 125hz
// Madeira Converter Exception: see LICENSE-EXCEPTION.md
import SwiftUI
import UIKit
import Darwin

private func runtimeRunning() -> Bool {
    for name in ["wine_process_is_running", "wineserver_is_running"] {
        guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), name) else { return true }
        let function = unsafeBitCast(symbol, to: (@convention(c) () -> Int32).self)
        if function() != 0 { return true }
    }
    return false
}

@MainActor private final class ExecutionProbe: ObservableObject {
    static let shared = ExecutionProbe()
    @Published var status = "Register a folder with the data probe first. Arm access before using the original runtime's Enable JIT and Wine Virtual Desktop buttons."
    @Published var armed = false
    private var release: DispatchSemaphore?

    func arm() {
        guard !armed, !runtimeRunning() else { return }
        armed = true
        let latch = DispatchSemaphore(value: 0)
        release = latch
        Task.detached(priority: .userInitiated) {
            do {
                let fm = FileManager.default
                let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                let library = try JSONDecoder().decode(SteamStorageLibrary.self, from: Data(contentsOf: support.appendingPathComponent("external-library-prototype.json")))
                _ = try SteamExternalAccess.withLibrary(library, write: true) { root in
                    let documents = fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
                    let prefix = documents.appendingPathComponent("wine")
                    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "madeira_seed_prefix_if_needed") else { throw SteamStorageError.invalidRecord }
                    let seed = unsafeBitCast(symbol, to: (@convention(c) (UnsafePointer<CChar>) -> Void).self)
                    prefix.path.withCString { seed($0) }
                    let devices = prefix.appendingPathComponent("dosdevices")
                    try fm.createDirectory(at: devices, withIntermediateDirectories: true)
                    let mapping = devices.appendingPathComponent("e:")
                    // Only this isolated harness owns E:. Never replace a real folder.
                    if (try? fm.attributesOfItem(atPath: mapping.path)[.type] as? FileAttributeType) == .typeSymbolicLink {
                        try fm.removeItem(at: mapping)
                    }
                    try fm.createSymbolicLink(at: mapping, withDestinationURL: root)
                    defer { try? fm.removeItem(at: mapping) }
                    let name = ".madeira-execution-" + UUID().uuidString
                    try Data(name.utf8).write(to: support.appendingPathComponent("ssd-last-execution.txt"), options: .atomic)
                    let scratch = try SteamStoragePath.native(name, root: root)
                    try fm.createDirectory(at: scratch, withIntermediateDirectories: false)
                    // Keep this small test output on SSD for inspection after a
                    // process exit; never copy a game's payload into app storage.
                    guard let fixture = Bundle.main.url(forResource: "ssd-fixture", withExtension: nil) else { throw SteamStorageError.invalidRecord }
                    for file in ["ssd_probe.exe", "ssd_probe.dll", "assets"] {
                        try fm.copyItem(at: fixture.appendingPathComponent(file), to: scratch.appendingPathComponent(file))
                    }
                    let config = "env.MADEIRA_EXE = E:\\\(name)\\ssd_probe.exe\nenv.MADEIRA_ARGS = \n"
                    try config.write(to: documents.appendingPathComponent("madeira.cfg"), atomically: true, encoding: .utf8)
                    Task { @MainActor in self.status = "E: access is armed and coordinated. Close this sheet, enable JIT using the original app UI, then tap Wine Virtual Desktop. The prepared config selects the test EXE. Reopen SSD to see the result. Access stays active until release or app exit." }
                    var reported = false
                    while latch.wait(timeout: .now() + 0.5) == .timedOut {
                        if !reported, let data = try? Data(contentsOf: scratch.appendingPathComponent("result.txt")), data.count < 16384,
                           let text = String(data: data, encoding: .utf8), text.contains("SSD-") {
                            reported = true
                            let passed = text.contains("SSD-EXE-DLL-ASSET-SAVE-PASS")
                            Task { @MainActor in self.status = passed ? "PASS: Windows x64 EXE and companion DLL loaded from E:, read a relative asset, and wrote/renamed/reopened a save beside the EXE. Brotato is not tested." : "FAIL: external EXE did not report success. Inspect the isolated app's Wine log and the SSD test output." }
                        }
                    }
                }
            } catch {
                let e = error as NSError
                Task { @MainActor in self.status = "Access failed (\(e.domain), \(e.code)). Reconnect or reauthorise the folder." }
            }
            Task { @MainActor in self.armed = false; self.release = nil }
        }
    }

    func checkResult() {
        guard !armed else { return }
        Task.detached(priority: .utility) {
            do {
                let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                let name = try String(contentsOf: support.appendingPathComponent("ssd-last-execution.txt"), encoding: .utf8)
                let library = try JSONDecoder().decode(SteamStorageLibrary.self, from: Data(contentsOf: support.appendingPathComponent("external-library-prototype.json")))
                let (passed, _) = try SteamExternalAccess.withLibrary(library, write: false) { root in
                    let file = try SteamStoragePath.native(name + "/result.txt", root: root)
                    guard let size = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize, size < 16384 else { throw SteamStorageError.invalidRecord }
                    let text = try String(contentsOf: file, encoding: .utf8)
                    return text.contains("SSD-EXE-DLL-ASSET-SAVE-PASS")
                }
                Task { @MainActor in self.status = passed ? "PASS: the last external EXE/DLL, relative asset and save test succeeded. Brotato remains untested." : "FAIL: last execution did not report success." }
            } catch {
                Task { @MainActor in self.status = "No readable completed result. Reconnect the SSD; if it is connected, the last execution did not complete." }
            }
        }
    }

    func disarm() {
        guard !runtimeRunning() else {
            status = "Wine or its server is still active. Quit this isolated app to release access safely."
            return
        }
        release?.signal()
    }
}

private struct RuntimeProbeView: View {
    @ObservedObject var probe = ExecutionProbe.shared
    @Environment(\.dismiss) var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section("Prebuilt runtime experiment") {
                    Text("This is the published runtime in an isolated app container, not the new source build. It does not use the working Madeira installation's credentials or games.")
                    NavigationLink("Register / test SSD folder") { SteamStorageProbeView() }.disabled(probe.armed)
                    Button("Arm E: and prepare external EXE") { probe.arm() }.disabled(probe.armed)
                    Button("Read last execution result") { probe.checkResult() }.disabled(probe.armed)
                    Button("Release SSD access") { probe.disarm() }.disabled(!probe.armed)
                }
                Section("Status") { Text(probe.status).textSelection(.enabled) }
            }
            .navigationTitle("SSD execution prototype")
            .toolbar { Button("Close") { dismiss() } }
        }
    }
}

@MainActor private final class Overlay: NSObject {
    static let shared = Overlay()
    var button: UIButton?
    @objc func show() {
        guard let root = button?.window?.rootViewController else { return }
        var top = root
        while let next = top.presentedViewController { top = next }
        top.present(UIHostingController(rootView: RuntimeProbeView()), animated: true)
    }
    @objc func attach() {
        guard button == nil,
              let window = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).flatMap(\.windows).first(where: \.isKeyWindow) else { return }
        let view = UIButton(type: .system)
        view.setTitle("SSD", for: .normal)
        view.backgroundColor = .systemBackground
        view.layer.cornerRadius = 12
        view.addTarget(self, action: #selector(show), for: .touchUpInside)
        view.translatesAutoresizingMaskIntoConstraints = false
        window.addSubview(view)
        NSLayoutConstraint.activate([
            view.trailingAnchor.constraint(equalTo: window.safeAreaLayoutGuide.trailingAnchor, constant: -12),
            view.topAnchor.constraint(equalTo: window.safeAreaLayoutGuide.topAnchor, constant: 44),
            view.widthAnchor.constraint(equalToConstant: 64), view.heightAnchor.constraint(equalToConstant: 44)
        ])
        button = view
    }
}

@_cdecl("madeira_ssd_overlay_install")
public func installOverlay() {
    DispatchQueue.main.async {
        NotificationCenter.default.addObserver(Overlay.shared, selector: #selector(Overlay.attach), name: UIApplication.didBecomeActiveNotification, object: nil)
        Overlay.shared.attach()
    }
}
