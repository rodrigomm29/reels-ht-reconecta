// Para onde o rosto aponta (Vision da Apple): uma linha por imagem, "<caminho>\t<yaw>\t<pitch>\t<roll>\t<area>"
// em graus (yaw: vira pro lado; pitch: olha pra cima/baixo). Sem rosto: "<caminho>\t-". Usa o maior rosto.
// Compilar: swiftc -O olhar_camera.swift -o bin/olhar_camera
// Uso: bin/olhar_camera img1.png img2.png ...
import Foundation
import Vision
import AppKit

for caminho in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: caminho),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("\(caminho)\t-"); continue
    }
    let req = VNDetectFaceRectanglesRequest()
    req.revision = VNDetectFaceRectanglesRequestRevision3
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    let rostos = (req.results ?? []).sorted { $0.boundingBox.width * $0.boundingBox.height > $1.boundingBox.width * $1.boundingBox.height }
    guard let r = rostos.first else { print("\(caminho)\t-"); continue }
    let g = { (v: NSNumber?) -> String in String(format: "%.1f", (v?.doubleValue ?? 0) * 180 / .pi) }
    print("\(caminho)\t\(g(r.yaw))\t\(g(r.pitch))\t\(g(r.roll))\t\(String(format: "%.3f", r.boundingBox.width * r.boundingBox.height))")
}
