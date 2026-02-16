#ifndef VIOLATION_CHECKER_H
#define VIOLATION_CHECKER_H

#include <vector>
#include <string>
#include <cstdint>
#include <map>

namespace ns3 {

struct ViolationResult {
    std::vector<std::string> violations;
    int score;  // 0-100, where 100 is perfect
    std::string rule_version;
};

/**
 * Checks AFDX frames against specification rules and generates violation reports.
 * Loads rules from JSON configuration file.
 */
class ViolationChecker
{
public:
    explicit ViolationChecker(const std::string& rulesFile);
    ~ViolationChecker() = default;
    
    /**
     * Check a frame against AFDX specification rules.
     * @param vl_id Virtual Link identifier
     * @param len_bytes Frame length in bytes
     * @param bag_ms BAG (Bandwidth Allocation Gap) in milliseconds
     * @param seq Sequence number
     * @param last_seq Previous sequence number for monotonic check
     * @param time_since_last Time since last frame on this VL (seconds)
     * @return Violation result with violations list and score
     */
    ViolationResult CheckFrame(uint16_t vl_id, 
                              uint32_t len_bytes,
                              uint32_t bag_ms,
                              uint16_t seq,
                              uint16_t last_seq,
                              double time_since_last);
    
    /**
     * Get the rule version string.
     */
    const std::string& GetRuleVersion() const { return m_ruleVersion; }
    
private:
    struct Rules {
        std::vector<uint32_t> allowed_bag_ms;
        uint32_t frame_lmin;
        uint32_t frame_lmax;
        uint32_t frame_smin;
        double jitter_max_fraction;
        double latency_max_ms;
        bool redundancy_default_true;
        bool redundancy_allow_non_redundant_if_explicit;
    };
    
    Rules m_rules;
    std::string m_ruleVersion;
    std::map<uint16_t, uint16_t> m_lastSequences;  // VL -> last sequence
    std::map<uint16_t, double> m_lastFrameTimes;   // VL -> last frame time
    
    bool LoadRules(const std::string& rulesFile);
    int CalculateScore(const std::vector<std::string>& violations);
};

} // namespace ns3

#endif // VIOLATION_CHECKER_H
