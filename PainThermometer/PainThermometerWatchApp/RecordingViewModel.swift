import Foundation
import HealthKit
import SwiftUI

@MainActor
final class RecordingViewModel: NSObject, ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var elapsedText = "00:00"
    @Published private(set) var status = "Ready"
    @Published var endpointURLText: String
    @Published var bearerTokenText: String
    @Published var liveUploadEnabled: Bool
    @Published var localModelEnabled: Bool
    @Published var syntheticModeEnabled = false
    @Published var syntheticPainBias = 0.0
    @Published private(set) var painActivationText = "Pain 0/10"
    @Published private(set) var painActivationCount = 0
    @Published private(set) var painDetectedMode = false
    @Published private(set) var dropoutText = "Dropout none"
    @Published private(set) var bufferText = "Buffer 0/100"
    @Published private(set) var questionnaireText = "Questionnaire idle"
    @Published private(set) var voiceStatusText = "Voice idle"
    @Published private(set) var transcriptText = ""
    @Published private(set) var sensorRows: [SensorDisplayRow] = []
    @Published private(set) var scoreRows: [ScoreDisplayRow] = []

    private let healthStore = HKHealthStore()
    private let store = RunStore()
    private let featureWindowBuilder = FeatureWindowBuilder()
    private let localScorer = LocalCoreMLPainScorer()
    private var measurementBuffer = MeasurementBuffer(capacity: 100)
    private var syntheticGenerator = SyntheticSampleGenerator()
    private let voiceController = VoiceDialogueController()
    private var activationTracker = PainActivationTracker()
    private var questionnaireTriggeredForRunID: UUID?
    private var workoutManager: WorkoutRecordingManager?
    private var motionRecorder: MotionRecorder?
    private var timer: Timer?
    private var startedAt: Date?
    private var activeRun: RecordingRun?

    override init() {
        let settings = EndpointSettings.load()
        endpointURLText = settings.baseURLString
        bearerTokenText = settings.bearerToken
        liveUploadEnabled = settings.liveFeedEnabled
        localModelEnabled = settings.localModelEnabled
        super.init()
    }

    func prepare() async {
        guard HKHealthStore.isHealthDataAvailable() else {
            status = "Health data unavailable"
            return
        }

        do {
            try await requestHealthAuthorization()
            await voiceController.requestSpeechAuthorization()
            voiceStatusText = voiceController.status
            status = "Ready"
        } catch {
            status = "Health authorization failed"
        }
    }

    func start() async {
        guard !isRecording else { return }

        let run = RecordingRun(startedAt: Date())

        do {
            await featureWindowBuilder.reset()
            measurementBuffer.reset()
            syntheticGenerator = SyntheticSampleGenerator()
            bufferText = measurementBuffer.countText
            sensorRows = []
            scoreRows = []
            questionnaireText = "Questionnaire idle"
            questionnaireTriggeredForRunID = nil
            try await store.begin(run: run)
            let manager = WorkoutRecordingManager(
                healthStore: healthStore,
                run: run,
                store: store,
                onSample: { [weak self] sample in
                    Task { @MainActor in
                        self?.handle(sample: sample)
                    }
                }
            )
            try await manager.start()

            let motion = MotionRecorder(
                run: run,
                store: store,
                onSample: { [weak self] sample in
                    Task { @MainActor in
                        self?.handle(sample: sample)
                    }
                }
            )
            motion.start()

            activeRun = run
            workoutManager = manager
            motionRecorder = motion
            startedAt = run.startedAt
            isRecording = true
            status = "Run \(run.shortID)"
            startTimer()
        } catch {
            status = "Start failed: \(error.localizedDescription)"
            try? await store.finish(runID: run.id, endedAt: Date())
        }
    }

    func stop() async {
        guard isRecording else { return }

        motionRecorder?.stop()
        await workoutManager?.stop()

        if let runID = workoutManager?.run.id {
            try? await store.finish(runID: runID, endedAt: Date())
        }

        timer?.invalidate()
        timer = nil
        workoutManager = nil
        motionRecorder = nil
        activeRun = nil
        isRecording = false
        status = "Saved locally"
    }

    func saveEndpointSettings() {
        endpointSettings.save()
    }

    func connectEndpoint() async {
        saveEndpointSettings()
        do {
            let client = UploadClient(configuration: endpointSettings.uploadConfiguration)
            guard let response = try await client.connect(deviceID: DeviceIdentity.current) else {
                status = "Endpoint not set"
                return
            }
            activationTracker.configure(
                windowCount: response.activationWindowCount,
                thresholdCount: response.activationThresholdCount
            )
            apply(dropoutSignals: response.dropoutSignals ?? [])
            status = response.accepted ? "Endpoint connected" : "Endpoint rejected"
        } catch {
            status = "Connect failed"
        }
    }

    func uploadPending() async {
        saveEndpointSettings()
        do {
            let uploader = UploadClient(configuration: endpointSettings.uploadConfiguration)
            let count = try await uploader.uploadPendingRuns(from: store)
            status = count == 0 ? "No endpoint or no pending runs" : "Uploaded \(count)"
        } catch {
            status = "Upload failed: \(error.localizedDescription)"
        }
    }

    private func requestHealthAuthorization() async throws {
        guard
            let heartRate = HKObjectType.quantityType(forIdentifier: .heartRate),
            let activeEnergy = HKObjectType.quantityType(forIdentifier: .activeEnergyBurned),
            let basalEnergy = HKObjectType.quantityType(forIdentifier: .basalEnergyBurned),
            let distance = HKObjectType.quantityType(forIdentifier: .distanceWalkingRunning)
        else {
            return
        }

        var readTypes: Set<HKObjectType> = [
            HKObjectType.workoutType(),
            heartRate,
            activeEnergy,
            basalEnergy,
            distance
        ]
        [
            HKQuantityTypeIdentifier.restingHeartRate,
            HKQuantityTypeIdentifier.walkingHeartRateAverage,
            HKQuantityTypeIdentifier.heartRateVariabilitySDNN,
            HKQuantityTypeIdentifier.oxygenSaturation,
            HKQuantityTypeIdentifier.respiratoryRate,
            HKQuantityTypeIdentifier.stepCount,
            HKQuantityTypeIdentifier.flightsClimbed,
            HKQuantityTypeIdentifier.environmentalAudioExposure
        ].compactMap { HKObjectType.quantityType(forIdentifier: $0) }.forEach { readTypes.insert($0) }
        if #available(watchOS 7.0, *) {
            readTypes.insert(HKObjectType.electrocardiogramType())
        }
        let writeTypes: Set<HKSampleType> = [
            HKObjectType.workoutType()
        ]
        try await healthStore.requestAuthorization(toShare: writeTypes, read: readTypes)
    }

    private var endpointSettings: EndpointSettings {
        EndpointSettings(
            baseURLString: endpointURLText,
            bearerToken: bearerTokenText,
            liveFeedEnabled: liveUploadEnabled,
            localModelEnabled: localModelEnabled
        )
    }

    private func handle(sample: SensorSampleRow) {
        guard let run = activeRun else { return }
        let settings = endpointSettings
        settings.save()
        measurementBuffer.append(sample)
        bufferText = measurementBuffer.countText
        sensorRows = measurementBuffer.sensorRows()

        Task {
            if let window = await featureWindowBuilder.append(sample) {
                let localScore = await localScorer.score(window, enabled: settings.localModelEnabled)
                await MainActor.run {
                    if let localScore {
                        self.apply(score: localScore)
                    } else if settings.localModelEnabled {
                        self.status = "Local model unavailable"
                    }
                    self.apply(dropoutSignals: window.dropoutSignals)
                }
            }

            guard settings.liveFeedEnabled else { return }
            do {
                let client = UploadClient(configuration: settings.uploadConfiguration)
                guard let response = try await client.submitLive(samples: [sample], run: run) else { return }
                await MainActor.run {
                    self.apply(response: response)
                }
            } catch {
                await MainActor.run {
                    if self.isRecording {
                        self.status = "Live upload retry later"
                    }
                }
            }
        }
    }

    private func apply(response: LiveSamplesResponse) {
        if let scores = response.scores {
            scores.forEach(apply(score:))
        }
        apply(dropoutSignals: response.dropoutSignals ?? [])
    }

    private func apply(score: ScoreResult) {
        let snapshot = activationTracker.append(score)
        painActivationCount = snapshot.positiveCount
        painDetectedMode = snapshot.isActive
        painActivationText = snapshot.isActive
            ? "Pain detected \(snapshot.positiveCount)/\(snapshot.windowCount)"
            : "Pain \(snapshot.positiveCount)/\(snapshot.windowCount)"
        questionnaireText = snapshot.isActive ? "Questionnaire trigger ready" : "Questionnaire idle"
        scoreRows = Self.scoreRows(from: score, activationText: painActivationText)
        apply(dropoutSignals: score.dropoutSignals ?? [])
        if snapshot.isActive {
            submitPainTriggerIfNeeded(score: score, snapshot: snapshot)
        }
    }

    private func apply(dropoutSignals: [DropoutSignal]) {
        let missing = dropoutSignals
            .filter { $0.present == false || ($0.validFrac ?? 1) <= 0 }
            .map(\.sensor)
        dropoutText = missing.isEmpty ? "Dropout none" : "Dropout " + missing.prefix(3).joined(separator: ", ")
    }

    private func startTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor [self] in
                self.tick()
            }
        }
        tick()
    }

    private func tick() {
        guard let startedAt else {
            elapsedText = "00:00"
            return
        }
        let elapsed = max(0, Int(Date().timeIntervalSince(startedAt)))
        elapsedText = String(format: "%02d:%02d", elapsed / 60, elapsed % 60)
        emitSyntheticSamplesIfNeeded()
    }

    func speakCurrentQuestion() {
        let text = questionnaireText == "Questionnaire trigger ready" ? Self.initialPainPrompt : questionnaireText
        voiceController.speak(text)
        voiceStatusText = voiceController.status
    }

    func startListening() {
        voiceController.startListeningPlaceholder()
        voiceStatusText = voiceController.status
        transcriptText = voiceController.transcript
    }

    private func submitPainTriggerIfNeeded(score: ScoreResult, snapshot: PainActivationSnapshot) {
        guard let run = activeRun, questionnaireTriggeredForRunID != run.id else { return }
        questionnaireTriggeredForRunID = run.id
        questionnaireText = Self.initialPainPrompt
        voiceController.speak(Self.initialPainPrompt)
        voiceStatusText = voiceController.status

        let payload = PainTriggerPayload(
            runID: run.id,
            deviceID: run.deviceID,
            triggeredAt: Date(),
            activationPositiveCount: snapshot.positiveCount,
            activationWindowCount: snapshot.windowCount,
            score: score,
            buffer: measurementBuffer.payloadSamples(),
            suggestedPrompt: Self.initialPainPrompt
        )
        let settings = endpointSettings
        Task {
            do {
                let client = UploadClient(configuration: settings.uploadConfiguration)
                guard let response = try await client.submitPainTrigger(payload: payload) else { return }
                await MainActor.run {
                    if let revisedScores = response.revisedScores {
                        self.scoreRows = Self.scoreRows(from: revisedScores, activationText: self.painActivationText)
                    }
                    if let question = response.nextQuestion {
                        self.questionnaireText = question
                    }
                }
            } catch {
                await MainActor.run {
                    self.status = "Pain trigger queued locally"
                }
            }
        }
    }

    private func emitSyntheticSamplesIfNeeded() {
        guard syntheticModeEnabled, let run = activeRun else { return }
        let samples = syntheticGenerator.samples(run: run, painBias: syntheticPainBias)
        for sample in samples {
            Task { try? await store.append(sample) }
            handle(sample: sample)
        }
    }

    private static func scoreRows(from score: ScoreResult, activationText: String) -> [ScoreDisplayRow] {
        var rows: [ScoreDisplayRow] = [
            ScoreDisplayRow(id: "activation", label: "Activation", valueText: activationText)
        ]

        if let value = score.painLikelihood01 {
            rows.append(ScoreDisplayRow(id: "pain_likelihood", label: "Pain likelihood", valueText: percent(value)))
        }
        if let value = score.painScore0100 {
            rows.append(ScoreDisplayRow(id: "pain_score", label: "Pain score", valueText: MeasurementBuffer.format(value)))
        }
        if let value = score.stressLikelihood01 {
            rows.append(ScoreDisplayRow(id: "stress", label: "Stress likelihood", valueText: percent(value)))
        }
        if let value = score.baselineDeparture01 {
            rows.append(ScoreDisplayRow(id: "baseline", label: "Baseline departure", valueText: percent(value)))
        }
        if let value = score.confidence01 {
            rows.append(ScoreDisplayRow(id: "confidence", label: "Confidence", valueText: percent(value)))
        }
        if let value = score.quality01 {
            rows.append(ScoreDisplayRow(id: "quality", label: "Quality", valueText: percent(value)))
        }
        if let modelVersion = score.modelVersion {
            rows.append(ScoreDisplayRow(id: "model", label: "Model", valueText: modelVersion))
        }
        return rows
    }

    private static func percent(_ value: Double) -> String {
        String(format: "%.0f%%", value * 100)
    }

    private static let initialPainPrompt = "What happened around when the pain started?"
}
