// Máscara da pessoa em um vídeo (Vision da Apple, segmentação de pessoa), para o formato "tela verde".
// Escreve no stdout um quadro cinza de 8 bits (largura × altura do vídeo) por quadro: 255 = pessoa, 0 = fundo.
// Compilar: swiftc -O recortar_pessoa.swift -o bin/recortar_pessoa
// Uso: bin/recortar_pessoa video.mp4 | ffmpeg -f rawvideo -pix_fmt gray -s LxA -r FPS -i - mascara.mp4
// (a largura/altura são as do vídeo; ffprobe dá os dois)
import Foundation
import AVFoundation
import Vision
import CoreImage

guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write("uso: recortar_pessoa video.mp4\n".data(using: .utf8)!); exit(1)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
guard let trilha = asset.tracks(withMediaType: .video).first,
      let leitor = try? AVAssetReader(asset: asset) else {
    FileHandle.standardError.write("não abri o vídeo\n".data(using: .utf8)!); exit(1)
}
let saidaVideo = AVAssetReaderTrackOutput(track: trilha, outputSettings: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
leitor.add(saidaVideo)
leitor.startReading()

let req = VNGeneratePersonSegmentationRequest()      // com estado: reusar entre quadros deixa a borda estável
req.qualityLevel = .accurate
req.outputPixelFormat = kCVPixelFormatType_OneComponent8
let sequencia = VNSequenceRequestHandler()
let ctx = CIContext(options: [.workingColorSpace: NSNull()])
let cinza = CGColorSpaceCreateDeviceGray()
let saida = FileHandle.standardOutput
var n = 0

while let amostra = saidaVideo.copyNextSampleBuffer(), let quadro = CMSampleBufferGetImageBuffer(amostra) {
    let L = CVPixelBufferGetWidth(quadro), A = CVPixelBufferGetHeight(quadro)
    var bytes = [UInt8](repeating: 0, count: L * A)
    if (try? sequencia.perform([req], on: quadro)) != nil, let m = req.results?.first?.pixelBuffer {
        let mi = CIImage(cvPixelBuffer: m)
        let esc = mi.transformed(by: CGAffineTransform(scaleX: CGFloat(L) / mi.extent.width,
                                                       y: CGFloat(A) / mi.extent.height))
        ctx.render(esc, toBitmap: &bytes, rowBytes: L, bounds: CGRect(x: 0, y: 0, width: L, height: A),
                   format: .L8, colorSpace: cinza)
    }
    saida.write(Data(bytes))
    n += 1
}
FileHandle.standardError.write("\(n) quadros\n".data(using: .utf8)!)
