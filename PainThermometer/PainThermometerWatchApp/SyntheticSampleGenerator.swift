import Foundation

struct SyntheticSampleGenerator: Sendable {
    private var heartRate = 74.0
    private var respiratoryRate = 15.0
    private var oxygenSaturation = 0.975
    private var wristTemperature = 33.1
    private var motion = 0.08

    mutating func samples(run: RecordingRun, painBias: Double) -> [SensorSampleRow] {
        let bias = min(1, max(0, painBias))
        heartRate = walk(heartRate, target: 74 + 28 * bias, step: 2.4)
        respiratoryRate = walk(respiratoryRate, target: 15 + 7 * bias, step: 0.7)
        oxygenSaturation = walk(oxygenSaturation, target: 0.976 - 0.018 * bias, step: 0.002)
        wristTemperature = walk(wristTemperature, target: 33.1 + 0.45 * bias, step: 0.04)
        motion = walk(motion, target: 0.08 + 0.18 * bias, step: 0.03)

        let now = Date()
        let offset = now.timeIntervalSince(run.startedAt)
        return [
            scalar(run: run, now: now, offset: offset, sensor: "heart_rate", unit: "count/min", value: heartRate, bias: bias),
            scalar(run: run, now: now, offset: offset, sensor: "respiratory_rate", unit: "count/min", value: respiratoryRate, bias: bias),
            scalar(run: run, now: now, offset: offset, sensor: "oxygen_saturation", unit: "%", value: oxygenSaturation, bias: bias),
            scalar(run: run, now: now, offset: offset, sensor: "wrist_temperature", unit: "degC", value: wristTemperature, bias: bias),
            vector(run: run, now: now, offset: offset, sensor: "accelerometer", unit: "g", scale: motion, bias: bias),
            vector(run: run, now: now, offset: offset, sensor: "gyroscope", unit: "rad/s", scale: motion * 0.6, bias: bias)
        ]
    }

    private mutating func walk(_ value: Double, target: Double, step: Double) -> Double {
        let pull = (target - value) * 0.18
        let noise = Double.random(in: -step...step)
        return value + pull + noise
    }

    private func scalar(
        run: RecordingRun,
        now: Date,
        offset: TimeInterval,
        sensor: String,
        unit: String,
        value: Double,
        bias: Double
    ) -> SensorSampleRow {
        SensorSampleRow(
            runID: run.id,
            sampleTimeUTC: now,
            sampleOffsetS: offset,
            sensor: sensor,
            unit: unit,
            value: value,
            x: nil,
            y: nil,
            z: nil,
            accuracy: nil,
            source: "synthetic_random_walk",
            metadata: ["pain_bias": String(format: "%.2f", bias)]
        )
    }

    private func vector(
        run: RecordingRun,
        now: Date,
        offset: TimeInterval,
        sensor: String,
        unit: String,
        scale: Double,
        bias: Double
    ) -> SensorSampleRow {
        SensorSampleRow(
            runID: run.id,
            sampleTimeUTC: now,
            sampleOffsetS: offset,
            sensor: sensor,
            unit: unit,
            value: nil,
            x: Double.random(in: -scale...scale),
            y: Double.random(in: -scale...scale),
            z: Double.random(in: -scale...scale),
            accuracy: nil,
            source: "synthetic_random_walk",
            metadata: ["pain_bias": String(format: "%.2f", bias)]
        )
    }
}
