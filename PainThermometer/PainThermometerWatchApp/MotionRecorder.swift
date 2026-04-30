import CoreMotion
import Foundation

final class MotionRecorder {
    private let manager = CMMotionManager()
    private let queue = OperationQueue()
    private let run: RecordingRun
    private let store: RunStore
    private let onSample: (SensorSampleRow) -> Void

    init(run: RecordingRun, store: RunStore, onSample: @escaping (SensorSampleRow) -> Void = { _ in }) {
        self.run = run
        self.store = store
        self.onSample = onSample
        queue.name = "PainThermometer.MotionRecorder"
        queue.qualityOfService = .utility
    }

    func start() {
        if manager.isAccelerometerAvailable {
            manager.accelerometerUpdateInterval = 1.0 / 25.0
            manager.startAccelerometerUpdates(to: queue) { [weak self] data, _ in
                guard let self, let data else { return }
                self.append(
                    sensor: "accelerometer",
                    unit: "g",
                    x: data.acceleration.x,
                    y: data.acceleration.y,
                    z: data.acceleration.z,
                    source: "coremotion_accelerometer"
                )
            }
        }

        if manager.isDeviceMotionAvailable {
            manager.deviceMotionUpdateInterval = 1.0 / 25.0
            manager.startDeviceMotionUpdates(to: queue) { [weak self] data, _ in
                guard let self, let data else { return }
                self.append(
                    sensor: "device_motion_acceleration",
                    unit: "g",
                    x: data.userAcceleration.x,
                    y: data.userAcceleration.y,
                    z: data.userAcceleration.z,
                    source: "coremotion_device_motion"
                )
            }
        }

        if manager.isGyroAvailable {
            manager.gyroUpdateInterval = 1.0 / 25.0
            manager.startGyroUpdates(to: queue) { [weak self] data, _ in
                guard let self, let data else { return }
                self.append(
                    sensor: "gyroscope",
                    unit: "rad/s",
                    x: data.rotationRate.x,
                    y: data.rotationRate.y,
                    z: data.rotationRate.z,
                    source: "coremotion_gyroscope"
                )
            }
        }
    }

    func stop() {
        manager.stopAccelerometerUpdates()
        manager.stopDeviceMotionUpdates()
        manager.stopGyroUpdates()
    }

    private func append(sensor: String, unit: String, x: Double, y: Double, z: Double, source: String) {
        let now = Date()
        let row = SensorSampleRow(
            runID: run.id,
            sampleTimeUTC: now,
            sampleOffsetS: now.timeIntervalSince(run.startedAt),
            sensor: sensor,
            unit: unit,
            value: nil,
            x: x,
            y: y,
            z: z,
            accuracy: nil,
            source: source,
            metadata: [:]
        )
        Task { try? await store.append(row) }
        onSample(row)
    }
}
