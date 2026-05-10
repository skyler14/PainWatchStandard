import Foundation

struct SensorDisplayRow: Identifiable, Sendable {
    let id: String
    let sensor: String
    let valueText: String
    let unitText: String
    let countText: String
    let updatedText: String
}

struct ScoreDisplayRow: Identifiable, Sendable {
    let id: String
    let label: String
    let valueText: String
}

struct BufferedMeasurementPayload: Codable, Sendable {
    let sampleID: UUID
    let sampleTimeUTC: Date
    let sampleOffsetS: TimeInterval
    let sensor: String
    let unit: String?
    let value: Double?
    let x: Double?
    let y: Double?
    let z: Double?

    enum CodingKeys: String, CodingKey {
        case sampleID = "sample_id"
        case sampleTimeUTC = "sample_time_utc"
        case sampleOffsetS = "sample_offset_s"
        case sensor
        case unit
        case value
        case x
        case y
        case z
    }
}

struct BufferEvictionCandidate: Identifiable, Sendable {
    let id: UUID
    let sensor: String
    let rank: Int
    let area: Double
    let sampleTimeUTC: Date
}

struct MeasurementBuffer: Sendable {
    private struct BufferedMeasurement: Identifiable, Sendable {
        let id: UUID
        let sampleTimeUTC: Date
        let sampleOffsetS: TimeInterval
        let sensor: String
        let unit: String?
        let value: Double?
        let x: Double?
        let y: Double?
        let z: Double?

        init(_ sample: SensorSampleRow) {
            id = sample.sampleID
            sampleTimeUTC = sample.sampleTimeUTC
            sampleOffsetS = sample.sampleOffsetS
            sensor = sample.sensor
            unit = sample.unit
            value = sample.value
            x = sample.x
            y = sample.y
            z = sample.z
        }

        var scalarValue: Double {
            if let value {
                return value
            }
            let xValue = x ?? 0
            let yValue = y ?? 0
            let zValue = z ?? 0
            return sqrt(xValue * xValue + yValue * yValue + zValue * zValue)
        }

        var valueText: String {
            if let value {
                return MeasurementBuffer.format(value)
            }
            let parts = [x, y, z].compactMap { component -> String? in
                guard let component else { return nil }
                return MeasurementBuffer.format(component)
            }
            return parts.isEmpty ? "--" : parts.joined(separator: ", ")
        }

        var payload: BufferedMeasurementPayload {
            BufferedMeasurementPayload(
                sampleID: id,
                sampleTimeUTC: sampleTimeUTC,
                sampleOffsetS: sampleOffsetS,
                sensor: sensor,
                unit: unit,
                value: value,
                x: x,
                y: y,
                z: z
            )
        }
    }

    let capacity: Int
    private var samples: [BufferedMeasurement] = []
    private(set) var nextEvictions: [BufferEvictionCandidate] = []

    init(capacity: Int = 100) {
        self.capacity = capacity
    }

    var count: Int {
        samples.count
    }

    var countText: String {
        "Buffer \(samples.count)/\(capacity)"
    }

    mutating func reset() {
        samples.removeAll(keepingCapacity: true)
        nextEvictions.removeAll(keepingCapacity: true)
    }

    mutating func append(_ sample: SensorSampleRow) {
        samples.append(BufferedMeasurement(sample))
        pruneIfNeeded()
        rebuildEvictionPlan()
    }

    func sensorRows() -> [SensorDisplayRow] {
        let grouped = Dictionary(grouping: samples, by: \.sensor)
        return grouped.keys.sorted().compactMap { sensor in
            guard let sensorSamples = grouped[sensor]?.sorted(by: { $0.sampleTimeUTC < $1.sampleTimeUTC }),
                  let latest = sensorSamples.last
            else {
                return nil
            }
            return SensorDisplayRow(
                id: sensor,
                sensor: sensor.replacingOccurrences(of: "_", with: " "),
                valueText: latest.valueText,
                unitText: latest.unit ?? "vector",
                countText: "\(sensorSamples.count)",
                updatedText: MeasurementBuffer.timeFormatter.string(from: latest.sampleTimeUTC)
            )
        }
    }

    func payloadSamples() -> [BufferedMeasurementPayload] {
        samples
            .sorted { $0.sampleTimeUTC < $1.sampleTimeUTC }
            .map(\.payload)
    }

    private mutating func pruneIfNeeded() {
        while samples.count > capacity {
            let candidates = rankedCandidates()
            if let candidate = candidates.first,
               let index = samples.firstIndex(where: { $0.id == candidate.id }) {
                samples.remove(at: index)
            } else {
                samples.removeFirst()
            }
        }
    }

    private mutating func rebuildEvictionPlan() {
        nextEvictions = Array(rankedCandidates().prefix(8))
    }

    private func rankedCandidates() -> [BufferEvictionCandidate] {
        let grouped = Dictionary(grouping: samples, by: \.sensor)
        var candidates: [BufferEvictionCandidate] = []

        for sensorSamples in grouped.values {
            let ordered = sensorSamples.sorted { $0.sampleTimeUTC < $1.sampleTimeUTC }
            guard ordered.count > 3 else { continue }
            let oldestSimplifiableIndexLimit = max(2, Int(Double(ordered.count) * 0.7))

            for index in 1..<min(ordered.count - 1, oldestSimplifiableIndexLimit) {
                let previous = ordered[index - 1]
                let current = ordered[index]
                let next = ordered[index + 1]
                let area = triangleArea(previous, current, next)
                candidates.append(
                    BufferEvictionCandidate(
                        id: current.id,
                        sensor: current.sensor,
                        rank: 0,
                        area: area,
                        sampleTimeUTC: current.sampleTimeUTC
                    )
                )
            }
        }

        return candidates
            .sorted {
                if $0.area == $1.area {
                    return $0.sampleTimeUTC < $1.sampleTimeUTC
                }
                return $0.area < $1.area
            }
            .enumerated()
            .map { offset, candidate in
                BufferEvictionCandidate(
                    id: candidate.id,
                    sensor: candidate.sensor,
                    rank: offset + 1,
                    area: candidate.area,
                    sampleTimeUTC: candidate.sampleTimeUTC
                )
            }
    }

    private func triangleArea(
        _ a: BufferedMeasurement,
        _ b: BufferedMeasurement,
        _ c: BufferedMeasurement
    ) -> Double {
        abs(
            (a.sampleOffsetS * (b.scalarValue - c.scalarValue)
                + b.sampleOffsetS * (c.scalarValue - a.scalarValue)
                + c.sampleOffsetS * (a.scalarValue - b.scalarValue)) / 2
        )
    }

    static func format(_ value: Double) -> String {
        if abs(value) >= 100 {
            return String(format: "%.0f", value)
        }
        if abs(value) >= 10 {
            return String(format: "%.1f", value)
        }
        return String(format: "%.2f", value)
    }

    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()
}
