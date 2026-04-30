import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        VStack(spacing: 10) {
            Text(recorder.isRecording ? "Recording" : "PainThermometer")
                .font(.headline)

            VStack(spacing: 4) {
                Text(recorder.elapsedText)
                    .font(.system(.title2, design: .monospaced))
                Text(recorder.painActivationText)
                    .font(.caption)
                    .foregroundStyle(recorder.painDetectedMode ? .red : .secondary)
                HStack(spacing: 2) {
                    ForEach(0..<10, id: \.self) { index in
                        RoundedRectangle(cornerRadius: 1)
                            .fill(index < recorder.painActivationCount ? Color.red : Color.secondary.opacity(0.25))
                            .frame(width: 8, height: 6)
                    }
                }
                Text(recorder.status)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                Text(recorder.dropoutText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            VStack(spacing: 4) {
                TextField("Endpoint", text: $recorder.endpointURLText)
                SecureField("Token", text: $recorder.bearerTokenText)
                Toggle("Live", isOn: $recorder.liveUploadEnabled)
                Toggle("Local ML", isOn: $recorder.localModelEnabled)
            }
            .font(.caption2)

            if recorder.isRecording {
                Button(role: .destructive) {
                    Task { await recorder.stop() }
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
            } else {
                Button {
                    Task { await recorder.start() }
                } label: {
                    Label("Start", systemImage: "record.circle")
                }
            }

            Button {
                Task { await recorder.connectEndpoint() }
            } label: {
                Label("Connect", systemImage: "antenna.radiowaves.left.and.right")
            }
            .disabled(recorder.isRecording)

            Button {
                Task { await recorder.uploadPending() }
            } label: {
                Label("Upload", systemImage: "arrow.up.circle")
            }
            .disabled(recorder.isRecording)
        }
        .padding()
        .task {
            await recorder.prepare()
        }
    }
}
