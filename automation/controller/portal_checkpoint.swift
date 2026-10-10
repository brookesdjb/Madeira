// Host-only macOS Vision checkpoint. Never export arbitrary recognized text.
import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count == 2,
      let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { exit(2) }
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["en-US"]
do { try VNImageRequestHandler(cgImage: image, options: [:]).perform([request]) }
catch { exit(3) }
func normalized(_ text: String) -> String {
    String(text.lowercased().filter { $0.isLetter || $0.isNumber })
}
// This package's large blurred title produces "Hirst" for "First" on Vision.
// Permit one substitution or one inserted/deleted glyph, with a bounded length.
// Background shapes can join the title; partial titles and substrings still fail.
func titleMatches(_ text: String) -> Bool {
    let expected = Array("portalthefirstslice"), actual = Array(normalized(text))
    guard abs(actual.count - expected.count) <= 1 else { return false }
    if actual.count == expected.count {
        return zip(actual, expected).filter { $0 != $1 }.count <= 1
    }
    let longer = actual.count > expected.count ? actual : expected
    let shorter = actual.count > expected.count ? expected : actual
    for omitted in longer.indices {
        if longer.enumerated().filter({ $0.offset != omitted }).map({ $0.element }) == shorter { return true }
    }
    return false
}
let expected = ["new_game": "newgame", "options": "options", "quit": "quit"]
var matches: [String: Bool] = ["title": false, "new_game": false, "options": false, "quit": false]
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first, candidate.confidence >= 0.8 else { continue }
    if titleMatches(candidate.string) { matches["title"] = true }
    // Menu labels must occur on the left, below the title; the title and
    // three separate labels together exclude the Source splash and desktop.
    if observation.boundingBox.minX < 0.3, observation.boundingBox.midY < 0.5 {
        for (key, value) in expected where normalized(candidate.string) == value { matches[key] = true }
    }
}
let result: [String: Any] = ["schema_version": 1, "checkpoint": "portal_first_slice_menu",
                           "matches": matches, "passed": matches.values.allSatisfy { $0 }]
guard let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]) else { exit(4) }
print(String(decoding: data, as: UTF8.self))
