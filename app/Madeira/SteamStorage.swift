// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 125hz
// Madeira Converter Exception: see LICENSE-EXCEPTION.md

import Foundation

/// Persistent identity is independent of the removable volume's current mount path.
/// The first prototype deliberately does not enable external installs or discovery.
struct SteamStorageLibrary: Codable, Equatable, Identifiable, Sendable {
    static let internalID = "internal"
    let id: String
    var name: String
    var bookmark: Data?
    var windowsDrive: String { id == Self.internalID ? "C" : "E" }
    static let internalLibrary = Self(id: internalID, name: "iPad", bookmark: nil)
}

enum SteamStorageAvailability: String, Codable {
    case available, disconnected, permissionDenied, readOnly, identityMismatch
}

enum SteamStorageError: Error, LocalizedError {
    case unavailable(SteamStorageAvailability), unsafePath, unsupportedLocation, invalidRecord
    var errorDescription: String? {
        switch self {
        case .unavailable(.disconnected): return "Reconnect the registered SSD and try again."
        case .unavailable(.permissionDenied): return "Select the registered folder again to renew access."
        case .unavailable(.readOnly): return "The SSD is read-only."
        case .unavailable(.identityMismatch): return "This is not the registered library folder. Select the original folder."
        case .unavailable(.available): return "The library could not be accessed."
        case .unsafePath: return "The requested path leaves the registered library."
        case .unsupportedLocation: return "Select a dedicated folder on a locally attached drive. Cloud and network folders are unsupported."
        case .invalidRecord: return "The saved library registration is invalid."
        }
    }
}

/// Shared by the device prototype and future install/launch integration.
/// Callers must keep external access and coordination active while using URLs.
enum SteamStoragePath {
    static func components(_ relative: String) throws -> [String] {
        let normalized = relative.replacingOccurrences(of: "\\", with: "/")
        let parts = normalized.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard !parts.isEmpty, parts.count <= 64, normalized.utf8.count < 4096,
              parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." &&
                  !$0.contains(":") && !$0.unicodeScalars.contains(where: { $0.value < 32 }) }) else {
            throw SteamStorageError.unsafePath
        }
        return parts
    }

    static func native(_ relative: String, root: URL) throws -> URL {
        let base = root.resolvingSymlinksInPath().standardizedFileURL
        let parts = try components(relative)
        var candidate = base
        for part in parts {
            candidate.appendPathComponent(part)
            // Resolving a whole nonexistent leaf can leave an existing symlink
            // ancestor unresolved on Darwin. Check each component, including
            // dangling links, before appending the next one.
            do {
                let attributes = try FileManager.default.attributesOfItem(atPath: candidate.path)
                if attributes[.type] as? FileAttributeType == .typeSymbolicLink {
                    throw SteamStorageError.unsafePath
                }
            } catch let error as NSError where error.domain == NSCocoaErrorDomain &&
                [NSFileReadNoSuchFileError, NSFileNoSuchFileError].contains(error.code) { }
        }

        return candidate
    }

    static func windows(_ relative: String, library: SteamStorageLibrary) throws -> String {
        library.windowsDrive + ":\\" + (try components(relative)).joined(separator: "\\")
    }
}

/// The marker prevents a different disk mounted at the old URL from inheriting
/// an install identity. It is not an authentication secret. Never recreate a
/// missing marker during reconnect: that requires an explicit new registration.
enum SteamStorageIdentity {
    static let marker = ".madeira-library-id"

    static func verify(_ id: String, root: URL) throws {
        let url = try SteamStoragePath.native(marker, root: root)
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              (values.fileSize ?? 1024) <= 128,
              try String(contentsOf: url, encoding: .utf8) == id else {
            throw SteamStorageError.unavailable(.identityMismatch)
        }
    }

    static func register(root: URL) throws -> String {
        let url = try SteamStoragePath.native(marker, root: root)
        // A registration can adopt an existing valid marker, never overwrite it.
        if FileManager.default.fileExists(atPath: url.path) {
            let values = try url.resourceValues(forKeys: [.fileSizeKey, .isSymbolicLinkKey])
            guard values.isSymbolicLink != true, (values.fileSize ?? 1024) <= 128 else {
                throw SteamStorageError.invalidRecord
            }
            let id = try String(contentsOf: url, encoding: .utf8)
            guard UUID(uuidString: id) != nil else { throw SteamStorageError.invalidRecord }
            try verify(id, root: root)
            return id
        }
        let id = UUID().uuidString
        try Data(id.utf8).write(to: url, options: .withoutOverwriting)
        return id
    }
}

#if os(iOS) || os(macOS)
/// One balanced scope and a coordinated accessor cover the *whole* synchronous
/// operation, including all POSIX handles and mappings. Run on a worker queue.
/// Never return an open handle, mmap pointer or task from this accessor.
/// A Wine session will require an accessor that ends only when Wine has stopped;
/// this data probe does not claim to have established that runtime contract.
enum SteamExternalAccess {
    static func coordinate<T>(url: URL, write: Bool, _ body: (URL) throws -> T) throws -> T {
        guard url.startAccessingSecurityScopedResource() else {
            throw SteamStorageError.unavailable(.permissionDenied)
        }
        defer { url.stopAccessingSecurityScopedResource() }
        var coordinationError: NSError?
        var outcome: Result<T, Error>?
        let coordinator = NSFileCoordinator()
        if write {
            coordinator.coordinate(writingItemAt: url, options: .forMerging, error: &coordinationError) {
                scoped in outcome = Result { try body(scoped) }
            }
        } else {
            coordinator.coordinate(readingItemAt: url, options: [], error: &coordinationError) {
                scoped in outcome = Result { try body(scoped) }
            }
        }
        if let coordinationError { throw coordinationError }
        guard let outcome else { throw SteamStorageError.unavailable(.disconnected) }
        return try outcome.get()
    }

    static func register(_ url: URL, replacing current: SteamStorageLibrary? = nil) throws -> SteamStorageLibrary {
        try coordinate(url: url, write: true) { root in
            let values = try root.resourceValues(forKeys: [.isDirectoryKey, .isUbiquitousItemKey, .volumeIsLocalKey, .volumeIsReadOnlyKey])
            guard values.isDirectory == true, values.isUbiquitousItem != true, values.volumeIsLocal == true else {
                throw SteamStorageError.unsupportedLocation
            }
            guard values.volumeIsReadOnly != true else { throw SteamStorageError.unavailable(.readOnly) }
            let id: String
            if let current {
                try SteamStorageIdentity.verify(current.id, root: root)
                id = current.id
            } else { id = try SteamStorageIdentity.register(root: root) }
            return SteamStorageLibrary(id: id, name: root.lastPathComponent,
                                       bookmark: try root.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil))
        }
    }

    /// Return refreshed bookmark data alongside the result; the caller persists it
    /// only after identity validation. No fallback to an internal path on failure.
    static func withLibrary<T>(_ library: SteamStorageLibrary, write: Bool,
                               _ body: (URL) throws -> T) throws -> (T, SteamStorageLibrary) {
        guard library.id != SteamStorageLibrary.internalID, let bookmark = library.bookmark else {
            throw SteamStorageError.invalidRecord
        }
        var stale = false
        let url = try URL(resolvingBookmarkData: bookmark, options: .withoutUI, relativeTo: nil, bookmarkDataIsStale: &stale)
        return try coordinate(url: url, write: write) { root in
            try SteamStorageIdentity.verify(library.id, root: root)
            let values = try root.resourceValues(forKeys: [.volumeIsReadOnlyKey])
            if write && values.volumeIsReadOnly == true { throw SteamStorageError.unavailable(.readOnly) }
            var updated = library
            if stale { updated.bookmark = try root.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil) }
            return (try body(root), updated)
        }
    }

    static func availability(for error: Error) -> SteamStorageAvailability {
        if case SteamStorageError.unavailable(let state) = error { return state }
        let e = error as NSError
        if e.domain == NSCocoaErrorDomain {
            if [NSFileReadNoPermissionError, NSFileWriteNoPermissionError].contains(e.code) { return .permissionDenied }
            if e.code == NSFileWriteVolumeReadOnlyError { return .readOnly }
        }
        return .disconnected
    }
}
#endif
