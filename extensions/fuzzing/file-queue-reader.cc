#include "file-queue-reader.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include <fstream>
#include <sstream>
#include <regex>
#include <algorithm>
#include <filesystem>

NS_LOG_COMPONENT_DEFINE("FileQueueReader");

namespace ns3 {

FileQueueReader::FileQueueReader(const std::string& inputDir, 
                                const std::string& outputDir,
                                const std::string& archiveDir,
                                const std::string& rulesFile)
    : m_inputDir(inputDir)
    , m_outputDir(outputDir)
    , m_archiveDir(archiveDir)
    , m_currentVlId(0)
    , m_frameIndex(0)
{
    m_violationChecker = std::make_unique<ViolationChecker>(rulesFile);
    m_feedbackLogger = std::make_unique<FeedbackLogger>(outputDir);
    
    // Try to load the first sequence file
    LoadNextSequenceFile();
}

std::vector<uint8_t> FileQueueReader::GetNextPayload(
    const std::string& label,
    const GlobalSimState& state,
    uint32_t round,
    uint32_t packetSize)
{
    if (m_currentFrames.empty()) {
        if (!LoadNextSequenceFile()) {
            NS_LOG_INFO("No more sequence files available, returning empty payload");
            return std::vector<uint8_t>();
        }
    }
    
    if (m_currentFrames.empty()) {
        return std::vector<uint8_t>();
    }
    
    InjectedFrame frame = m_currentFrames.front();
    m_currentFrames.pop();
    
    // Convert hex payload to bytes
    std::vector<uint8_t> payload = HexStringToBytes(frame.payload_hex);
    
    // Pad or truncate to requested packet size
    if (payload.size() < packetSize) {
        payload.resize(packetSize, 0x00); // Pad with zeros
    } else if (payload.size() > packetSize) {
        payload.resize(packetSize); // Truncate
    }
    
    // Log feedback for this frame
    LogFrameFeedback(label, m_currentVlId, payload, frame.seq, frame.bag_ms);
    
    m_frameIndex++;
    
    // If we've consumed all frames from this sequence, archive the file
    if (m_currentFrames.empty() && !m_currentSequenceFile.empty()) {
        ArchiveProcessedFile(m_currentSequenceFile);
        m_currentSequenceFile.clear();
    }
    
    return payload;
}

bool FileQueueReader::HasMorePayloads() const
{
    return !m_currentFrames.empty() || !GetNextInputFile().empty();
}

void FileQueueReader::Reset()
{
    while (!m_currentFrames.empty()) {
        m_currentFrames.pop();
    }
    m_currentVlId = 0;
    m_frameIndex = 0;
    m_currentSequenceFile.clear();
}

bool FileQueueReader::LoadNextSequenceFile()
{
    std::string nextFile = GetNextInputFile();
    if (nextFile.empty()) {
        return false;
    }
    
    InjectedSequence sequence;
    if (!ParseSequenceFile(nextFile, sequence)) {
        NS_LOG_ERROR("Failed to parse sequence file: " << nextFile);
        // Archive the bad file to prevent infinite retry
        ArchiveProcessedFile(nextFile);
        return false;
    }
    
    // Load frames into queue
    for (const auto& frame : sequence.frames) {
        m_currentFrames.push(frame);
    }
    
    m_currentVlId = sequence.vl_id;
    m_currentSequenceFile = nextFile;
    m_frameIndex = 0;
    
    // Extract run ID from filename for feedback logging
    std::string filename = std::filesystem::path(nextFile).filename().string();
    std::string runId = filename.substr(0, filename.find('.'));
    m_feedbackLogger->StartSession(runId);
    
    NS_LOG_INFO("Loaded sequence file: " << nextFile << " with " << sequence.frames.size() << " frames for VL " << sequence.vl_id);
    return true;
}

void FileQueueReader::LogFrameFeedback(const std::string& label, uint16_t vl_id, 
                                     const std::vector<uint8_t>& payload, 
                                     uint32_t seq, uint32_t bag_ms)
{
    double now = Simulator::Now().GetSeconds();
    
    // Check violations
    ViolationResult violations = m_violationChecker->CheckFrame(
        vl_id, 
        payload.size(), 
        bag_ms, 
        static_cast<uint16_t>(seq), 
        0, // TODO: Track last sequence properly
        now
    );
    
    // Create feedback entry
    FeedbackEntry entry;
    entry.ts = now;
    entry.vl_id = vl_id;
    entry.len_bytes = static_cast<uint32_t>(payload.size());
    entry.seq = static_cast<uint16_t>(seq);
    entry.bag_ms = bag_ms;
    entry.violations = violations.violations;
    entry.score = violations.score;
    entry.rule_version = violations.rule_version;
    
    m_feedbackLogger->LogFrame(entry);
}

bool FileQueueReader::ParseSequenceFile(const std::string& filepath, InjectedSequence& sequence)
{
    std::ifstream file(filepath);
    if (!file.is_open()) {
        return false;
    }
    
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string content = buffer.str();
    
    try {
        // Simple JSON parsing for our specific format
        std::regex vl_id_regex(R"("vl_id"\s*:\s*(\d+))");
        std::smatch match;
        
        if (std::regex_search(content, match, vl_id_regex)) {
            sequence.vl_id = static_cast<uint16_t>(std::stoul(match[1].str()));
        } else {
            NS_LOG_ERROR("No vl_id found in sequence file");
            return false;
        }
        
        // Parse frames array
        std::regex frames_regex(R"("frames"\s*:\s*\[(.*?)\])", std::regex_constants::ECMAScript | std::regex_constants::dotall);
        if (std::regex_search(content, match, frames_regex)) {
            std::string frames_content = match[1].str();
            
            // Parse individual frames
            std::regex frame_regex(R"(\{[^}]*"time"\s*:\s*([\d.]+)[^}]*"seq"\s*:\s*(\d+)[^}]*"bag_ms"\s*:\s*(\d+)[^}]*"payload_hex"\s*:\s*"([^"]+)"[^}]*\})");
            std::sregex_iterator iter(frames_content.begin(), frames_content.end(), frame_regex);
            std::sregex_iterator end;
            
            for (; iter != end; ++iter) {
                InjectedFrame frame;
                frame.time = std::stod((*iter)[1].str());
                frame.seq = static_cast<uint16_t>(std::stoul((*iter)[2].str()));
                frame.bag_ms = std::stoul((*iter)[3].str());
                frame.payload_hex = (*iter)[4].str();
                
                sequence.frames.push_back(frame);
            }
        }
        
        return !sequence.frames.empty();
    }
    catch (const std::exception& e) {
        NS_LOG_ERROR("Error parsing sequence file: " << e.what());
        return false;
    }
}

std::vector<uint8_t> FileQueueReader::HexStringToBytes(const std::string& hexStr)
{
    std::vector<uint8_t> bytes;
    std::string cleanHex = hexStr;
    
    // Remove spaces and other non-hex characters
    cleanHex.erase(std::remove_if(cleanHex.begin(), cleanHex.end(), 
                                 [](char c) { return !std::isxdigit(c); }), 
                  cleanHex.end());
    
    // Ensure even number of characters
    if (cleanHex.length() % 2 != 0) {
        cleanHex = "0" + cleanHex;
    }
    
    for (size_t i = 0; i < cleanHex.length(); i += 2) {
        std::string byteStr = cleanHex.substr(i, 2);
        uint8_t byte = static_cast<uint8_t>(std::stoul(byteStr, nullptr, 16));
        bytes.push_back(byte);
    }
    
    return bytes;
}

void FileQueueReader::ArchiveProcessedFile(const std::string& filepath)
{
    try {
        std::string filename = std::filesystem::path(filepath).filename().string();
        std::string archivePath = m_archiveDir + "/" + filename;
        
        std::filesystem::rename(filepath, archivePath);
        NS_LOG_INFO("Archived processed file: " << filepath << " -> " << archivePath);
    }
    catch (const std::exception& e) {
        NS_LOG_ERROR("Failed to archive file " << filepath << ": " << e.what());
    }
}

std::string FileQueueReader::GetNextInputFile()
{
    try {
        if (!std::filesystem::exists(m_inputDir)) {
            return "";
        }
        
        std::vector<std::string> files;
        for (const auto& entry : std::filesystem::directory_iterator(m_inputDir)) {
            if (entry.is_regular_file() && entry.path().extension() == ".json") {
                files.push_back(entry.path().string());
            }
        }
        
        if (files.empty()) {
            return "";
        }
        
        // Sort files to process in order
        std::sort(files.begin(), files.end());
        return files[0];
    }
    catch (const std::exception& e) {
        NS_LOG_ERROR("Error scanning input directory: " << e.what());
        return "";
    }
}

} // namespace ns3
