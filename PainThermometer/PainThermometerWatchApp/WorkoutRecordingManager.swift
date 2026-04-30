import Foundation
import HealthKit

final class WorkoutRecordingManager: NSObject {
    let run: RecordingRun

    private let healthStore: HKHealthStore
    private let store: RunStore
    private let onSample: (SensorSampleRow) -> Void
    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?

    init(
        healthStore: HKHealthStore,
        run: RecordingRun,
        store: RunStore,
        onSample: @escaping (SensorSampleRow) -> Void = { _ in }
    ) {
        self.healthStore = healthStore
        self.run = run
        self.store = store
        self.onSample = onSample
        super.init()
    }

    func start() async throws {
        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .other
        configuration.locationType = .unknown

        let session = try HKWorkoutSession(healthStore: healthStore, configuration: configuration)
        let builder = session.associatedWorkoutBuilder()
        builder.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore, workoutConfiguration: configuration)
        builder.delegate = self

        self.session = session
        self.builder = builder

        session.startActivity(with: run.startedAt)
        try await builder.beginCollection(at: run.startedAt)
    }

    func stop() async {
        let endedAt = Date()
        session?.end()
        await withCheckedContinuation { continuation in
            builder?.endCollection(withEnd: endedAt) { [weak self] _, _ in
                self?.builder?.finishWorkout { _, _ in
                    continuation.resume()
                }
            }
        }
    }

    private func appendStatistic(for quantityType: HKQuantityType) {
        guard let builder, let statistics = builder.statistics(for: quantityType) else { return }

        let unit: HKUnit
        let sensor: String
        let quantity: HKQuantity?

        switch quantityType.identifier {
        case HKQuantityTypeIdentifier.heartRate.rawValue:
            unit = HKUnit.count().unitDivided(by: .minute())
            sensor = "heart_rate"
            quantity = statistics.mostRecentQuantity()
        case HKQuantityTypeIdentifier.activeEnergyBurned.rawValue:
            unit = .kilocalorie()
            sensor = "active_energy"
            quantity = statistics.sumQuantity()
        case HKQuantityTypeIdentifier.basalEnergyBurned.rawValue:
            unit = .kilocalorie()
            sensor = "basal_energy"
            quantity = statistics.sumQuantity()
        case HKQuantityTypeIdentifier.distanceWalkingRunning.rawValue:
            unit = .meter()
            sensor = "distance_walking_running"
            quantity = statistics.sumQuantity()
        default:
            return
        }

        guard let quantity else { return }
        let now = Date()
        let row = SensorSampleRow(
            runID: run.id,
            sampleTimeUTC: now,
            sampleOffsetS: now.timeIntervalSince(run.startedAt),
            sensor: sensor,
            unit: unit.unitString,
            value: quantity.doubleValue(for: unit),
            x: nil,
            y: nil,
            z: nil,
            accuracy: nil,
            source: "healthkit_live_workout",
            metadata: [:]
        )
        Task { try? await store.append(row) }
        onSample(row)
    }
}

extension WorkoutRecordingManager: HKLiveWorkoutBuilderDelegate {
    func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf collectedTypes: Set<HKSampleType>) {
        for sampleType in collectedTypes {
            guard let quantityType = sampleType as? HKQuantityType else { continue }
            appendStatistic(for: quantityType)
        }
    }

    func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}
}
