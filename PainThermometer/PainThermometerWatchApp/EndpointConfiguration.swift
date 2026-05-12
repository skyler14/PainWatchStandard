import Foundation

struct EndpointSettings: Equatable, Sendable {
    var baseURLString: String
    var bearerToken: String
    var liveFeedEnabled: Bool
    var localModelEnabled: Bool

    var baseURL: URL? {
        let trimmed = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return URL(string: trimmed)
    }

    var uploadConfiguration: UploadConfiguration {
        UploadConfiguration(
            baseURL: baseURL,
            bearerToken: bearerToken.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        )
    }

    static func load() -> EndpointSettings {
        let defaults = UserDefaults.standard
        return EndpointSettings(
            baseURLString: defaults.string(forKey: Keys.baseURLString) ?? BuiltInEndpoint.baseURLString,
            bearerToken: defaults.string(forKey: Keys.bearerToken) ?? BuiltInEndpoint.bearerToken,
            liveFeedEnabled: defaults.object(forKey: Keys.liveFeedEnabled) as? Bool ?? false,
            localModelEnabled: defaults.object(forKey: Keys.localModelEnabled) as? Bool ?? true
        )
    }

    func save() {
        let defaults = UserDefaults.standard
        defaults.set(baseURLString, forKey: Keys.baseURLString)
        defaults.set(bearerToken, forKey: Keys.bearerToken)
        defaults.set(liveFeedEnabled, forKey: Keys.liveFeedEnabled)
        defaults.set(localModelEnabled, forKey: Keys.localModelEnabled)
    }

    private enum Keys {
        static let baseURLString = "PainThermometerEndpointBaseURL"
        static let bearerToken = "PainThermometerEndpointBearerToken"
        static let liveFeedEnabled = "PainThermometerLiveFeedEnabled"
        static let localModelEnabled = "PainThermometerLocalModelEnabled"
    }
}

private enum BuiltInEndpoint {
    static let baseURLString = "https://pain-thermometer-po.web.app"
    static let bearerToken = ""
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
