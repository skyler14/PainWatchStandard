import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        TabView {
            RecordingTab()
            SensorsTab()
            ScoresTab()
        }
        .task {
            await recorder.prepare()
        }
    }
}

private struct RecordingTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel
    @FocusState private var crownFocused: Bool

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
                Text(recorder.bufferText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Text(recorder.questionnaireText)
                    .font(.caption2)
                    .foregroundStyle(recorder.painDetectedMode ? .orange : .secondary)
                    .lineLimit(1)
                Text(recorder.voiceStatusText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            VStack(spacing: 4) {
                TextField("Endpoint", text: $recorder.endpointURLText)
                SecureField("Token", text: $recorder.bearerTokenText)
                Toggle("Live", isOn: $recorder.liveUploadEnabled)
                Toggle("Local ML", isOn: $recorder.localModelEnabled)
                Picker("Signal", selection: $recorder.signalMode) {
                    ForEach(SignalMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                Toggle("Synthetic", isOn: $recorder.syntheticModeEnabled)
                if recorder.syntheticModeEnabled {
                    Text("Bias \(Int(recorder.syntheticPainBias * 100))")
                        .font(.system(.caption2, design: .monospaced))
                        .focusable(true)
                        .focused($crownFocused)
                        .digitalCrownRotation(
                            $recorder.syntheticPainBias,
                            from: 0,
                            through: 1,
                            by: 0.05,
                            sensitivity: .medium,
                            isContinuous: false,
                            isHapticFeedbackEnabled: true
                        )
                }
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

            HStack {
                Button {
                    recorder.speakCurrentQuestion()
                } label: {
                    Image(systemName: "speaker.wave.2")
                }

                Button {
                    recorder.startListening()
                } label: {
                    Image(systemName: "mic")
                }
            }
        }
        .padding()
        .onChange(of: recorder.syntheticModeEnabled) { _, enabled in
            crownFocused = enabled
        }
    }
}

private struct SensorsTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        List {
            Section {
                Text(recorder.bufferText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            ForEach(recorder.sensorRows) { row in
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.sensor.capitalized)
                        .font(.caption)
                    Text("\(row.valueText) \(row.unitText)")
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                    Text("n=\(row.countText) \(row.updatedText)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if recorder.sensorRows.isEmpty {
                Text("No samples")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct ScoresTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        List {
            Section {
                Text(recorder.questionnaireText)
                    .font(.caption2)
                    .foregroundStyle(recorder.painDetectedMode ? .orange : .secondary)
            }

            ForEach(recorder.scoreRows) { row in
                HStack {
                    Text(row.label)
                        .font(.caption2)
                    Spacer()
                    Text(row.valueText)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }

            if recorder.scoreRows.isEmpty {
                Text("No scores")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
