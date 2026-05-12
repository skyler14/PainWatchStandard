import Foundation

struct RecordingRun: Codable, Sendable {
    let id: UUID
    let deviceID: UUID
    let startedAt: Date

    init(id: UUID = UUID(), deviceID: UUID = DeviceIdentity.current, startedAt: Date) {
        self.id = id
        self.deviceID = deviceID
        self.startedAt = startedAt
    }

    var shortID: String {
        String(id.uuidString.prefix(8))
    }
}

struct RunHeaderRow: Codable, Sendable {
    let rowType = "run"
    let schemaVersion = 1
    let runID: UUID
    let deviceID: UUID
    let appName = "PainThermometer"
    let platform = "watchOS"
    let startedAt: Date
    let workoutActivityType = "other"
    let sensorBlocksRequested: [String]

    enum CodingKeys: String, CodingKey {
        case rowType = "row_type"
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case deviceID = "device_id"
        case appName = "app_name"
        case platform
        case startedAt = "started_at"
        case workoutActivityType = "workout_activity_type"
        case sensorBlocksRequested = "sensor_blocks_requested"
    }
}

struct SensorSampleRow: Codable, Sendable {
    let rowType = "sample"
    let schemaVersion = 1
    let runID: UUID
    let sampleID = UUID()
    let sampleTimeUTC: Date
    let sampleOffsetS: TimeInterval
    let sensor: String
    let unit: String?
    let value: Double?
    let x: Double?
    let y: Double?
    let z: Double?
    let accuracy: Double?
    let source: String
    let metadata: [String: String]

    enum CodingKeys: String, CodingKey {
        case rowType = "row_type"
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case sampleID = "sample_id"
        case sampleTimeUTC = "sample_time_utc"
        case sampleOffsetS = "sample_offset_s"
        case sensor
        case unit
        case value
        case x
        case y
        case z
        case accuracy
        case source
        case metadata
    }
}

struct RunEndRow: Codable, Sendable {
    let rowType = "run_end"
    let schemaVersion = 1
    let runID: UUID
    let endedAt: Date

    enum CodingKeys: String, CodingKey {
        case rowType = "row_type"
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case endedAt = "ended_at"
    }
}

struct PatientProfile: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    var firstName: String
    var lastName: String
    var createdAt: Date

    init(id: UUID = UUID(), firstName: String, lastName: String, createdAt: Date = Date()) {
        self.id = id
        self.firstName = firstName
        self.lastName = lastName
        self.createdAt = createdAt
    }

    var displayName: String {
        "\(firstName) \(lastName)"
    }
}

struct BaselineVitalRow: Identifiable, Equatable, Sendable {
    let id: String
    let label: String
    let valueText: String
    let detailText: String
}

struct QuestionnaireSessionSummary: Identifiable, Equatable, Sendable {
    let id: UUID
    let remoteSessionID: String?
    let startedAtText: String
    let painText: String
    let responseCount: Int
    let completionText: String
    let canSubmit: Bool
}

struct QuestionnaireDialogueMessage: Identifiable, Codable, Equatable, Sendable {
    enum Speaker: String, Codable, Sendable {
        case system
        case patient
    }

    let id: UUID
    let speaker: Speaker
    let text: String
    let timeText: String

    init(id: UUID = UUID(), speaker: Speaker, text: String, timeText: String) {
        self.id = id
        self.speaker = speaker
        self.text = text
        self.timeText = timeText
    }
}

enum DeviceIdentity {
    static var current: UUID {
        let key = "PainThermometerDeviceID"
        let defaults = UserDefaults.standard
        if let text = defaults.string(forKey: key), let uuid = UUID(uuidString: text) {
            return uuid
        }
        let uuid = UUID()
        defaults.set(uuid.uuidString, forKey: key)
        return uuid
    }
}

enum SignalMode: String, CaseIterable, Identifiable {
    case dummy
    case actual

    var id: String { rawValue }

    var label: String {
        switch self {
        case .dummy:
            return "Dummy"
        case .actual:
            return "Actual"
        }
    }
}

extension JSONEncoder {
    static var painThermometer: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}
