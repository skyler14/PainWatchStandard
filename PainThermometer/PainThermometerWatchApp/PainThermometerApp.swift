import SwiftUI

@main
struct PainThermometerApp: App {
    @StateObject private var recorder = RecordingViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(recorder)
        }
    }
}
