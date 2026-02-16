#ifndef FILE_QUEUE_READER_H
#define FILE_QUEUE_READER_H

#include "payload-provider.h"
#include "feedback-logger.h"
#include "violation-checker.h"
#include <string>
#include <vector>
#include <queue>
#include <memory>

namespace ns3 {

struct InjectedFrame {
    double time;        // Simulation time to send frame
    uint16_t seq;       // Sequence number
    uint32_t bag_ms;    // BAG in milliseconds
    std::string payload_hex;  // Payload as hex string
};

struct InjectedSequence {
    uint16_t vl_id;
    std::vector<InjectedFrame> frames;
};

/**
 * PayloadProvider implementation that reads JSON sequence files from a queue directory.
 * Processes files in order, schedules frames by their timing, and archives processed files.
 */
class FileQueueReader : public PayloadProvider
{
public:
    FileQueueReader(const std::string& inputDir, 
                   const std::string& outputDir,
                   const std::string& archiveDir,
                   const std::string& rulesFile);
    
    virtual ~FileQueueReader() = default;
    
    // PayloadProvider interface
    std::vector<uint8_t> GetNextPayload(
        const std::string& label,
        const GlobalSimState& state,
        uint32_t round,
        uint32_t packetSize) override;
    
    bool HasMorePayloads() const override;
    void Reset() override;
    
    // FileQueueReader specific methods
    bool LoadNextSequenceFile();
    void LogFrameFeedback(const std::string& label, uint16_t vl_id, 
                         const std::vector<uint8_t>& payload, 
                         uint32_t seq, uint32_t bag_ms);
    
private:
    std::string m_inputDir;
    std::string m_outputDir;
    std::string m_archiveDir;
    
    std::unique_ptr<ViolationChecker> m_violationChecker;
    std::unique_ptr<FeedbackLogger> m_feedbackLogger;
    
    std::queue<InjectedFrame> m_currentFrames;
    uint16_t m_currentVlId;
    std::string m_currentSequenceFile;
    size_t m_frameIndex;
    
    bool ParseSequenceFile(const std::string& filepath, InjectedSequence& sequence);
    std::vector<uint8_t> HexStringToBytes(const std::string& hexStr);
    void ArchiveProcessedFile(const std::string& filepath);
    std::string GetNextInputFile();
};

} // namespace ns3

#endif // FILE_QUEUE_READER_H
