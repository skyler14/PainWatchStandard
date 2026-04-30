import Foundation

actor RunStore {
    private let encoder = JSONEncoder.painThermometer
    private let fileManager = FileManager.default
    private let runsDirectory: URL
    private let uploadedDirectory: URL

    init() {
        let documents = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
        runsDirectory = documents.appendingPathComponent("runs", isDirectory: true)
        uploadedDirectory = documents.appendingPathComponent("uploaded", isDirectory: true)
    }

    func begin(run: RecordingRun) throws {
        try ensureDirectories()
        let row = RunHeaderRow(
            runID: run.id,
            deviceID: run.deviceID,
            startedAt: run.startedAt,
            sensorBlocksRequested: SensorCatalog.requestedBlocks
        )
        try write(row, to: run.id)
    }

    func append(_ row: SensorSampleRow) throws {
        try write(row, to: row.runID)
    }

    func finish(runID: UUID, endedAt: Date) throws {
        try write(RunEndRow(runID: runID, endedAt: endedAt), to: runID)
    }

    func pendingRunFiles() throws -> [URL] {
        try ensureDirectories()
        return try fileManager.contentsOfDirectory(at: runsDirectory, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "jsonl" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    func markUploaded(_ file: URL) throws {
        try ensureDirectories()
        let destination = uploadedDirectory.appendingPathComponent(file.lastPathComponent)
        if fileManager.fileExists(atPath: destination.path) {
            try fileManager.removeItem(at: destination)
        }
        try fileManager.moveItem(at: file, to: destination)
    }

    private func write<T: Encodable>(_ row: T, to runID: UUID) throws {
        let data = try encoder.encode(row)
        try append(data: data, to: runID)
    }

    private func append(data: Data, to runID: UUID) throws {
        try ensureDirectories()
        let url = runsDirectory.appendingPathComponent("\(runID.uuidString).jsonl")
        if !fileManager.fileExists(atPath: url.path) {
            fileManager.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
        try handle.write(contentsOf: Data("\n".utf8))
    }

    private func ensureDirectories() throws {
        try fileManager.createDirectory(at: runsDirectory, withIntermediateDirectories: true, attributes: nil)
        try fileManager.createDirectory(at: uploadedDirectory, withIntermediateDirectories: true, attributes: nil)
    }
}
