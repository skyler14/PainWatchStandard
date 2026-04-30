import CoreML
import Foundation

actor LocalCoreMLPainScorer {
    private var model: MLModel?

    func reset() {
        model = nil
    }

    func score(_ window: FeatureWindow, enabled: Bool) async -> ScoreResult? {
        guard enabled else { return nil }
        guard let model = loadModel() else { return nil }

        let providerValues = window.features.reduce(into: [String: MLFeatureValue]()) { partialResult, item in
            partialResult[item.key] = MLFeatureValue(double: item.value)
        }

        guard
            let provider = try? MLDictionaryFeatureProvider(dictionary: providerValues),
            let output = try? await model.prediction(from: provider)
        else {
            return nil
        }

        return ScoreResult(
            scoreName: "local_coreml",
            painLikelihood01: output.doubleValue("pain_likelihood_0_1"),
            painScore0100: output.doubleValue("pain_score_0_100"),
            painDetected: output.doubleValue("pain_flag").map { $0 >= 0.5 },
            confidence01: output.doubleValue("confidence_0_1"),
            quality01: output.doubleValue("quality_0_1"),
            stressLikelihood01: output.doubleValue("stress_likelihood_0_1"),
            baselineDeparture01: output.doubleValue("baseline_departure_0_1"),
            windowStartUTC: window.windowStartUTC,
            windowEndUTC: window.windowEndUTC,
            modelVersion: "pain-thermometer-phase3-final-v1",
            dropoutSignals: window.dropoutSignals
        )
    }

    private func loadModel() -> MLModel? {
        if let model {
            return model
        }
        guard let url = Bundle.main.url(forResource: "PainThermometerPhase3Final", withExtension: "mlmodelc") else {
            return nil
        }
        model = try? MLModel(contentsOf: url)
        return model
    }
}

private extension MLFeatureProvider {
    func doubleValue(_ name: String) -> Double? {
        featureValue(for: name)?.doubleValue
    }
}
