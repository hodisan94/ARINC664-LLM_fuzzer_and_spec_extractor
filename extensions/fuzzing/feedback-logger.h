#ifndef FEEDBACK_LOGGER_H
#define FEEDBACK_LOGGER_H

#include <string>
#include <vector>
#include <fstream>
#include <cstdint>

namespace ns3 {

struct FeedbackEntry {
    double ts;                          // Actual send time
    uint16_t vl_id;                     // Virtual Link ID
    uint32_t len_bytes;                 // Frame length in bytes
    uint16_t seq;                       // Sequence number
    uint32_t bag_ms;                    // BAG in milliseconds
    std::vector<std::string> violations; // Array of violation strings
    int score;                          // Numeric score (0-100)
    std::string rule_version;           // Rule version identifier
};

/**
 * Logs frame feedback in JSONL format for external fuzzer consumption.
 * Each line is a complete JSON object representing one frame's feedback.
 */
class FeedbackLogger
{
public:
    explicit FeedbackLogger(const std::string& outputDir);
    ~FeedbackLogger();
    
    /**
     * Log feedback for a transmitted frame.
     * @param entry Complete feedback entry to log
     */
    void LogFrame(const FeedbackEntry& entry);
    
    /**
     * Start a new feedback session with a specific run ID.
     * @param runId Unique identifier for this fuzzing session
     */
    void StartSession(const std::string& runId);
    
    /**
     * End the current session and close the log file.
     */
    void EndSession();
    
private:
    std::string m_outputDir;
    std::string m_currentRunId;
    std::ofstream m_logFile;
    
    std::string GetLogFilePath(const std::string& runId) const;
    std::string ViolationsToJsonArray(const std::vector<std::string>& violations) const;
};

} // namespace ns3

#endif // FEEDBACK_LOGGER_H
