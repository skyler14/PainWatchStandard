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
    @Published var signalMode: SignalMode = .dummy
    @Published var syntheticModeEnabled = false {
        didSet {
            signalMode = syntheticModeEnabled ? .dummy : .actual
            if syntheticModeEnabled {
                syntheticPainBias = max(syntheticPainBias, 0.12)
                status = "Synthetic random walk"
                if selectedPatient != nil, !isRecording {
                    Task { await start() }
                }
            } else if selectedPatient != nil {
                syntheticPainBias = 0
                status = isRecording ? "Live watch sensors" : "Ready"
            }
        }
    }
    @Published var syntheticPainBias = 0.0
    @Published private(set) var patientsOnDevice: [PatientProfile] = []
    @Published private(set) var selectedPatient: PatientProfile?
    @Published private(set) var baselineRows: [BaselineVitalRow] = []
    @Published private(set) var baselineStatusText = "Baseline pending"
    @Published private(set) var painActivationText = "Pain 0/10"
    @Published private(set) var painActivationCount = 0
    @Published private(set) var painDetectedMode = false
    @Published private(set) var dropoutText = "Dropout none"
    @Published private(set) var bufferText = "Buffer 0/100"
    @Published private(set) var questionnaireText = "Questionnaire idle"
    @Published private(set) var questionnaireNoticeVisible = false
    @Published private(set) var questionnaireActive = false
    @Published private(set) var currentQuestionText = "Tell me what happened when the pain started, where you felt it, and what it felt like."
    @Published var questionnaireResponseText = "" {
        didSet {
            resetQuestionSilenceCountdown()
        }
    }
    @Published private(set) var selectedQuestionnaireSessionID: UUID?
    @Published private(set) var dialogueMessages: [QuestionnaireDialogueMessage] = [] {
        didSet {
            if let activeQuestionnaireSessionID {
                dialogueMessagesBySession[activeQuestionnaireSessionID] = dialogueMessages
            }
        }
    }
    @Published private(set) var isRecordingQuestionnaireResponse = false
    @Published private(set) var responseSilenceProgress = 0.0
    @Published private(set) var speakingProgress = 0.0
    @Published private(set) var questionnaireCompletionText = "0%"
    @Published private(set) var questionnaireCanSubmit = false
    @Published private(set) var voiceStatusText = "Voice idle"
    @Published private(set) var transcriptText = ""
    @Published private(set) var sensorRows: [SensorDisplayRow] = []
    @Published private(set) var scoreRows: [ScoreDisplayRow] = []
    @Published private(set) var sensorChartPoints: [BufferChartPoint] = []
    @Published private(set) var scoreChartPoints: [BufferChartPoint] = []
    @Published private(set) var questionnaireSessions: [QuestionnaireSessionSummary] = []

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
    private var silenceTimer: Timer?
    private var silenceProgressTimer: Timer?
    private var silenceStartedAt: Date?
    private var speakingProgressTimer: Timer?
    private var startedAt: Date?
    private var activeRun: RecordingRun?
    private var questionIndex = 0
    private var activeQuestionnaireSessionID: UUID?
    private var activeRemoteQuestionnaireSessionID: String?
    private var activeQuestionnaireStartedAt: Date?
    private var activeQuestionnaireResponseCount = 0
    private var activeQuestionnaireCompletion = 0.0
    private var dialogueMessagesBySession: [UUID: [QuestionnaireDialogueMessage]] = [:]
    private var pendingBackendMessageID: UUID?

    override init() {
        let settings = EndpointSettings.load()
        endpointURLText = settings.baseURLString
        bearerTokenText = settings.bearerToken
        liveUploadEnabled = settings.liveFeedEnabled
        localModelEnabled = settings.localModelEnabled
        signalMode = settings.localModelEnabled ? .actual : .dummy
        patientsOnDevice = Self.loadPatients()
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
            await loadBaselineVitals()
            status = "Ready"
        } catch {
            status = "Health authorization failed"
        }
    }

    func createRandomPatientAndStart() async {
        let patient = Self.randomPatient()
        patientsOnDevice.insert(patient, at: 0)
        Self.savePatients(patientsOnDevice)
        await registerPatientWithBridge(patient)
        await selectPatientAndStart(patient)
    }

    func selectPatientAndStart(_ patient: PatientProfile) async {
        selectedPatient = patient
        await registerPatientWithBridge(patient)
        questionnaireNoticeVisible = false
        questionnaireActive = false
        selectedQuestionnaireSessionID = nil
        dialogueMessages = []
        questionIndex = 0
        activeQuestionnaireSessionID = nil
        activeRemoteQuestionnaireSessionID = nil
        activeQuestionnaireCompletion = 0
        questionnaireCompletionText = "0%"
        questionnaireCanSubmit = false
        currentQuestionText = Self.questionnairePrompts[0]
        if !isRecording {
            await start()
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
            sensorChartPoints = []
            scoreChartPoints = []
            questionnaireText = "Questionnaire idle"
            questionnaireNoticeVisible = false
            questionnaireActive = false
            questionnaireResponseText = ""
            selectedQuestionnaireSessionID = nil
            dialogueMessages = []
            isRecordingQuestionnaireResponse = false
            responseSilenceProgress = 0
            stopSpeakingProgress()
            questionIndex = 0
            currentQuestionText = Self.questionnairePrompts[0]
            questionnaireTriggeredForRunID = nil
            activeQuestionnaireSessionID = nil
            activeQuestionnaireStartedAt = nil
            activeQuestionnaireResponseCount = 0
            try await store.begin(run: run)
            if syntheticModeEnabled {
                activate(run: run, workoutManager: nil, motionRecorder: nil)
                status = "\(selectedPatient?.displayName ?? "Patient") synthetic"
                return
            }
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

            activate(run: run, workoutManager: manager, motionRecorder: motion)
            let mode = syntheticModeEnabled ? "synthetic" : "live"
            status = "\(selectedPatient?.displayName ?? "Patient") \(mode)"
        } catch {
            if syntheticModeEnabled {
                activate(run: run, workoutManager: nil, motionRecorder: nil)
                status = "\(selectedPatient?.displayName ?? "Patient") synthetic"
            } else {
                status = "Start failed: \(error.localizedDescription)"
                try? await store.finish(runID: run.id, endedAt: Date())
            }
        }
    }

    private func activate(run: RecordingRun, workoutManager: WorkoutRecordingManager?, motionRecorder: MotionRecorder?) {
        activeRun = run
        self.workoutManager = workoutManager
        self.motionRecorder = motionRecorder
        startedAt = run.startedAt
        isRecording = true
        startTimer()
        tick()
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
        silenceTimer?.invalidate()
        silenceTimer = nil
        silenceProgressTimer?.invalidate()
        silenceProgressTimer = nil
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

    private func loadBaselineVitals() async {
        let specs: [(String, String, HKQuantityTypeIdentifier, HKUnit, HKStatisticsOptions)] = [
            ("resting_hr", "Resting HR", .restingHeartRate, HKUnit.count().unitDivided(by: .minute()), .discreteAverage),
            ("walking_hr", "Walking HR", .walkingHeartRateAverage, HKUnit.count().unitDivided(by: .minute()), .discreteAverage),
            ("hrv", "HRV SDNN", .heartRateVariabilitySDNN, .secondUnit(with: .milli), .discreteAverage),
            ("spo2", "Blood oxygen", .oxygenSaturation, .percent(), .discreteAverage),
            ("respiration", "Respiration", .respiratoryRate, HKUnit.count().unitDivided(by: .minute()), .discreteAverage),
            ("steps", "Daily steps", .stepCount, .count(), .cumulativeSum)
        ]

        baselineStatusText = "Reading Health history"
        let end = Date()
        let start = Calendar.current.date(byAdding: .day, value: -30, to: end) ?? end.addingTimeInterval(-30 * 24 * 60 * 60)
        var rows: [BaselineVitalRow] = []

        for spec in specs {
            guard let type = HKObjectType.quantityType(forIdentifier: spec.2) else { continue }
            let value = await baselineValue(type: type, unit: spec.3, options: spec.4, start: start, end: end)
            let valueText: String
            if let value {
                if spec.0 == "spo2" {
                    valueText = String(format: "%.0f%%", value * 100)
                } else if spec.0 == "steps" {
                    valueText = String(format: "%.0f/day", value / 30)
                } else {
                    valueText = MeasurementBuffer.format(value)
                }
            } else {
                valueText = "--"
            }
            rows.append(BaselineVitalRow(id: spec.0, label: spec.1, valueText: valueText, detailText: "30 day watch history"))
        }

        baselineRows = rows
        baselineStatusText = rows.contains { $0.valueText != "--" } ? "Baseline from Health history" : "No baseline history yet"
    }

    private func baselineValue(
        type: HKQuantityType,
        unit: HKUnit,
        options: HKStatisticsOptions,
        start: Date,
        end: Date
    ) async -> Double? {
        await withCheckedContinuation { continuation in
            let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictEndDate)
            let query = HKStatisticsQuery(quantityType: type, quantitySamplePredicate: predicate, options: options) { _, statistics, _ in
                let quantity: HKQuantity?
                if options.contains(.cumulativeSum) {
                    quantity = statistics?.sumQuantity()
                } else {
                    quantity = statistics?.averageQuantity()
                }
                continuation.resume(returning: quantity?.doubleValue(for: unit))
            }
            healthStore.execute(query)
        }
    }

    private var endpointSettings: EndpointSettings {
        EndpointSettings(
            baseURLString: endpointURLText,
            bearerToken: bearerTokenText,
            liveFeedEnabled: liveUploadEnabled,
            localModelEnabled: localModelEnabled
        )
    }

    private func registerPatientWithBridge(_ patient: PatientProfile) async {
        let settings = endpointSettings
        settings.save()
        guard settings.uploadConfiguration.baseURL != nil else { return }
        do {
            let client = UploadClient(configuration: settings.uploadConfiguration)
            guard let response = try await client.createPatient(patient, deviceID: DeviceIdentity.current) else { return }
            status = response.accepted ? "Patient linked to Doctor A" : "Patient link rejected"
        } catch {
            status = "Patient link retry later"
        }
    }

    private func handle(sample: SensorSampleRow) {
        guard let run = activeRun else { return }
        if syntheticModeEnabled && sample.source != "synthetic_random_walk" {
            return
        }
        let settings = endpointSettings
        settings.save()
        measurementBuffer.append(sample)
        bufferText = measurementBuffer.countText
        sensorRows = measurementBuffer.sensorRows()
        sensorChartPoints = measurementBuffer.chartPoints()

        Task {
            if let window = await featureWindowBuilder.append(sample) {
                let localScore: ScoreResult?
                switch signalMode {
                case .dummy:
                    localScore = dummyScore(for: window)
                case .actual:
                    localScore = await localScorer.score(window, enabled: settings.localModelEnabled)
                }
                await MainActor.run {
                    if let localScore {
                        self.apply(score: localScore)
                    } else if settings.localModelEnabled && self.signalMode == .actual {
                        self.status = "Local model unavailable"
                    }
                    self.apply(dropoutSignals: window.dropoutSignals)
                }
            }

            let shouldStreamPainSession = activeRemoteQuestionnaireSessionID != nil || questionnaireActive || questionnaireNoticeVisible
            guard settings.liveFeedEnabled || shouldStreamPainSession else { return }
            do {
                let client = UploadClient(configuration: settings.uploadConfiguration)
                guard let response = try await client.submitLive(
                    samples: [sample],
                    run: run,
                    patient: selectedPatient,
                    questionnaireSessionID: activeRemoteQuestionnaireSessionID
                ) else { return }
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
        if questionnaireActive {
            questionnaireText = "Questionnaire active"
        } else if questionnaireNoticeVisible || snapshot.isActive {
            questionnaireText = "Questionnaire ready"
        } else {
            questionnaireText = "Questionnaire idle"
        }
        scoreRows = Self.scoreRows(from: score, activationText: painActivationText)
        scoreChartPoints.append(Self.scoreChartPoint(from: score))
        if scoreChartPoints.count > 100 {
            scoreChartPoints.removeFirst(scoreChartPoints.count - 100)
        }
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
        guard selectedQuestionnaireSessionID != nil else { return }
        voiceController.speak(currentQuestionText)
        voiceStatusText = voiceController.status
        if voiceController.isSpeaking {
            startSpeakingProgress(for: currentQuestionText)
        } else {
            stopSpeakingProgress()
        }
    }

    func startQuestionnaireResponseRecording() {
        guard selectedQuestionnaireSessionID != nil else { return }
        stopSpeakingProgress()
        isRecordingQuestionnaireResponse = true
        responseSilenceProgress = 0
        questionnaireResponseText = ""
        stopSilenceCountdown()
        voiceController.stopListening()
        voiceStatusText = voiceController.status
        transcriptText = voiceController.transcript
        questionnaireText = "Typing response"
    }

    func stopQuestionnaireResponseRecording() {
        finalizeQuestionnaireResponse()
    }

    func cancelQuestionnaireResponse() {
        stopSilenceCountdown()
        voiceController.stopListening()
        isRecordingQuestionnaireResponse = false
        responseSilenceProgress = 0
        questionnaireResponseText = ""
        transcriptText = ""
        voiceStatusText = voiceController.status
        questionnaireText = "Questionnaire active"
    }

    func submitActiveQuestionnaire() {
        guard questionnaireCanSubmit,
              let activeQuestionnaireSessionID,
              let activeRemoteQuestionnaireSessionID else { return }
        let transcript = dialogueMessages
        let settings = endpointSettings
        Task {
            do {
                let client = UploadClient(configuration: settings.uploadConfiguration)
                guard let response = try await client.submitQuestionnaire(
                    sessionID: activeRemoteQuestionnaireSessionID,
                    localSessionID: activeQuestionnaireSessionID,
                    transcript: transcript
                ) else { return }
                await MainActor.run {
                    if response.accepted {
                        self.questionnaireText = response.completed == true ? "Questionnaire submitted" : "Questionnaire saved"
                        self.questionnaireActive = response.completed != true
                        self.questionnaireCanSubmit = response.completed != true
                        self.activeQuestionnaireCompletion = response.completion01 ?? self.activeQuestionnaireCompletion
                        self.questionnaireCompletionText = Self.percent(self.activeQuestionnaireCompletion)
                        self.recordQuestionnaireSessionSummary()
                    }
                }
            } catch {
                await MainActor.run {
                    self.questionnaireText = "Submit retry later"
                }
            }
        }
    }

    func openQuestionnaireSession(_ session: QuestionnaireSessionSummary) {
        selectedQuestionnaireSessionID = session.id
        activeQuestionnaireSessionID = session.id
        activeRemoteQuestionnaireSessionID = session.remoteSessionID
        activeQuestionnaireStartedAt = activeQuestionnaireStartedAt ?? Date()
        activeQuestionnaireCompletion = completionValue(from: session.completionText)
        questionnaireCanSubmit = session.canSubmit
        questionnaireCompletionText = session.completionText
        questionnaireNoticeVisible = false
        questionnaireActive = true
        questionIndex = 0
        currentQuestionText = Self.questionnairePrompts[questionIndex]
        questionnaireResponseText = ""
        dialogueMessages = dialogueMessagesBySession[session.id] ?? [
            QuestionnaireDialogueMessage(
                speaker: .system,
                text: currentQuestionText,
                timeText: Self.shortTimeFormatter.string(from: Date())
            )
        ]
        questionnaireText = "Questionnaire active"
        speakCurrentQuestion()
    }

    func dismissQuestionnaireSession(_ session: QuestionnaireSessionSummary) {
        guard selectedQuestionnaireSessionID == session.id else { return }
        selectedQuestionnaireSessionID = nil
        questionnaireActive = false
        dialogueMessages = []
        questionnaireResponseText = ""
        isRecordingQuestionnaireResponse = false
        voiceController.stopListening()
        voiceStatusText = voiceController.status
        responseSilenceProgress = 0
        stopSpeakingProgress()
        silenceTimer?.invalidate()
        silenceTimer = nil
        silenceProgressTimer?.invalidate()
        silenceProgressTimer = nil
        questionnaireText = questionnaireSessions.isEmpty ? "Questionnaire idle" : "Questionnaire ready"
    }

    func removeQuestionnaireSession(_ session: QuestionnaireSessionSummary) {
        dismissQuestionnaireSession(session)
        questionnaireSessions.removeAll { $0.id == session.id }
        if activeQuestionnaireSessionID == session.id {
            activeQuestionnaireSessionID = nil
            activeRemoteQuestionnaireSessionID = nil
            activeQuestionnaireStartedAt = nil
            activeQuestionnaireResponseCount = 0
            activeQuestionnaireCompletion = 0
            questionnaireCompletionText = "0%"
            questionnaireCanSubmit = false
        }
        questionnaireNoticeVisible = !questionnaireSessions.isEmpty
        questionnaireText = questionnaireSessions.isEmpty ? "Questionnaire idle" : "Questionnaire ready"
    }

    func startQuestionnaireNow() {
        if let first = questionnaireSessions.first {
            openQuestionnaireSession(first)
        }
    }

    func advanceQuestionAfterSilence() {
        finalizeQuestionnaireResponse()
    }

    private func finalizeQuestionnaireResponse() {
        guard questionnaireActive else { return }
        stopSilenceCountdown()
        isRecordingQuestionnaireResponse = false
        voiceController.stopListening()
        voiceStatusText = voiceController.status
        responseSilenceProgress = 0
        stopSpeakingProgress()

        let response = questionnaireResponseText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !response.isEmpty else {
            questionnaireResponseText = ""
            transcriptText = ""
            questionnaireText = "No speech detected"
            recordQuestionnaireSessionSummary()
            return
        }

        activeQuestionnaireResponseCount += 1
        dialogueMessages.append(
            QuestionnaireDialogueMessage(
                speaker: .patient,
                text: response,
                timeText: Self.shortTimeFormatter.string(from: Date())
            )
        )
        let pendingID = UUID()
        pendingBackendMessageID = pendingID
        dialogueMessages.append(
            QuestionnaireDialogueMessage(
                id: pendingID,
                speaker: .system,
                text: "Sending response...",
                timeText: Self.shortTimeFormatter.string(from: Date())
            )
        )
        questionnaireResponseText = ""
        transcriptText = ""
        questionnaireText = "Waiting for response"
        recordQuestionnaireSessionSummary()
        if let activeQuestionnaireSessionID, let activeRemoteQuestionnaireSessionID {
            Task {
                await continueRemoteQuestionnaire(
                    remoteSessionID: activeRemoteQuestionnaireSessionID,
                    localSessionID: activeQuestionnaireSessionID,
                    response: response
                )
            }
        } else {
            appendNextLocalQuestion()
        }
    }

    private func appendNextLocalQuestion() {
        removePendingBackendMessage()
        questionIndex = min(questionIndex + 1, Self.questionnairePrompts.count - 1)
        currentQuestionText = Self.questionnairePrompts[questionIndex]
        activeQuestionnaireCompletion = min(1, activeQuestionnaireCompletion + 0.12)
        questionnaireCanSubmit = activeQuestionnaireCompletion >= 0.8
        questionnaireCompletionText = Self.percent(activeQuestionnaireCompletion)
        recordQuestionnaireSessionSummary()
        dialogueMessages.append(
            QuestionnaireDialogueMessage(
                speaker: .system,
                text: currentQuestionText,
                timeText: Self.shortTimeFormatter.string(from: Date())
            )
        )
        speakCurrentQuestion()
    }

    private func continueRemoteQuestionnaire(remoteSessionID: String, localSessionID: UUID, response: String) async {
        do {
            let client = UploadClient(configuration: endpointSettings.uploadConfiguration)
            guard let result = try await client.continueQuestionnaire(
                sessionID: remoteSessionID,
                localSessionID: localSessionID,
                response: response
            ) else {
                await MainActor.run { self.appendNextLocalQuestion() }
                return
            }
            await MainActor.run {
                self.apply(questionnaireResponse: result, remoteSessionID: remoteSessionID)
            }
        } catch {
            await MainActor.run {
                self.removePendingBackendMessage()
                self.questionnaireText = "Questionnaire offline"
                self.appendNextLocalQuestion()
            }
        }
    }

    private func apply(painTriggerResponse response: PainTriggerResponse) {
        activeRemoteQuestionnaireSessionID = response.questionnaireSessionID
        activeQuestionnaireCompletion = response.completion01 ?? activeQuestionnaireCompletion
        questionnaireCanSubmit = response.canSubmit ?? (activeQuestionnaireCompletion >= 0.8)
        questionnaireCompletionText = Self.percent(activeQuestionnaireCompletion)
        let next = response.question?.text ?? response.nextQuestion
        if let next, !next.isEmpty {
            currentQuestionText = next
        }
        recordQuestionnaireSessionSummary()
    }

    private func apply(questionnaireResponse response: ContinueQuestionnaireResponse, remoteSessionID: String) {
        removePendingBackendMessage()
        activeRemoteQuestionnaireSessionID = remoteSessionID
        activeQuestionnaireCompletion = response.completion01 ?? activeQuestionnaireCompletion
        questionnaireCanSubmit = response.canSubmit ?? (activeQuestionnaireCompletion >= 0.8)
        questionnaireCompletionText = Self.percent(activeQuestionnaireCompletion)
        let next = response.question?.text ?? response.nextQuestion ?? Self.questionnairePrompts[min(questionIndex + 1, Self.questionnairePrompts.count - 1)]
        currentQuestionText = next
        questionnaireText = questionnaireCanSubmit ? "Questionnaire ready to submit" : "Questionnaire active"
        recordQuestionnaireSessionSummary()
        dialogueMessages.append(
            QuestionnaireDialogueMessage(
                speaker: .system,
                text: currentQuestionText,
                timeText: Self.shortTimeFormatter.string(from: Date())
            )
        )
        speakCurrentQuestion()
    }

    private func removePendingBackendMessage() {
        guard let pendingBackendMessageID else { return }
        dialogueMessages.removeAll { $0.id == pendingBackendMessageID }
        self.pendingBackendMessageID = nil
    }

    private func submitPainTriggerIfNeeded(score: ScoreResult, snapshot: PainActivationSnapshot) {
        guard let run = activeRun, questionnaireTriggeredForRunID != run.id else { return }
        questionnaireTriggeredForRunID = run.id
        createQuestionnaireSessionCard()
        questionnaireNoticeVisible = true
        questionnaireText = "Questionnaire ready"

        let payload = PainTriggerPayload(
            runID: run.id,
            deviceID: run.deviceID,
            patient: selectedPatient,
            doctorGroupID: "doctor_a",
            doctorGroupName: "Doctor A",
            triggeredAt: Date(),
            activationPositiveCount: snapshot.positiveCount,
            activationWindowCount: snapshot.windowCount,
            score: score,
            scoreHistory: scoreChartPoints.suffix(100).map(Self.scoreHistoryPoint(from:)),
            buffer: measurementBuffer.payloadSamples(),
            suggestedPrompt: Self.questionnairePrompts[0]
        )
        let settings = endpointSettings
        Task {
            do {
                let client = UploadClient(configuration: settings.uploadConfiguration)
                guard let response = try await client.submitPainTrigger(payload: payload) else {
                    await MainActor.run { self.status = "Pain trigger local only" }
                    return
                }
                await MainActor.run {
                    self.apply(painTriggerResponse: response)
                    self.status = response.accepted ? "Pain trigger sent" : "Pain trigger rejected"
                }
            } catch {
                await MainActor.run {
                    self.status = "Pain trigger retry later"
                }
            }
        }
    }

    private func dummyScore(for window: FeatureWindow) -> ScoreResult {
        let heartRate = window.features["hr__last"] ?? window.features["hr__mean"] ?? 74
        let respiration = window.features["respiration__last"] ?? window.features["respiration__mean"] ?? 15
        let temperature = window.features["temperature__last"] ?? window.features["temperature__mean"] ?? 33.1
        let motion = window.features["acc__mag__mean"] ?? 0.05
        let bias = syntheticModeEnabled ? syntheticPainBias : 0
        let physiologicalSignal =
            normalized(heartRate, low: 68, high: 112) * 0.34
            + normalized(respiration, low: 12, high: 24) * 0.18
            + normalized(temperature, low: 32.8, high: 34.2) * 0.12
            + normalized(motion, low: 0.02, high: 0.35) * 0.16
            + bias * 0.20
        let painLikelihood = min(0.99, max(0.01, physiologicalSignal))
        let missingCount = window.dropoutSignals.filter { $0.present == false || ($0.validFrac ?? 1) <= 0 }.count
        let quality = min(1, max(0.2, 1 - 0.07 * Double(missingCount)))
        let confidence = min(0.95, max(0.05, 0.5 * quality + abs(painLikelihood - 0.5)))

        return ScoreResult(
            scoreName: "dummy_watch_signal",
            painLikelihood01: painLikelihood,
            painScore0100: painLikelihood * 100,
            painDetected: painLikelihood >= 0.65 && confidence >= 0.50 && quality >= 0.60,
            confidence01: confidence,
            quality01: quality,
            stressLikelihood01: nil,
            baselineDeparture01: nil,
            windowStartUTC: window.windowStartUTC,
            windowEndUTC: window.windowEndUTC,
            modelVersion: "dummy_dropout_signal",
            dropoutSignals: window.dropoutSignals
        )
    }

    private func normalized(_ value: Double, low: Double, high: Double) -> Double {
        guard high > low else { return 0 }
        return min(1, max(0, (value - low) / (high - low)))
    }

    private func emitSyntheticSamplesIfNeeded() {
        guard syntheticModeEnabled, let run = activeRun else { return }
        let samples = syntheticGenerator.samples(run: run, painBias: syntheticPainBias)
        for sample in samples {
            Task { try? await store.append(sample) }
            handle(sample: sample)
        }
    }

    private func resetQuestionSilenceCountdown() {
        guard isRecordingQuestionnaireResponse else { return }
        startSilenceCountdown()
    }

    private func stopSilenceCountdown() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        silenceProgressTimer?.invalidate()
        silenceProgressTimer = nil
        silenceStartedAt = nil
    }

    private func startSilenceCountdown() {
        stopSilenceCountdown()
        guard questionnaireActive else { return }
        silenceStartedAt = Date()
        responseSilenceProgress = 1
        silenceTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: false) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.finalizeQuestionnaireResponse()
            }
        }
        silenceProgressTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, let silenceStartedAt = self.silenceStartedAt else { return }
                let elapsed = Date().timeIntervalSince(silenceStartedAt)
                self.responseSilenceProgress = max(0, 1 - elapsed / 10)
            }
        }
    }

    private func startSpeakingProgress(for text: String) {
        stopSpeakingProgress()
        guard !text.isEmpty else { return }
        let duration = min(18, max(1.8, Double(text.split(separator: " ").count) * 0.45))
        let startedAt = Date()
        speakingProgress = 1
        speakingProgressTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                let elapsed = Date().timeIntervalSince(startedAt)
                if elapsed >= duration || !self.voiceController.isSpeaking {
                    self.stopSpeakingProgress()
                } else {
                    self.speakingProgress = max(0, 1 - elapsed / duration)
                }
            }
        }
    }

    private func stopSpeakingProgress() {
        speakingProgressTimer?.invalidate()
        speakingProgressTimer = nil
        speakingProgress = 0
    }

    private func createQuestionnaireSessionCard() {
        let sessionID = UUID()
        activeQuestionnaireSessionID = sessionID
        activeRemoteQuestionnaireSessionID = nil
        activeQuestionnaireStartedAt = Date()
        activeQuestionnaireResponseCount = 0
        activeQuestionnaireCompletion = 0
        questionnaireCompletionText = "0%"
        questionnaireCanSubmit = false
        recordQuestionnaireSessionSummary()
    }

    private func recordQuestionnaireSessionSummary() {
        guard let activeQuestionnaireSessionID else { return }
        let formatter = Self.shortTimeFormatter
        let startedAt = activeQuestionnaireStartedAt ?? Date()
        let painText = painActivationText.replacingOccurrences(of: "Pain detected ", with: "")
        let summary = QuestionnaireSessionSummary(
            id: activeQuestionnaireSessionID,
            remoteSessionID: activeRemoteQuestionnaireSessionID,
            startedAtText: formatter.string(from: startedAt),
            painText: painText,
            responseCount: activeQuestionnaireResponseCount,
            completionText: questionnaireCompletionText,
            canSubmit: questionnaireCanSubmit
        )
        questionnaireSessions.removeAll { $0.id == activeQuestionnaireSessionID }
        questionnaireSessions.insert(summary, at: 0)
    }

    private func completionValue(from text: String) -> Double {
        let valueText = text.replacingOccurrences(of: "%", with: "")
        return (Double(valueText) ?? 0) / 100
    }

    private static func loadPatients() -> [PatientProfile] {
        let defaults = UserDefaults.standard
        if let data = defaults.data(forKey: patientStoreKey),
           let patients = try? JSONDecoder.painThermometer.decode([PatientProfile].self, from: data),
           !patients.isEmpty {
            return patients
        }
        let seeded = [PatientProfile(firstName: "Taylor", lastName: "Morgan")]
        savePatients(seeded)
        return seeded
    }

    private static func savePatients(_ patients: [PatientProfile]) {
        guard let data = try? JSONEncoder.painThermometer.encode(patients) else { return }
        UserDefaults.standard.set(data, forKey: patientStoreKey)
    }

    private static func randomPatient() -> PatientProfile {
        let first = ["Avery", "Jordan", "Riley", "Casey", "Morgan", "Quinn", "Jamie", "Taylor"].randomElement() ?? "Avery"
        let last = ["Hayes", "Reed", "Parker", "Lane", "Brooks", "Ellis", "Stone", "Cole"].randomElement() ?? "Hayes"
        return PatientProfile(firstName: first, lastName: last)
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

    private static func scoreChartPoint(from score: ScoreResult) -> BufferChartPoint {
        let value = score.painLikelihood01 ?? ((score.painScore0100 ?? 0) / 100)
        let id = UUID()
        return BufferChartPoint(
            id: id,
            sensor: "pain_score",
            label: "P",
            value: value,
            normalizedValue: min(1, max(0, value)),
            timeText: shortTimeFormatter.string(from: score.windowEndUTC ?? Date())
        )
    }

    private static func scoreHistoryPoint(from point: BufferChartPoint) -> ScoreHistoryPoint {
        ScoreHistoryPoint(
            id: point.id,
            scoreName: point.sensor,
            value: point.value,
            normalizedValue: point.normalizedValue,
            timeText: point.timeText,
            capturedAt: nil
        )
    }

    private static let shortTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()

    private static let patientStoreKey = "PainThermometerPatientsOnDevice"
    private static let questionnairePrompts = [
        "Tell me what happened when the pain started, where you felt it, and what it felt like.",
        "How much did this pain affect walking, stairs, dressing, sleep, or daily activities?",
        "On a zero to ten scale, how bad is the pain now and on average this week?"
    ]
}
