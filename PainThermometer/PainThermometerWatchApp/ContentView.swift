import SwiftUI

private enum WatchTab {
    case main
    case baseline
    case questionnaire
    case charts
    case patient
}

struct ContentView: View {
    @EnvironmentObject private var recorder: RecordingViewModel
    @State private var selectedTab: WatchTab = .main

    var body: some View {
        Group {
            if recorder.selectedPatient == nil {
                PatientStartView()
            } else {
                TabView(selection: $selectedTab) {
                    MonitoringTab(selectedTab: $selectedTab)
                        .tag(WatchTab.main)
                    BaselineTab()
                        .tag(WatchTab.baseline)
                    QuestionnaireTab()
                        .tag(WatchTab.questionnaire)
                    ChartsTab()
                        .tag(WatchTab.charts)
                    PatientInfoTab()
                        .tag(WatchTab.patient)
                }
            }
        }
        .task {
            await recorder.prepare()
        }
    }
}

private struct PatientStartView: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("PainThermometer")
                    .font(.headline)

                Button {
                    Task { await recorder.createRandomPatientAndStart() }
                } label: {
                    Label("New Patient", systemImage: "person.crop.circle.badge.plus")
                }

                Text("Existing Patient")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                ForEach(recorder.patientsOnDevice) { patient in
                    Button {
                        Task { await recorder.selectPatientAndStart(patient) }
                    } label: {
                        HStack {
                            Image(systemName: "person.crop.circle")
                            Text(patient.displayName)
                                .lineLimit(1)
                        }
                    }
                }

                Text(recorder.status)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
    }
}

private struct MonitoringTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel
    @Binding var selectedTab: WatchTab

    var body: some View {
        ZStack {
            SyntheticBiasTopChrome(isEnabled: recorder.syntheticModeEnabled, value: $recorder.syntheticPainBias)

            FingerDragScrollView {
                VStack(spacing: 10) {
                    Toggle(isOn: $recorder.syntheticModeEnabled) {
                        Label(recorder.syntheticModeEnabled ? "Synthetic" : "Live", systemImage: recorder.syntheticModeEnabled ? "waveform.path.ecg" : "applewatch")
                    }
                    .font(.caption)

                    VStack(spacing: 4) {
                        Text(recorder.isRecording ? recorder.elapsedText : "Starting")
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
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
                    }
                    .frame(maxWidth: .infinity)

                    ScoreGrid(rows: recorder.scoreRows)

                    if recorder.questionnaireNoticeVisible, let session = recorder.questionnaireSessions.first {
                        Button {
                            recorder.openQuestionnaireSession(session)
                            selectedTab = .questionnaire
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Label("Pain session", systemImage: "bell.fill")
                                    .font(.caption)
                                Text(session.startedAtText)
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .tint(.orange)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Biosensors")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        ForEach(recorder.sensorRows) { row in
                            HStack {
                                Text(row.sensor.capitalized)
                                    .font(.caption2)
                                    .lineLimit(1)
                                Spacer()
                                Text("\(row.valueText) \(row.unitText)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }

                        if recorder.sensorRows.isEmpty {
                            Text("Waiting for readings")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }

                        Text("\(recorder.bufferText) · \(recorder.dropoutText)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    Button(role: .destructive) {
                        Task { await recorder.stop() }
                    } label: {
                        Label("Stop", systemImage: "stop.fill")
                    }
                    .disabled(!recorder.isRecording)
                }
                .padding()
            }
        }
    }
}

private struct FingerDragScrollView<Content: View>: View {
    @ViewBuilder let content: Content
    @State private var contentHeight: CGFloat = 0
    @State private var viewportHeight: CGFloat = 0
    @State private var offset: CGFloat = 0
    @State private var dragStartOffset: CGFloat = 0

    var body: some View {
        GeometryReader { proxy in
            content
                .frame(maxWidth: .infinity, alignment: .top)
                .background(
                    GeometryReader { contentProxy in
                        Color.clear.preference(key: FingerDragContentHeightKey.self, value: contentProxy.size.height)
                    }
                )
                .offset(y: clampedOffset(offset))
                .gesture(
                    DragGesture(minimumDistance: 4)
                        .onChanged { value in
                            viewportHeight = proxy.size.height
                            offset = clampedOffset(dragStartOffset + value.translation.height)
                        }
                        .onEnded { value in
                            viewportHeight = proxy.size.height
                            offset = clampedOffset(dragStartOffset + value.translation.height)
                            dragStartOffset = offset
                        }
                )
                .clipped()
                .onAppear {
                    viewportHeight = proxy.size.height
                    offset = clampedOffset(offset)
                    dragStartOffset = offset
                }
                .onChange(of: proxy.size.height) { height in
                    viewportHeight = height
                    offset = clampedOffset(offset)
                    dragStartOffset = offset
                }
        }
        .onPreferenceChange(FingerDragContentHeightKey.self) { height in
            contentHeight = height
            offset = clampedOffset(offset)
            dragStartOffset = offset
        }
    }

    private func clampedOffset(_ value: CGFloat) -> CGFloat {
        let minOffset = min(0, viewportHeight - contentHeight)
        return min(0, max(minOffset, value))
    }
}

private struct FingerDragContentHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

private struct SyntheticBiasTopChrome: View {
    let isEnabled: Bool
    @Binding var value: Double
    @FocusState private var crownFocused: Bool

    var body: some View {
        GeometryReader { proxy in
            VStack(spacing: 0) {
                Rectangle()
                    .fill(isEnabled ? Color.red.opacity(0.08 + clampedValue * 0.46) : Color.clear)
                    .frame(height: max(18, proxy.safeAreaInsets.top + 6))
                    .focusable(isEnabled)
                    .focused($crownFocused)
                    .digitalCrownRotation(
                        $value,
                        from: 0,
                        through: 1,
                        by: 0.04,
                        sensitivity: .medium,
                        isContinuous: false,
                        isHapticFeedbackEnabled: true
                    )
                Spacer(minLength: 0)
                    .allowsHitTesting(false)
            }
            .ignoresSafeArea(edges: .top)
        }
        .accessibilityHidden(true)
        .onAppear {
            crownFocused = isEnabled
        }
        .onChange(of: isEnabled) { enabled in
            crownFocused = enabled
        }
    }

    private var clampedValue: Double {
        min(max(value, 0), 1)
    }
}

private struct ScoreGrid: View {
    let rows: [ScoreDisplayRow]
    private let columns = [
        GridItem(.flexible(), spacing: 4),
        GridItem(.flexible(), spacing: 4)
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 4) {
            ForEach(rows.prefix(6)) { row in
                VStack(spacing: 2) {
                    Text(row.label)
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Text(row.valueText)
                        .font(.system(size: 12, design: .monospaced).bold())
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity, minHeight: 34)
                .background(Color.secondary.opacity(0.14))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            if rows.isEmpty {
                Text("Scores pending")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 34)
                    .background(Color.secondary.opacity(0.14))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
    }
}

private struct BaselineTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        List {
            Section {
                Text(recorder.baselineStatusText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            ForEach(recorder.baselineRows) { row in
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.label)
                        .font(.caption)
                    Text(row.valueText)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                    Text(row.detailText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct QuestionnaireTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        List {
            Section {
                Text("Questionnaire")
                    .font(.headline)
            }

            Section {
                if recorder.questionnaireSessions.isEmpty {
                    Text("No pain sessions yet")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(recorder.questionnaireSessions) { session in
                        QuestionnaireSessionCard(session: session)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button {
                                recorder.dismissQuestionnaireSession(session)
                            } label: {
                                Label("Dismiss", systemImage: "xmark")
                            }
                            .tint(.gray)

                            Button(role: .destructive) {
                                recorder.removeQuestionnaireSession(session)
                            } label: {
                                Label("Remove", systemImage: "trash")
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct QuestionnaireSessionCard: View {
    @EnvironmentObject private var recorder: RecordingViewModel
    let session: QuestionnaireSessionSummary

    private var isOpen: Bool {
        recorder.selectedQuestionnaireSessionID == session.id
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                recorder.openQuestionnaireSession(session)
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(session.startedAtText)
                            .font(.system(.caption, design: .monospaced))
                        Spacer()
                        Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Text("\(session.painText) · \(session.responseCount) responses")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("\(session.completionText) complete")
                        .font(.caption2)
                        .foregroundStyle(session.canSubmit ? .green : .secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)

            if isOpen {
                ForEach(recorder.dialogueMessages) { message in
                    DialogueBubble(message: message) {
                        if message.speaker == .system {
                            recorder.speakCurrentQuestion()
                        }
                    }
                }

                if recorder.isRecordingQuestionnaireResponse {
                    VStack(alignment: .leading, spacing: 6) {
                        VStack(alignment: .leading, spacing: 3) {
                            Label("Dictating", systemImage: "waveform")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(recorder.questionnaireResponseText.isEmpty ? "Listening..." : recorder.questionnaireResponseText)
                                .font(.caption)
                                .foregroundStyle(recorder.questionnaireResponseText.isEmpty ? .secondary : .primary)
                                .multilineTextAlignment(.leading)
                                .frame(maxWidth: .infinity, minHeight: 34, alignment: .topLeading)
                                .padding(6)
                                .background(Color.secondary.opacity(0.16), in: RoundedRectangle(cornerRadius: 6))
                        }
                        ProgressView(value: recorder.responseSilenceProgress)
                            .progressViewStyle(.linear)
                        Button {
                            recorder.stopQuestionnaireResponseRecording()
                        } label: {
                            Label(
                                recorder.questionnaireResponseText.isEmpty ? "Stop" : "Send",
                                systemImage: recorder.questionnaireResponseText.isEmpty ? "stop.fill" : "paperplane.fill"
                            )
                        }
                    }
                } else {
                    HStack {
                        Button {
                            recorder.startQuestionnaireResponseRecording()
                        } label: {
                            Label("Start Now", systemImage: "mic.fill")
                        }

                        if session.canSubmit {
                            Button {
                                recorder.submitActiveQuestionnaire()
                            } label: {
                                Label("Submit", systemImage: "checkmark.circle.fill")
                            }
                            .tint(.green)
                        }
                    }
                }

                Text(recorder.voiceStatusText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct DialogueBubble: View {
    let message: QuestionnaireDialogueMessage
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: message.speaker == .system ? .leading : .trailing, spacing: 2) {
                Text(message.text)
                    .font(message.speaker == .system ? .caption : .body)
                    .multilineTextAlignment(message.speaker == .system ? .leading : .trailing)
                Text(message.timeText)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .padding(6)
            .frame(maxWidth: .infinity, alignment: message.speaker == .system ? .leading : .trailing)
            .background(message.speaker == .system ? Color.secondary.opacity(0.12) : Color.blue.opacity(0.22))
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
    }
}

private struct ChartsTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        VStack(spacing: 6) {
            BufferChart(title: "Sensors", points: recorder.sensorChartPoints)
                .frame(maxHeight: .infinity)
            BufferChart(title: "Scores", points: recorder.scoreChartPoints)
                .frame(maxHeight: .infinity)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }
}

private struct BufferChart: View {
    let title: String
    let points: [BufferChartPoint]

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.secondary.opacity(0.10))

                ChartLines(points: points)
                    .padding(.top, 18)
                    .padding(.trailing, 44)
                    .padding(.bottom, 8)
                    .padding(.leading, 4)

                VStack(alignment: .trailing, spacing: 2) {
                    ForEach(seriesNames, id: \.self) { sensor in
                        Text(displayName(for: sensor))
                            .font(.system(size: 7))
                            .foregroundStyle(bufferChartColor(for: sensor))
                            .lineLimit(1)
                    }
                }
                .frame(width: 40, alignment: .trailing)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
                .padding(.trailing, 4)
                .padding(.top, 18)

                VStack(alignment: .leading, spacing: 0) {
                    Text(title)
                        .font(.system(size: 9))
                    Text(points.first?.timeText ?? "--:--:--")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                .padding(4)
            }
        }
    }

    private var seriesNames: [String] {
        Array(Set(points.map(\.sensor))).sorted().prefix(5).map { $0 }
    }

    private func displayName(for sensor: String) -> String {
        switch sensor {
        case "heart_rate": return "HR"
        case "respiratory_rate": return "Resp"
        case "oxygen_saturation": return "SpO2"
        case "wrist_temperature": return "Temp"
        case "body_temperature": return "Body"
        case "accelerometer", "device_motion_acceleration": return "Accel"
        case "gyroscope": return "Gyro"
        case "pain_score": return "Pain"
        default:
            return sensor
                .split(separator: "_")
                .map { $0.prefix(4) }
                .joined(separator: " ")
        }
    }
}

private struct ChartLines: View {
    let points: [BufferChartPoint]

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                ForEach(series, id: \.sensor) { item in
                    Path { path in
                        guard let first = item.indexedPoints.first else { return }
                        path.move(to: chartPoint(first, in: proxy.size))
                        for point in item.indexedPoints.dropFirst() {
                            path.addLine(to: chartPoint(point, in: proxy.size))
                        }
                    }
                    .stroke(bufferChartColor(for: item.sensor), style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))

                    ForEach(item.indexedPoints) { point in
                        Circle()
                            .fill(bufferChartColor(for: item.sensor))
                            .frame(width: 2.5, height: 2.5)
                            .position(chartPoint(point, in: proxy.size))
                    }
                }
            }
        }
    }

    private var series: [ChartSeries] {
        let indexed = points.enumerated().map { offset, point in
            IndexedChartPoint(id: point.id, index: offset, point: point)
        }
        return Dictionary(grouping: indexed, by: { $0.point.sensor })
            .map { sensor, indexedPoints in
                ChartSeries(sensor: sensor, indexedPoints: indexedPoints.sorted { $0.index < $1.index })
            }
            .sorted { $0.sensor < $1.sensor }
    }

    private func chartPoint(_ indexedPoint: IndexedChartPoint, in size: CGSize) -> CGPoint {
        let denominator = max(points.count - 1, 1)
        let x = size.width * CGFloat(indexedPoint.index) / CGFloat(denominator)
        let y = size.height * (1 - CGFloat(min(max(indexedPoint.point.normalizedValue, 0), 1)))
        return CGPoint(x: x, y: y)
    }

}

private func bufferChartColor(for sensor: String) -> Color {
    switch sensor {
    case "heart_rate", "pain_score": return .red
    case "respiratory_rate": return .blue
    case "oxygen_saturation": return .cyan
    case "wrist_temperature", "body_temperature": return .orange
    case "accelerometer", "device_motion_acceleration": return .green
    case "gyroscope": return .purple
    default: return .secondary
    }
}

private struct ChartSeries {
    let sensor: String
    let indexedPoints: [IndexedChartPoint]
}

private struct IndexedChartPoint: Identifiable {
    let id: UUID
    let index: Int
    let point: BufferChartPoint
}

private struct PatientInfoTab: View {
    @EnvironmentObject private var recorder: RecordingViewModel

    var body: some View {
        List {
            VStack(alignment: .leading, spacing: 3) {
                Text(recorder.selectedPatient?.displayName ?? "Patient")
                    .font(.headline)
                Text(recorder.status)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(recorder.isRecording ? "Monitoring \(recorder.elapsedText)" : "Not recording")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(recorder.questionnaireText)
                    .font(.caption2)
                    .foregroundStyle(recorder.painDetectedMode ? .orange : .secondary)
            }
        }
    }
}
