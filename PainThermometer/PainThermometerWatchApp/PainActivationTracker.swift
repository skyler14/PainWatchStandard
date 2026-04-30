import Foundation

struct PainActivationSnapshot: Sendable {
    let positiveCount: Int
    let windowCount: Int
    let thresholdCount: Int
    let isActive: Bool
}

struct PainActivationTracker {
    private var windows: [Bool] = []
    private let windowCount: Int
    private let thresholdCount: Int

    init(windowCount: Int = 10, thresholdCount: Int = 7) {
        self.windowCount = windowCount
        self.thresholdCount = thresholdCount
    }

    mutating func append(_ score: ScoreResult) -> PainActivationSnapshot {
        windows.append(score.activatesPainWindow)
        if windows.count > windowCount {
            windows.removeFirst(windows.count - windowCount)
        }
        return snapshot
    }

    mutating func configure(windowCount: Int?, thresholdCount: Int?) {
        let nextWindowCount = max(1, windowCount ?? self.windowCount)
        let nextThresholdCount = max(1, thresholdCount ?? self.thresholdCount)
        if windows.count > nextWindowCount {
            windows.removeFirst(windows.count - nextWindowCount)
        }
        self = PainActivationTracker(windowCount: nextWindowCount, thresholdCount: nextThresholdCount, windows: windows)
    }

    var snapshot: PainActivationSnapshot {
        let positiveCount = windows.filter { $0 }.count
        return PainActivationSnapshot(
            positiveCount: positiveCount,
            windowCount: windowCount,
            thresholdCount: thresholdCount,
            isActive: positiveCount >= thresholdCount
        )
    }

    private init(windowCount: Int, thresholdCount: Int, windows: [Bool]) {
        self.windowCount = windowCount
        self.thresholdCount = thresholdCount
        self.windows = windows
    }
}
