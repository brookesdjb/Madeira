// Host-only Vision adapter. Export fixed checkpoints and benchmark numbers only.
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
request.usesCPUOnly = true
do { try VNImageRequestHandler(cgImage: image, options: [:]).perform([request]) }
catch { exit(3) }
var scores: [String: Any] = [:]
var labels = Set<String>()
let names = ["mountain_peak": "Mountain Peak", "syria": "Syria", "geothermal_valley": "Geothermal Valley"]
for observation in request.results ?? [] {
    guard observation.boundingBox.midY > 0.13,
          let candidate = observation.topCandidates(1).first, candidate.confidence >= 0.8 else { continue }
    let text = candidate.string
    let normalized = String(text.lowercased().filter { $0.isLetter || $0.isNumber })
    for label in ["continue", "loadgame", "newgame", "startbenchmark", "ok"] where normalized == label {
        labels.insert(label)
    }
    for (key, name) in names {
        let pattern = "^" + name + #":\s*([0-9]+\.[0-9]{2}) FPS \(min:\s*([0-9]+\.[0-9]{2}), max:\s*([0-9]+\.[0-9]{2})\)$"#
        if let match = try? NSRegularExpression(pattern: pattern).firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
           let a = Range(match.range(at: 1), in: text), let b = Range(match.range(at: 2), in: text), let c = Range(match.range(at: 3), in: text),
           let average = Double(text[a]), let minimum = Double(text[b]), let maximum = Double(text[c]),
           minimum <= average, average <= maximum, maximum <= 1000 {
            scores[key] = ["average_fps": average, "minimum_fps": minimum, "maximum_fps": maximum]
        }
    }
    if let match = try? NSRegularExpression(pattern: #"^Overall score:\s*([0-9]+\.[0-9]{2}) FPS$"#).firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
       let range = Range(match.range(at: 1), in: text), let value = Double(text[range]), value > 0, value <= 1000 {
        scores["overall_fps"] = value
    }
}
let result: [String: Any] = ["schema_version": 1, "game": "rise_of_the_tomb_raider",
    "result_ready": scores.count == 4 && labels.contains("ok"),
    "menu_ready": Set(["continue", "loadgame", "newgame", "startbenchmark"]).isSubset(of: labels),
    "scores": scores]
guard let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]) else { exit(4) }
print(String(decoding: data, as: UTF8.self))
