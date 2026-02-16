#include "feedback-logger.h"
#include "ns3/log.h"
#include <iomanip>
#include <sstream>

NS_LOG_COMPONENT_DEFINE("FeedbackLogger");

namespace ns3 {

FeedbackLogger::FeedbackLogger(const std::string& outputDir)
    : m_outputDir(outputDir)
{
}

FeedbackLogger::~FeedbackLogger()
{
    EndSession();
}

void FeedbackLogger::StartSession(const std::string& runId)
{
    EndSession(); // Close any existing session
    
    m_currentRunId = runId;
    std::string logPath = GetLogFilePath(runId);
    
    m_logFile.open(logPath, std::ios::out | std::ios::trunc);
    if (!m_logFile.is_open()) {
        NS_LOG_ERROR("Failed to open feedback log file: " << logPath);
    } else {
        NS_LOG_INFO("Started feedback session: " << runId << " -> " << logPath);
    }
}

void FeedbackLogger::EndSession()
{
    if (m_logFile.is_open()) {
        m_logFile.close();
        NS_LOG_INFO("Ended feedback session: " << m_currentRunId);
    }
    m_currentRunId.clear();
}

void FeedbackLogger::LogFrame(const FeedbackEntry& entry)
{
    if (!m_logFile.is_open()) {
        NS_LOG_WARN("No active feedback session - cannot log frame");
        return;
    }
    
    // Create JSONL entry (one JSON object per line)
    std::ostringstream json;
    json << std::fixed << std::setprecision(6);
    
    json << "{";
    json << "\"ts\":" << entry.ts << ",";
    json << "\"vl_id\":" << entry.vl_id << ",";
    json << "\"len_bytes\":" << entry.len_bytes << ",";
    json << "\"seq\":" << entry.seq << ",";
    json << "\"bag_ms\":" << entry.bag_ms << ",";
    json << "\"violations\":" << ViolationsToJsonArray(entry.violations) << ",";
    json << "\"score\":" << entry.score << ",";
    json << "\"rule_version\":\"" << entry.rule_version << "\"";
    json << "}";
    
    m_logFile << json.str() << std::endl;
    m_logFile.flush(); // Ensure immediate write for external consumers
}

std::string FeedbackLogger::GetLogFilePath(const std::string& runId) const
{
    return m_outputDir + "/fb_" + runId + ".jsonl";
}

std::string FeedbackLogger::ViolationsToJsonArray(const std::vector<std::string>& violations) const
{
    if (violations.empty()) {
        return "[]";
    }
    
    std::ostringstream json;
    json << "[";
    for (size_t i = 0; i < violations.size(); ++i) {
        if (i > 0) json << ",";
        json << "\"" << violations[i] << "\"";
    }
    json << "]";
    return json.str();
}

} // namespace ns3
