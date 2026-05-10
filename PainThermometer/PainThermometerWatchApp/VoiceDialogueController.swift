import AVFoundation
import Foundation

#if canImport(Speech)
import Speech
#endif

@MainActor
final class VoiceDialogueController: NSObject, ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var status = "Voice idle"

    private let synthesizer = AVSpeechSynthesizer()

    func speak(_ text: String) {
        guard !text.isEmpty else { return }
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
        synthesizer.speak(utterance)
        status = "Speaking"
    }

    func requestSpeechAuthorization() async {
        #if canImport(Speech)
        _ = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
        self.status = "Speech ready"
        #else
        status = "Speech unavailable"
        #endif
    }

    func startListeningPlaceholder() {
        status = "Listening scaffold"
        transcript = ""
    }
}
