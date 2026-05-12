import CoreML
import Foundation

actor LocalCoreMLPainScorer {
    private let modelResourceNames = [
        "watch_friendly_linear_svc",
        "watch_friendly_svc_linear",
        "watch_friendly_svc_rbf",
        "watch_friendly_decision_tree_depth3",
        "watch_friendly_decision_tree_depth6",
        "watch_friendly_random_forest_50_depth6",
        "watch_friendly_random_forest_100_depth8",
        "watch_friendly_gradient_boosting_50_depth2",
        "watch_friendly_gradient_boosting_100_depth2"
    ]
    private var models: [MLModel]?

    func reset() {
        models = nil
    }

    func score(_ window: FeatureWindow, enabled: Bool) async -> ScoreResult? {
        guard enabled else { return nil }
        let loadedModels = loadModels()
        guard !loadedModels.isEmpty else { return nil }

        var painLikelihoods: [Double] = []
        for model in loadedModels {
            let providerValues = model.modelDescription.inputDescriptionsByName.keys.reduce(into: [String: MLFeatureValue]()) { partialResult, featureName in
                partialResult[featureName] = MLFeatureValue(double: window.features[featureName] ?? 0)
            }

            guard
                let provider = try? MLDictionaryFeatureProvider(dictionary: providerValues),
                let output = try? await model.prediction(from: provider),
                let likelihood = output.probabilityForPositiveClass()
            else {
                continue
            }
            painLikelihoods.append(likelihood)
        }

        guard !painLikelihoods.isEmpty else { return nil }
        let rawPainLikelihood = painLikelihoods.reduce(0, +) / Double(painLikelihoods.count)
        let painLikelihood = calibrateWatchPainLikelihood(rawPainLikelihood)
        let quality = qualityScore(from: window.dropoutSignals)
        let confidence = min(0.95, max(0.05, 0.5 * quality + abs(painLikelihood - 0.5)))

        return ScoreResult(
            scoreName: "local_coreml_watch_ensemble",
            painLikelihood01: painLikelihood,
            painScore0100: painLikelihood * 100,
            painDetected: painLikelihood >= 0.65 && confidence >= 0.50 && quality >= 0.60,
            confidence01: confidence,
            quality01: quality,
            stressLikelihood01: nil,
            baselineDeparture01: nil,
            windowStartUTC: window.windowStartUTC,
            windowEndUTC: window.windowEndUTC,
            modelVersion: "pain-thermometer-dropout-ensemble/watch_friendly_calibrated_v1",
            dropoutSignals: window.dropoutSignals
        )
    }

    private func loadModels() -> [MLModel] {
        if let models {
            return models
        }
        let loaded = modelResourceNames.compactMap { name -> MLModel? in
            guard let url = Bundle.main.url(forResource: name, withExtension: "mlmodelc") else {
                return nil
            }
            return try? MLModel(contentsOf: url)
        }
        models = loaded
        return loaded
    }

    private func qualityScore(from dropoutSignals: [DropoutSignal]) -> Double {
        let missingCount = dropoutSignals.filter { $0.present == false || ($0.validFrac ?? 1) <= 0 }.count
        return min(1, max(0.2, 1 - 0.07 * Double(missingCount)))
    }

    private func calibrateWatchPainLikelihood(_ raw: Double) -> Double {
        let clamped = min(1, max(0, raw))
        if clamped <= 0.62 {
            return clamped * 0.45
        }
        if clamped <= 0.84 {
            let t = (clamped - 0.62) / 0.22
            return 0.28 + pow(t, 1.15) * 0.47
        }
        let t = (clamped - 0.84) / 0.16
        return min(0.99, 0.75 + t * 0.24)
    }
}

private extension MLFeatureProvider {
    func doubleValue(_ name: String) -> Double? {
        featureValue(for: name)?.doubleValue
    }

    func probabilityForPositiveClass() -> Double? {
        guard let dictionary = featureValue(for: "pain_scores")?.dictionaryValue else {
            return nil
        }
        for (key, value) in dictionary {
            if "\(key)" == "1" || "\(key)" == "1.0" || "\(key)" == "true" {
                return value.doubleValue
            }
        }
        return dictionary.values.map(\.doubleValue).max()
    }
}
