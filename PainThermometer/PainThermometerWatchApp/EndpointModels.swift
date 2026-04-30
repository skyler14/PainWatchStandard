import Foundation

struct ConnectRequest: Codable, Sendable {
    let schemaVersion = 1
    let source = "PainThermometerWatchApp"
    let deviceID: UUID
    let platform = "watchOS"
    let capabilities: [String]
    let display: DisplayContract

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case source
        case deviceID = "device_id"
        case platform
        case capabilities
        case display
    }
}

struct DisplayContract: Codable, Sendable {
    let activationWindowCount = 10
    let activationThresholdCount = 7
    let painLikelihoodThreshold = 0.65
    let confidenceThreshold = 0.50
    let qualityThreshold = 0.60

    enum CodingKeys: String, CodingKey {
        case activationWindowCount = "activation_window_count"
        case activationThresholdCount = "activation_threshold_count"
        case painLikelihoodThreshold = "pain_likelihood_threshold"
        case confidenceThreshold = "confidence_threshold"
        case qualityThreshold = "quality_threshold"
    }
}

struct ConnectResponse: Codable, Sendable {
    let accepted: Bool
    let serverTimeUTC: Date?
    let liveSamplesPath: String?
    let historicalImportPath: String?
    let scorePath: String?
    let activationWindowCount: Int?
    let activationThresholdCount: Int?
    let dropoutSignals: [DropoutSignal]?

    enum CodingKeys: String, CodingKey {
        case accepted
        case serverTimeUTC = "server_time_utc"
        case liveSamplesPath = "live_samples_path"
        case historicalImportPath = "historical_import_path"
        case scorePath = "score_path"
        case activationWindowCount = "activation_window_count"
        case activationThresholdCount = "activation_threshold_count"
        case dropoutSignals = "dropout_signals"
    }
}

struct LiveSamplesPayload: Codable, Sendable {
    let schemaVersion = 1
    let source = "PainThermometerWatchApp"
    let runID: UUID
    let deviceID: UUID
    let sentAt: Date
    let samples: [SensorSampleRow]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case source
        case runID = "run_id"
        case deviceID = "device_id"
        case sentAt = "sent_at"
        case samples
    }
}

struct HistoricalUploadPayload: Codable, Sendable {
    let schemaVersion = 1
    let source = "PainThermometerWatchApp"
    let uploadedAt: Date
    let fileName: String
    let rowsJSONL: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case source
        case uploadedAt = "uploaded_at"
        case fileName = "file_name"
        case rowsJSONL = "rows_jsonl"
    }
}

struct LiveSamplesResponse: Codable, Sendable {
    let accepted: Bool
    let acceptedCount: Int?
    let serverTimeUTC: Date?
    let scores: [ScoreResult]?
    let dropoutSignals: [DropoutSignal]?

    enum CodingKeys: String, CodingKey {
        case accepted
        case acceptedCount = "accepted_count"
        case serverTimeUTC = "server_time_utc"
        case scores
        case dropoutSignals = "dropout_signals"
    }
}

struct HistoricalUploadResponse: Codable, Sendable {
    let accepted: Bool
    let runID: UUID?
    let rowsReceived: Int?
    let duplicateRows: Int?
    let scores: [ScoreResult]?
    let dropoutSignals: [DropoutSignal]?

    enum CodingKeys: String, CodingKey {
        case accepted
        case runID = "run_id"
        case rowsReceived = "rows_received"
        case duplicateRows = "duplicate_rows"
        case scores
        case dropoutSignals = "dropout_signals"
    }
}

struct ScoreResult: Codable, Sendable {
    let scoreName: String?
    let painLikelihood01: Double?
    let painScore0100: Double?
    let painDetected: Bool?
    let confidence01: Double?
    let quality01: Double?
    let stressLikelihood01: Double?
    let baselineDeparture01: Double?
    let windowStartUTC: Date?
    let windowEndUTC: Date?
    let modelVersion: String?
    let dropoutSignals: [DropoutSignal]?

    enum CodingKeys: String, CodingKey {
        case scoreName = "score_name"
        case painLikelihood01 = "pain_likelihood_0_1"
        case painScore0100 = "pain_score_0_100"
        case painDetected = "pain_detected"
        case confidence01 = "confidence_0_1"
        case quality01 = "quality_0_1"
        case stressLikelihood01 = "stress_likelihood_0_1"
        case baselineDeparture01 = "baseline_departure_0_1"
        case windowStartUTC = "window_start_utc"
        case windowEndUTC = "window_end_utc"
        case modelVersion = "model_version"
        case dropoutSignals = "dropout_signals"
    }

    var activatesPainWindow: Bool {
        if let painDetected {
            return painDetected
        }
        return (painLikelihood01 ?? 0) >= 0.65
            && (confidence01 ?? 0) >= 0.50
            && (quality01 ?? 0) >= 0.60
    }
}

struct DropoutSignal: Codable, Sendable {
    let sensor: String
    let present: Bool?
    let validFrac: Double?
    let reason: String?
    let severity: String?

    enum CodingKeys: String, CodingKey {
        case sensor
        case present
        case validFrac = "valid_frac"
        case reason
        case severity
    }
}

extension JSONDecoder {
    static var painThermometer: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}
