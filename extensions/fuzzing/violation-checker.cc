#include "violation-checker.h"
#include "ns3/log.h"
#include <fstream>
#include <sstream>
#include <algorithm>

// Simple JSON parsing for our specific use case
#include <regex>

NS_LOG_COMPONENT_DEFINE("ViolationChecker");

namespace ns3 {

ViolationChecker::ViolationChecker(const std::string& rulesFile)
    : m_ruleVersion("1.0.0")
{
    if (!LoadRules(rulesFile)) {
        NS_LOG_ERROR("Failed to load rules from: " << rulesFile);
    }
}

bool ViolationChecker::LoadRules(const std::string& rulesFile)
{
    std::ifstream file(rulesFile);
    if (!file.is_open()) {
        NS_LOG_ERROR("Cannot open rules file: " << rulesFile);
        return false;
    }
    
    // Read entire file
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string content = buffer.str();
    
    try {
        // Parse allowed BAG values
        std::regex bag_regex(R"("allowed_ms"\s*:\s*\[\s*((?:\d+(?:\s*,\s*)?)*)\s*\])");
        std::smatch bag_match;
        if (std::regex_search(content, bag_match, bag_regex)) {
            std::string bag_values = bag_match[1].str();
            std::regex num_regex(R"(\d+)");
            std::sregex_iterator iter(bag_values.begin(), bag_values.end(), num_regex);
            std::sregex_iterator end;
            
            for (; iter != end; ++iter) {
                m_rules.allowed_bag_ms.push_back(std::stoul(iter->str()));
            }
        }
        
        // Parse frame limits
        std::regex lmin_regex(R"("lmin"\s*:\s*(\d+))");
        std::regex lmax_regex(R"("lmax"\s*:\s*(\d+))");
        std::regex smin_regex(R"("smin"\s*:\s*(\d+|null))");
        
        std::smatch match;
        if (std::regex_search(content, match, lmin_regex)) {
            m_rules.frame_lmin = std::stoul(match[1].str());
        } else {
            m_rules.frame_lmin = 64; // Default
        }
        
        if (std::regex_search(content, match, lmax_regex)) {
            m_rules.frame_lmax = std::stoul(match[1].str());
        } else {
            m_rules.frame_lmax = 1518; // Default
        }
        
        if (std::regex_search(content, match, smin_regex)) {
            std::string smin_val = match[1].str();
            if (smin_val != "null") {
                m_rules.frame_smin = std::stoul(smin_val);
            } else {
                m_rules.frame_smin = 0; // null means no minimum
            }
        } else {
            m_rules.frame_smin = 0;
        }
        
        // Parse other parameters with defaults
        std::regex jitter_regex(R"("jitter_max_fraction"\s*:\s*([\d.]+))");
        if (std::regex_search(content, match, jitter_regex)) {
            m_rules.jitter_max_fraction = std::stod(match[1].str());
        } else {
            m_rules.jitter_max_fraction = 0.5;
        }
        
        std::regex latency_regex(R"("latency_max_ms"\s*:\s*([\d.]+))");
        if (std::regex_search(content, match, latency_regex)) {
            m_rules.latency_max_ms = std::stod(match[1].str());
        } else {
            m_rules.latency_max_ms = 0.15;
        }
        
        // Redundancy defaults
        m_rules.redundancy_default_true = true;
        m_rules.redundancy_allow_non_redundant_if_explicit = false;
        
        NS_LOG_INFO("Loaded rules: lmin=" << m_rules.frame_lmin << ", lmax=" << m_rules.frame_lmax 
                   << ", allowed_bags=" << m_rules.allowed_bag_ms.size());
        
        return true;
    }
    catch (const std::exception& e) {
        NS_LOG_ERROR("Error parsing rules file: " << e.what());
        return false;
    }
}

ViolationResult ViolationChecker::CheckFrame(uint16_t vl_id, 
                                           uint32_t len_bytes,
                                           uint32_t bag_ms,
                                           uint16_t seq,
                                           uint16_t last_seq,
                                           double time_since_last)
{
    ViolationResult result;
    result.rule_version = m_ruleVersion;
    
    // Check frame length violations
    if (len_bytes < m_rules.frame_lmin) {
        result.violations.push_back("LEN_TOO_SMALL");
    }
    if (len_bytes > m_rules.frame_lmax) {
        result.violations.push_back("LEN_TOO_LARGE");
    }
    if (m_rules.frame_smin > 0 && len_bytes < m_rules.frame_smin) {
        result.violations.push_back("LEN_BELOW_SMIN");
    }
    
    // Check BAG violations
    if (!m_rules.allowed_bag_ms.empty()) {
        auto it = std::find(m_rules.allowed_bag_ms.begin(), m_rules.allowed_bag_ms.end(), bag_ms);
        if (it == m_rules.allowed_bag_ms.end()) {
            result.violations.push_back("BAG_NOT_ALLOWED");
        }
    }
    
    // Check sequence violations (only if we have previous sequence)
    if (m_lastSequences.count(vl_id)) {
        uint16_t expected_seq = (m_lastSequences[vl_id] + 1) % 65536;
        if (seq != expected_seq) {
            if (seq < m_lastSequences[vl_id]) {
                result.violations.push_back("SEQ_NON_MONOTONIC");
            } else if (seq > expected_seq) {
                result.violations.push_back("SEQ_JUMP");
            }
        }
    }
    m_lastSequences[vl_id] = seq;
    
    // Check timing violations (BAG enforcement)
    if (m_lastFrameTimes.count(vl_id)) {
        double expected_interval = bag_ms / 1000.0; // Convert to seconds
        double actual_interval = time_since_last;
        
        if (actual_interval < expected_interval * 0.95) { // 5% tolerance
            result.violations.push_back("BAG_TOO_FAST");
        }
    }
    m_lastFrameTimes[vl_id] = time_since_last;
    
    // TODO: Add redundancy checks when we have VL configuration
    // For now, assume redundancy is missing if not explicitly configured
    if (m_rules.redundancy_default_true && !m_rules.redundancy_allow_non_redundant_if_explicit) {
        // This would need VL configuration to determine properly
        // result.violations.push_back("REDUNDANCY_MISSING");
    }
    
    result.score = CalculateScore(result.violations);
    return result;
}

int ViolationChecker::CalculateScore(const std::vector<std::string>& violations)
{
    // Simple scoring: start at 100, subtract 30 for each violation
    int score = 100 - (30 * static_cast<int>(violations.size()));
    return std::max(0, score);
}

} // namespace ns3
