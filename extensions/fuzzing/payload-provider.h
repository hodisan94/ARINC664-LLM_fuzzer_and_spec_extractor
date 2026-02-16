#ifndef PAYLOAD_PROVIDER_H
#define PAYLOAD_PROVIDER_H

#include <vector>
#include <cstdint>
#include <string>
#include "../../scratch/afdx/global-sim-state.h"

namespace ns3 {

/**
 * Abstract interface for payload sources in AFDX VL transmitters.
 * Allows switching between normal payload generation and fuzzer-injected sequences.
 */
class PayloadProvider
{
public:
    virtual ~PayloadProvider() = default;
    
    /**
     * Get the next payload for transmission.
     * @param label VL label/identifier
     * @param state Current global simulation state
     * @param round Current transmission round
     * @param packetSize Required packet size
     * @return Payload bytes vector
     */
    virtual std::vector<uint8_t> GetNextPayload(
        const std::string& label,
        const GlobalSimState& state,
        uint32_t round,
        uint32_t packetSize) = 0;
    
    /**
     * Check if this provider has more payloads available.
     * @return true if more payloads can be provided
     */
    virtual bool HasMorePayloads() const = 0;
    
    /**
     * Reset provider to initial state (optional).
     */
    virtual void Reset() {}
};

} // namespace ns3

#endif // PAYLOAD_PROVIDER_H
