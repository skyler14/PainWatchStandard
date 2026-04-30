import Foundation

struct FeatureWindow: Sendable {
    let runID: UUID
    let windowStartUTC: Date
    let windowEndUTC: Date
    let features: [String: Double]
    let dropoutSignals: [DropoutSignal]
}

actor FeatureWindowBuilder {
    private let windowSeconds: TimeInterval
    private let cadenceSeconds: TimeInterval
    private var samples: [SensorSampleRow] = []
    private var lastAnchor: Date?

    init(windowSeconds: TimeInterval = 30, cadenceSeconds: TimeInterval = 1) {
        self.windowSeconds = windowSeconds
        self.cadenceSeconds = cadenceSeconds
    }

    func reset() {
        samples.removeAll()
        lastAnchor = nil
    }

    func append(_ sample: SensorSampleRow) -> FeatureWindow? {
        samples.append(sample)
        let anchor = sample.sampleTimeUTC
        let windowStart = anchor.addingTimeInterval(-windowSeconds)
        samples.removeAll { $0.sampleTimeUTC < windowStart }

        if let lastAnchor, anchor.timeIntervalSince(lastAnchor) < cadenceSeconds {
            return nil
        }

        lastAnchor = anchor
        return build(runID: sample.runID, windowStart: windowStart, windowEnd: anchor)
    }

    private func build(runID: UUID, windowStart: Date, windowEnd: Date) -> FeatureWindow {
        let windowSamples = samples.filter { $0.sampleTimeUTC >= windowStart && $0.sampleTimeUTC <= windowEnd }
        var features: [String: Double] = [
            "window_seconds": windowSeconds
        ]
        var dropoutSignals: [DropoutSignal] = []

        addScalarBlock("hr", sensorNames: ["heart_rate"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("spo2", sensorNames: ["oxygen_saturation"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("respiration", sensorNames: ["respiratory_rate"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("temperature", sensorNames: ["wrist_temperature", "body_temperature"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addVectorBlock("acc", sensorNames: ["accelerometer", "device_motion_acceleration"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addVectorBlock("gyro", sensorNames: ["gyroscope"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)

        return FeatureWindow(
            runID: runID,
            windowStartUTC: windowStart,
            windowEndUTC: windowEnd,
            features: features,
            dropoutSignals: dropoutSignals
        )
    }

    private func addScalarBlock(
        _ block: String,
        sensorNames: [String],
        samples: [SensorSampleRow],
        features: inout [String: Double],
        dropoutSignals: inout [DropoutSignal]
    ) {
        let values = samples.filter { sensorNames.contains($0.sensor) }.compactMap(\.value)
        features["\(block)__present"] = values.isEmpty ? 0 : 1
        features["\(block)__valid_count"] = Double(values.count)
        features["\(block)__valid_frac"] = values.isEmpty ? 0 : 1
        features["\(block)__mean"] = values.meanOrZero
        features["\(block)__last"] = values.last ?? 0

        if values.isEmpty {
            dropoutSignals.append(DropoutSignal(sensor: block, present: false, validFrac: 0, reason: "no_samples_in_window", severity: "missing"))
        }
    }

    private func addVectorBlock(
        _ block: String,
        sensorNames: [String],
        samples: [SensorSampleRow],
        features: inout [String: Double],
        dropoutSignals: inout [DropoutSignal]
    ) {
        let vectors = samples.filter { sensorNames.contains($0.sensor) && $0.x != nil && $0.y != nil && $0.z != nil }
        features["\(block)__present"] = vectors.isEmpty ? 0 : 1
        features["\(block)__valid_count"] = Double(vectors.count)
        features["\(block)__valid_frac"] = vectors.isEmpty ? 0 : 1
        features["\(block)__x_mean"] = vectors.compactMap(\.x).meanOrZero
        features["\(block)__y_mean"] = vectors.compactMap(\.y).meanOrZero
        features["\(block)__z_mean"] = vectors.compactMap(\.z).meanOrZero
        features["\(block)__mag_mean"] = vectors.map { sample in
            let x = sample.x ?? 0
            let y = sample.y ?? 0
            let z = sample.z ?? 0
            return sqrt(x * x + y * y + z * z)
        }.meanOrZero

        if vectors.isEmpty {
            dropoutSignals.append(DropoutSignal(sensor: block, present: false, validFrac: 0, reason: "no_samples_in_window", severity: "missing"))
        }
    }
}

private extension Array where Element == Double {
    var meanOrZero: Double {
        guard !isEmpty else { return 0 }
        return reduce(0, +) / Double(count)
    }
}
