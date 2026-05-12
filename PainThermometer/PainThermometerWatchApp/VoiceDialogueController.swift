import AVFoundation
import Foundation

#if canImport(Speech)
import Speech
#endif

@MainActor
final class VoiceDialogueController: NSObject, ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var status = "Voice idle"
    @Published private(set) var isSpeaking = false

    private let synthesizer = AVSpeechSynthesizer()
    private let audioEngine = AVAudioEngine()
    #if canImport(Speech)
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    #endif

    func speak(_ text: String) {
        guard !text.isEmpty else { return }
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
            isSpeaking = false
            status = "Speech stopped"
            return
        }
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
        synthesizer.speak(utterance)
        isSpeaking = true
        status = "Speaking"
    }

    func requestSpeechAuthorization() async {
        #if os(watchOS) || os(iOS)
        let microphoneAllowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { allowed in
                continuation.resume(returning: allowed)
            }
        }
        guard microphoneAllowed else {
            status = "Mic denied"
            return
        }
        #endif

        #if canImport(Speech)
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
        switch speechStatus {
        case .authorized:
            status = "Speech ready"
        case .denied:
            status = "Speech denied"
        case .restricted:
            status = "Speech restricted"
        case .notDetermined:
            status = "Speech not determined"
        @unknown default:
            status = "Speech unavailable"
        }
        #else
        status = "Speech unavailable"
        #endif
    }

    @discardableResult
    func startListening(onTranscript: @escaping (String) -> Void) -> Bool {
        transcript = ""
        stopListening()

        #if canImport(Speech)
        guard let speechRecognizer, speechRecognizer.isAvailable else {
            status = "Speech recognizer unavailable"
            return false
        }

        do {
            if synthesizer.isSpeaking {
                synthesizer.stopSpeaking(at: .immediate)
                isSpeaking = false
            }
            try configureAudioSession()
            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            recognitionRequest = request

            let inputNode = audioEngine.inputNode
            let recordingFormat = inputNode.outputFormat(forBus: 0)
            inputNode.removeTap(onBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak request] buffer, _ in
                request?.append(buffer)
            }

            audioEngine.prepare()
            try audioEngine.start()
            status = "Listening"

            recognitionTask = speechRecognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let result {
                        let text = result.bestTranscription.formattedString
                        self.transcript = text
                        onTranscript(text)
                        self.status = result.isFinal ? "Transcript final" : "Listening"
                    }

                    if let error {
                        self.status = "Speech error: \(error.localizedDescription)"
                        self.stopListening()
                    } else if result?.isFinal == true {
                        self.stopListening()
                    }
                }
            }
        } catch {
            status = "Mic error: \(error.localizedDescription)"
            stopListening()
            return false
        }
        return true
        #else
        status = "Speech unavailable"
        return false
        #endif
    }

    func startDictation(onTranscript: @escaping (String) -> Void, onFinished: @escaping () -> Void) {
        if !startListening(onTranscript: onTranscript) {
            onFinished()
        }
    }

    func stopListening() {
        let wasListening = audioEngine.isRunning
        if audioEngine.isRunning {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
        }

        #if canImport(Speech)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest = nil
        #endif

        if wasListening, status == "Listening" {
            status = "Voice idle"
        }
    }

    private func configureAudioSession() throws {
        #if os(watchOS) || os(iOS)
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .measurement, options: [.duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        #endif
    }
}
