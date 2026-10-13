// OCR da legenda queimada (Vision da Apple, pt-BR). Uma linha de saída por imagem: "<caminho>\t<texto>".
// Compilar: swiftc -O ocr_legenda.swift -o bin/ocr_legenda
// Uso: bin/ocr_legenda img1.png img2.png ...
import Foundation
import Vision
import AppKit

for caminho in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: caminho),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("\(caminho)\t"); continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["pt-BR", "en-US"]
    req.usesLanguageCorrection = true
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    try? h.perform([req])
    // ordena de cima pra baixo (y do Vision cresce pra cima)
    let obs = (req.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    let linhas = obs.compactMap { $0.topCandidates(1).first?.string }
    print("\(caminho)\t\(linhas.joined(separator: " "))")
}
