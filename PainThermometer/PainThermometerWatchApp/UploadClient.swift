import Foundation

struct UploadConfiguration {
    let baseURL: URL?
    let bearerToken: String?
    let connectPath: String
    let liveSamplesPath: String
    let historicalImportPath: String
    let painTriggerPath: String
    let createPatientPath: String
    let continueQuestionnairePath: String
    let submitQuestionnairePath: String

    init(
        baseURL: URL?,
        bearerToken: String?,
        connectPath: String = "/v1/connect",
        liveSamplesPath: String = "/v1/live-samples",
        historicalImportPath: String = "/v1/runs/import-jsonl",
        painTriggerPath: String = "/v1/pain-trigger",
        createPatientPath: String = "/v1/patients",
        continueQuestionnairePath: String = "/v1/questionnaire/continue",
        submitQuestionnairePath: String = "/v1/questionnaire/submit"
    ) {
        self.baseURL = baseURL
        self.bearerToken = bearerToken
        self.connectPath = connectPath
        self.liveSamplesPath = liveSamplesPath
        self.historicalImportPath = historicalImportPath
        self.painTriggerPath = painTriggerPath
        self.createPatientPath = createPatientPath
        self.continueQuestionnairePath = continueQuestionnairePath
        self.submitQuestionnairePath = submitQuestionnairePath
    }

    static let disabled = UploadConfiguration(baseURL: nil, bearerToken: nil)
}

struct UploadClient {
    let configuration: UploadConfiguration

    func connect(deviceID: UUID) async throws -> ConnectResponse? {
        guard let url = endpointURL(path: configuration.connectPath) else { return nil }
        let payload = ConnectRequest(
            deviceID: deviceID,
            capabilities: SensorCatalog.requestedBlocks,
            display: DisplayContract()
        )
        return try await post(payload, to: url)
    }

    func submitLive(
        samples: [SensorSampleRow],
        run: RecordingRun,
        patient: PatientProfile? = nil,
        questionnaireSessionID: String? = nil
    ) async throws -> LiveSamplesResponse? {
        guard !samples.isEmpty, let url = endpointURL(path: configuration.liveSamplesPath) else { return nil }
        let payload = LiveSamplesPayload(
            runID: run.id,
            deviceID: run.deviceID,
            sentAt: Date(),
            patientID: patient?.id,
            patient: patient,
            questionnaireSessionID: questionnaireSessionID,
            samples: samples
        )
        return try await post(payload, to: url)
    }

    func submitPainTrigger(payload: PainTriggerPayload) async throws -> PainTriggerResponse? {
        guard let url = endpointURL(path: configuration.painTriggerPath) else { return nil }
        return try await post(payload, to: url)
    }

    func createPatient(_ patient: PatientProfile, deviceID: UUID) async throws -> CreatePatientResponse? {
        guard let url = endpointURL(path: configuration.createPatientPath) else { return nil }
        let payload = CreatePatientRequest(patient: patient, deviceID: deviceID, createdAt: Date())
        return try await post(payload, to: url)
    }

    func continueQuestionnaire(sessionID: String, localSessionID: UUID, response: String) async throws -> ContinueQuestionnaireResponse? {
        guard let url = endpointURL(path: configuration.continueQuestionnairePath) else { return nil }
        let payload = ContinueQuestionnairePayload(
            questionnaireSessionID: sessionID,
            localSessionID: localSessionID,
            response: response,
            submittedAt: Date()
        )
        return try await post(payload, to: url)
    }

    func submitQuestionnaire(sessionID: String, localSessionID: UUID, transcript: [QuestionnaireDialogueMessage]) async throws -> SubmitQuestionnaireResponse? {
        guard let url = endpointURL(path: configuration.submitQuestionnairePath) else { return nil }
        let payload = SubmitQuestionnairePayload(
            questionnaireSessionID: sessionID,
            localSessionID: localSessionID,
            transcript: transcript,
            submittedAt: Date()
        )
        return try await post(payload, to: url)
    }

    func uploadPendingRuns(from store: RunStore) async throws -> Int {
        guard let endpoint = endpointURL(path: configuration.historicalImportPath) else { return 0 }

        var uploaded = 0
        for file in try await store.pendingRunFiles() {
            let rows = try String(contentsOf: file, encoding: .utf8)
            let payload = HistoricalUploadPayload(
                uploadedAt: Date(),
                fileName: file.lastPathComponent,
                rowsJSONL: rows
            )
            let response: HistoricalUploadResponse = try await post(payload, to: endpoint)
            guard response.accepted else { throw UploadError.rejected }
            try await store.markUploaded(file)
            uploaded += 1
        }
        return uploaded
    }

    private func post<T: Encodable, U: Decodable>(_ payload: T, to endpoint: URL) async throws -> U {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let bearerToken = configuration.bearerToken {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder.painThermometer.encode(payload)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, 200..<300 ~= httpResponse.statusCode else {
            throw UploadError.rejected
        }
        return try JSONDecoder.painThermometer.decode(U.self, from: data)
    }

    private func endpointURL(path: String) -> URL? {
        guard let baseURL = configuration.baseURL else { return nil }
        if let absolute = URL(string: path), absolute.scheme != nil {
            return absolute
        }
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        let basePath = components?.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) ?? ""
        let nextPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components?.path = "/" + ([basePath, nextPath].filter { !$0.isEmpty }.joined(separator: "/"))
        return components?.url
    }
}

enum UploadError: Error {
    case rejected
}
