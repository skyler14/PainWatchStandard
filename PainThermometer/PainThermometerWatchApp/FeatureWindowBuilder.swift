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
        addScalarBlock("ibi", sensorNames: ["heart_rate_variability_sdnn"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("ecg", sensorNames: ["electrocardiogram"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("bvp", sensorNames: ["blood_volume_pulse"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("respiration", sensorNames: ["respiratory_rate"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addScalarBlock("temperature", sensorNames: ["wrist_temperature", "body_temperature"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addVectorBlock("acc", sensorNames: ["accelerometer", "device_motion_acceleration"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addVectorBlock("gyro", sensorNames: ["gyroscope"], samples: windowSamples, features: &features, dropoutSignals: &dropoutSignals)
        addBaselinePlaceholders(features: &features)

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
        addStats(prefix: "\(block)__", values: values, features: &features)

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
        addStats(prefix: "\(block)_x__", values: vectors.compactMap(\.x), features: &features)
        addStats(prefix: "\(block)_y__", values: vectors.compactMap(\.y), features: &features)
        addStats(prefix: "\(block)_z__", values: vectors.compactMap(\.z), features: &features)
        addStats(prefix: "\(block)__mag__", values: vectors.map { sample in
            let x = sample.x ?? 0
            let y = sample.y ?? 0
            let z = sample.z ?? 0
            return sqrt(x * x + y * y + z * z)
        }, features: &features)

        if vectors.isEmpty {
            dropoutSignals.append(DropoutSignal(sensor: block, present: false, validFrac: 0, reason: "no_samples_in_window", severity: "missing"))
        }
    }

    private func addStats(prefix: String, values: [Double], features: inout [String: Double]) {
        features["\(prefix)mean"] = values.meanOrZero
        features["\(prefix)std"] = values.stdOrZero
        features["\(prefix)min"] = values.min() ?? 0
        features["\(prefix)max"] = values.max() ?? 0
        features["\(prefix)last"] = values.last ?? 0
        features["\(prefix)slope_per_s"] = values.slopeOrZero
        features["\(prefix)peak_count"] = Double(values.peakCount)
    }

    private func addBaselinePlaceholders(features: inout [String: Double]) {
        for key in [
            "baseline_abs_delta_mean",
            "baseline_abs_delta_max",
            "baseline_feature_count",
            "baseline_missing",
            "state_cluster_id",
            "baseline_l2_delta",
            "baseline_anchor_available"
        ] {
            features[key, default: 0] = 0
        }

        for prefix in ["bvp__mean", "temperature__mean", "acc_x__mean", "acc_y__mean", "acc_z__mean", "acc__mag__mean"] {
            features["\(prefix)__baseline_mean", default: 0] = 0
            features["\(prefix)__baseline_std", default: 0] = 0
            features["\(prefix)__delta_from_baseline", default: 0] = 0
            features["\(prefix)__z_from_baseline", default: 0] = 0
        }
    }
}

private extension Array where Element == Double {
    var meanOrZero: Double {
        guard !isEmpty else { return 0 }
        return reduce(0, +) / Double(count)
    }

    var stdOrZero: Double {
        guard count > 1 else { return 0 }
        let mean = meanOrZero
        let variance = map { pow($0 - mean, 2) }.reduce(0, +) / Double(count - 1)
        return sqrt(variance)
    }

    var slopeOrZero: Double {
        guard count > 1 else { return 0 }
        return ((last ?? 0) - (first ?? 0)) / Double(count - 1)
    }

    var peakCount: Int {
        guard count > 2 else { return 0 }
        var count = 0
        for index in 1..<(self.count - 1) where self[index] > self[index - 1] && self[index] > self[index + 1] {
            count += 1
        }
        return count
    }
}
