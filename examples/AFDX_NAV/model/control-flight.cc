/*
 * Copyright (c) 2024 AFDX Development Team
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Author: AFDX Development Team
 * 
 * Flight Control System Implementation
 */

#include "control-flight.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/uinteger.h"
#include <sstream>
#include <iomanip>
#include <cmath>
#include <iostream>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("ControlFlight");

NS_OBJECT_ENSURE_REGISTERED(FlightControlSystem);

// ============================================================================
// GpsValidationResult Implementation
// ============================================================================

std::string
GpsValidationResult::ToString() const
{
    std::ostringstream oss;
    oss << "ValidationResult{"
        << "valid=" << (isValid ? "YES" : "NO")
        << ", checksum=" << (checksumValid ? "OK" : "FAIL")
        << ", fix=" << (fixValid ? "3D" : "INVALID")
        << ", position=" << (positionValid ? "OK" : "OUT_OF_BOUNDS")
        << ", velocity=" << (velocityValid ? "OK" : "EXCEEDED")
        << ", tow=" << (towValid ? "OK" : "INVALID")
        << ", satellites=" << (satelliteCountValid ? "OK" : "INSUFFICIENT");
    if (!isValid)
    {
        oss << ", error=\"" << errorMessage << "\"";
    }
    oss << "}";
    return oss.str();
}

// ============================================================================
// FlightControlSystem Implementation
// ============================================================================

TypeId
FlightControlSystem::GetTypeId()
{
    static TypeId tid = TypeId("ns3::FlightControlSystem")
        .SetParent<Application>()
        .SetGroupName("Afdx")
        .AddConstructor<FlightControlSystem>()
        .AddAttribute("SystemId",
                      "Flight Control System identifier",
                      UintegerValue(1),
                      MakeUintegerAccessor(&FlightControlSystem::m_systemId),
                      MakeUintegerChecker<uint16_t>())
        .AddAttribute("MinSatellites",
                      "Minimum number of satellites required for valid fix",
                      UintegerValue(4),
                      MakeUintegerAccessor(&FlightControlSystem::m_minSatellites),
                      MakeUintegerChecker<uint8_t>());
    return tid;
}

FlightControlSystem::FlightControlSystem()
    : m_endSystem(nullptr),
      m_systemId(1),
      m_minSatellites(4),
      m_hasValidPosition(false),
      m_messagesReceived(0),
      m_validMessages(0),
      m_invalidMessages(0),
      m_validationCallback(MakeNullCallback<void, const GpsMessage&, const GpsValidationResult&>())
{
    NS_LOG_FUNCTION(this);
    
    // Initialize last validation result
    m_lastValidationResult.isValid = false;
    m_lastValidationResult.checksumValid = false;
    m_lastValidationResult.fixValid = false;
    m_lastValidationResult.positionValid = false;
    m_lastValidationResult.velocityValid = false;
    m_lastValidationResult.towValid = false;
    m_lastValidationResult.satelliteCountValid = false;
}

FlightControlSystem::~FlightControlSystem()
{
    NS_LOG_FUNCTION(this);
}

void
FlightControlSystem::DoDispose()
{
    NS_LOG_FUNCTION(this);
    m_endSystem = nullptr;
    Application::DoDispose();
}

void
FlightControlSystem::SetAfdxEndSystem(Ptr<AfdxEndSystem> endSystem)
{
    NS_LOG_FUNCTION(this << endSystem);
    m_endSystem = endSystem;
}

void
FlightControlSystem::SetSystemId(uint16_t id)
{
    NS_LOG_FUNCTION(this << id);
    m_systemId = id;
}

void
FlightControlSystem::SubscribeToGpsData(uint16_t vlId)
{
    NS_LOG_FUNCTION(this << vlId);
    
    m_gpsVirtualLinks.push_back(vlId);
    
    if (m_endSystem)
    {
        m_endSystem->AddSubscription(vlId);
        NS_LOG_INFO("Flight Control System " << m_systemId << " subscribed to GPS VL " << vlId);
    }
}

void
FlightControlSystem::SetPositionBounds(const PositionBounds& bounds)
{
    NS_LOG_FUNCTION(this);
    m_positionBounds = bounds;
}

void
FlightControlSystem::SetVelocityLimits(const VelocityLimits& limits)
{
    NS_LOG_FUNCTION(this);
    m_velocityLimits = limits;
}

void
FlightControlSystem::SetMinimumSatellites(uint8_t minSats)
{
    NS_LOG_FUNCTION(this << (int)minSats);
    m_minSatellites = minSats;
}

void
FlightControlSystem::SetValidationCallback(ValidationCallback callback)
{
    NS_LOG_FUNCTION(this);
    m_validationCallback = callback;
}

void
FlightControlSystem::StartApplication()
{
    NS_LOG_FUNCTION(this);
    
    if (!m_endSystem)
    {
        NS_LOG_ERROR("Flight Control System " << m_systemId << " has no AFDX End System configured");
        return;
    }
    
    // Subscribe to configured GPS VLs
    for (uint16_t vlId : m_gpsVirtualLinks)
    {
        m_endSystem->AddSubscription(vlId);
    }
    
    NS_LOG_INFO("Flight Control System " << m_systemId << " started, subscribed to " 
                << m_gpsVirtualLinks.size() << " GPS Virtual Links");
}

void
FlightControlSystem::StopApplication()
{
    NS_LOG_FUNCTION(this);
    
    NS_LOG_INFO("Flight Control System " << m_systemId << " stopping");
    PrintStatistics(std::cout);
}

void
FlightControlSystem::HandleReceivedFrame(uint16_t vlId, const std::vector<uint8_t>& payload, uint8_t seqNum)
{
    NS_LOG_FUNCTION(this << vlId << payload.size() << (int)seqNum);
    
    // Check if this is a GPS VL we're subscribed to
    bool isGpsVl = false;
    for (uint16_t gpsVl : m_gpsVirtualLinks)
    {
        if (gpsVl == vlId)
        {
            isGpsVl = true;
            break;
        }
    }
    
    if (!isGpsVl)
    {
        NS_LOG_DEBUG("Received frame on VL " << vlId << " - not a subscribed GPS VL");
        return;
    }
    
    m_messagesReceived++;
    
    // Deserialize GPS message
    GpsMessage msg = GpsReceiver::DeserializeMessage(payload);
    m_lastGpsMessage = msg;
    
    // =========================================================================
    // STEP 4: FLIGHT CONTROL RECEIVES GPS DATA VIA AFDX
    // =========================================================================
    std::cout << "\n╔══════════════════════════════════════════════════════════════════════╗\n";
    std::cout << "║  ✈️  STEP 4: FLIGHT CONTROL <- GPS DATA (via AFDX)                    ║\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  Time: " << std::fixed << std::setprecision(3) << Simulator::Now().GetSeconds() << "s\n";
    std::cout << "║  Flight Control System ID: " << m_systemId << "\n";
    std::cout << "║  Virtual Link: " << vlId << ", Sequence: " << (int)seqNum << "\n";
    std::cout << "║  Payload Size: " << payload.size() << " bytes\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  RECEIVED GPS MESSAGE:\n";
    std::cout << "║  ┌────────────────────────────────────────────────────────────────┐\n";
    std::cout << "║  │ HEADER:                                                        │\n";
    std::cout << "║  │   Message ID:     " << std::setw(10) << msg.messageId << "                             │\n";
    std::cout << "║  │   GPS Receiver:   " << std::setw(10) << msg.gpsReceiverId << "                             │\n";
    std::cout << "║  │   Timestamp:      " << std::setw(10) << msg.timestampMs << " ms                          │\n";
    std::cout << "║  ├────────────────────────────────────────────────────────────────┤\n";
    std::cout << "║  │ SATELLITE DATA:                                                │\n";
    std::cout << "║  │   Position X:    " << std::setw(12) << std::setprecision(2) << msg.satelliteData.positionX << " m                         │\n";
    std::cout << "║  │   Position Y:    " << std::setw(12) << msg.satelliteData.positionY << " m                         │\n";
    std::cout << "║  │   Position Z:    " << std::setw(12) << msg.satelliteData.positionZ << " m                         │\n";
    std::cout << "║  │   Velocity Vx:   " << std::setw(12) << msg.satelliteData.velocityX << " m/s                       │\n";
    std::cout << "║  │   Velocity Vy:   " << std::setw(12) << msg.satelliteData.velocityY << " m/s                       │\n";
    std::cout << "║  │   Velocity Vz:   " << std::setw(12) << msg.satelliteData.velocityZ << " m/s                       │\n";
    std::cout << "║  │   TOW:           " << std::setw(12) << std::setprecision(1) << msg.satelliteData.timeOfWeek << " s                         │\n";
    std::cout << "║  │   Satellites:    " << std::setw(12) << (int)msg.satelliteData.numSatellites << "                             │\n";
    std::cout << "║  │   Fix Type:      " << std::setw(12) << (int)msg.satelliteData.fixType;
    if (msg.satelliteData.fixType == 2) std::cout << " [3D FIX]";
    else if (msg.satelliteData.fixType == 1) std::cout << " [2D FIX]";
    else std::cout << " [NO FIX]";
    std::cout << "                   │\n";
    std::cout << "║  ├────────────────────────────────────────────────────────────────┤\n";
    std::cout << "║  │ INTEGRITY:                                                     │\n";
    std::cout << "║  │   Checksum:   0x" << std::hex << std::setw(8) << std::setfill('0') << msg.checksum << std::dec << std::setfill(' ') << "                               │\n";
    std::cout << "║  └────────────────────────────────────────────────────────────────┘\n";
    
    // Validate the message
    GpsValidationResult result = ValidateGpsMessage(msg);
    m_lastValidationResult = result;
    
    // =========================================================================
    // STEP 5: FLIGHT CONTROL VALIDATES GPS DATA
    // =========================================================================
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  🔍 STEP 5: FLIGHT CONTROL VALIDATES GPS DATA                        ║\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  VALIDATION RESULTS:\n";
    std::cout << "║  ┌────────────────────────────────────────────────────────────────┐\n";
    std::cout << "║  │ Checksum:         " << (result.checksumValid ? "✓ PASS" : "✗ FAIL") << "                                     │\n";
    std::cout << "║  │ Fix Type:         " << (result.fixValid ? "✓ PASS (3D)" : "✗ FAIL") << "                                │\n";
    std::cout << "║  │ Position Bounds:  " << (result.positionValid ? "✓ PASS" : "✗ OUT OF BOUNDS") << "                            │\n";
    std::cout << "║  │ Velocity Limits:  " << (result.velocityValid ? "✓ PASS" : "✗ EXCEEDED") << "                                 │\n";
    std::cout << "║  │ Time of Week:     " << (result.towValid ? "✓ PASS" : "✗ INVALID") << "                                  │\n";
    std::cout << "║  │ Satellite Count:  " << (result.satelliteCountValid ? "✓ PASS" : "✗ INSUFFICIENT") << "                             │\n";
    std::cout << "║  ├────────────────────────────────────────────────────────────────┤\n";
    std::cout << "║  │ OVERALL:          " << (result.isValid ? "✓ VALID - Data accepted for navigation" : "✗ INVALID - Data rejected") << "    │\n";
    if (!result.isValid)
    {
        std::cout << "║  │ Error: " << result.errorMessage << "\n";
    }
    std::cout << "║  └────────────────────────────────────────────────────────────────┘\n";
    std::cout << "╚══════════════════════════════════════════════════════════════════════╝\n\n";

    if (result.isValid)
    {
        m_validMessages++;
        m_lastValidPosition = msg.satelliteData;
        m_hasValidPosition = true;
        
        NS_LOG_INFO("GPS data VALID: " << result.ToString());
    }
    else
    {
        m_invalidMessages++;
        m_errorCounts[result.errorMessage]++;
        
        NS_LOG_WARN("GPS data INVALID: " << result.ToString());
    }
    
    // Invoke callback if set
    if (!m_validationCallback.IsNull())
    {
        m_validationCallback(msg, result);
    }
}

GpsValidationResult
FlightControlSystem::ValidateGpsMessage(const GpsMessage& msg)
{
    NS_LOG_FUNCTION(this);
    
    GpsValidationResult result;
    result.isValid = true;
    result.errorMessage = "";
    
    // 1. Verify checksum integrity
    result.checksumValid = GpsReceiver::VerifyChecksum(msg);
    if (!result.checksumValid)
    {
        result.isValid = false;
        result.errorMessage = "Checksum verification failed";
        NS_LOG_WARN("Checksum FAILED for message ID " << msg.messageId);
    }
    
    // Validate satellite data
    GpsValidationResult satResult = ValidateSatelliteData(msg.satelliteData);
    
    result.fixValid = satResult.fixValid;
    result.positionValid = satResult.positionValid;
    result.velocityValid = satResult.velocityValid;
    result.towValid = satResult.towValid;
    result.satelliteCountValid = satResult.satelliteCountValid;
    
    // Combine results
    if (!satResult.isValid)
    {
        result.isValid = false;
        if (result.errorMessage.empty())
        {
            result.errorMessage = satResult.errorMessage;
        }
        else
        {
            result.errorMessage += "; " + satResult.errorMessage;
        }
    }
    
    return result;
}

GpsValidationResult
FlightControlSystem::ValidateSatelliteData(const SatelliteData& data)
{
    NS_LOG_FUNCTION(this);
    
    GpsValidationResult result;
    result.isValid = true;
    result.checksumValid = true; // Not applicable for direct satellite data
    std::vector<std::string> errors;
    
    // 2. Validate GPS fix type (must be 3D for valid navigation)
    result.fixValid = (data.fixType == static_cast<uint8_t>(SatelliteFixType::FIX_3D));
    if (!result.fixValid)
    {
        result.isValid = false;
        errors.push_back("Invalid GPS fix type (not 3D)");
        NS_LOG_WARN("Fix type INVALID: " << (int)data.fixType << " (expected 2 for 3D)");
    }
    
    // 3. Validate satellite count
    result.satelliteCountValid = (data.numSatellites >= m_minSatellites);
    if (!result.satelliteCountValid)
    {
        result.isValid = false;
        errors.push_back("Insufficient satellites (" + std::to_string(data.numSatellites) + 
                        " < " + std::to_string(m_minSatellites) + ")");
        NS_LOG_WARN("Satellite count INSUFFICIENT: " << (int)data.numSatellites 
                   << " < " << (int)m_minSatellites);
    }
    
    // 4. Validate position bounds
    result.positionValid = ValidatePosition(data.positionX, data.positionY, data.positionZ);
    if (!result.positionValid)
    {
        result.isValid = false;
        errors.push_back("Position out of bounds");
        NS_LOG_WARN("Position OUT OF BOUNDS: (" << data.positionX << ", " 
                   << data.positionY << ", " << data.positionZ << ")");
    }
    
    // 5. Validate velocity limits
    result.velocityValid = ValidateVelocity(data.velocityX, data.velocityY, data.velocityZ);
    if (!result.velocityValid)
    {
        result.isValid = false;
        errors.push_back("Velocity exceeds limits");
        NS_LOG_WARN("Velocity EXCEEDED: (" << data.velocityX << ", " 
                   << data.velocityY << ", " << data.velocityZ << ") m/s");
    }
    
    // 6. Validate Time of Week
    result.towValid = ValidateTOW(data.timeOfWeek);
    if (!result.towValid)
    {
        result.isValid = false;
        errors.push_back("Invalid Time of Week");
        NS_LOG_WARN("TOW INVALID: " << data.timeOfWeek << " seconds");
    }
    
    // Combine error messages
    if (!errors.empty())
    {
        result.errorMessage = errors[0];
        for (size_t i = 1; i < errors.size(); ++i)
        {
            result.errorMessage += "; " + errors[i];
        }
    }
    
    return result;
}

bool
FlightControlSystem::ValidatePosition(double x, double y, double z) const
{
    // Check X bounds
    if (x < m_positionBounds.minX || x > m_positionBounds.maxX)
    {
        return false;
    }
    
    // Check Y bounds
    if (y < m_positionBounds.minY || y > m_positionBounds.maxY)
    {
        return false;
    }
    
    // Check Z (altitude) bounds
    if (z < m_positionBounds.minZ || z > m_positionBounds.maxZ)
    {
        return false;
    }
    
    // Check for NaN or infinity
    if (std::isnan(x) || std::isnan(y) || std::isnan(z) ||
        std::isinf(x) || std::isinf(y) || std::isinf(z))
    {
        return false;
    }
    
    return true;
}

bool
FlightControlSystem::ValidateVelocity(double vx, double vy, double vz) const
{
    // Calculate horizontal velocity magnitude
    double horizontalSpeed = std::sqrt(vx * vx + vy * vy);
    
    // Check horizontal velocity limit
    if (horizontalSpeed > m_velocityLimits.maxHorizontal)
    {
        return false;
    }
    
    // Check vertical velocity limit
    if (std::abs(vz) > m_velocityLimits.maxVertical)
    {
        return false;
    }
    
    // Check for NaN or infinity
    if (std::isnan(vx) || std::isnan(vy) || std::isnan(vz) ||
        std::isinf(vx) || std::isinf(vy) || std::isinf(vz))
    {
        return false;
    }
    
    return true;
}

bool
FlightControlSystem::ValidateTOW(double tow) const
{
    // TOW must be in range [0, 604799] seconds (one week)
    if (tow < 0.0 || tow >= 604800.0)
    {
        return false;
    }
    
    // Check for NaN or infinity
    if (std::isnan(tow) || std::isinf(tow))
    {
        return false;
    }
    
    return true;
}

std::tuple<double, double, double>
FlightControlSystem::GetCurrentPosition() const
{
    if (m_hasValidPosition)
    {
        return std::make_tuple(m_lastValidPosition.positionX,
                               m_lastValidPosition.positionY,
                               m_lastValidPosition.positionZ);
    }
    return std::make_tuple(0.0, 0.0, 0.0);
}

std::tuple<double, double, double>
FlightControlSystem::GetCurrentVelocity() const
{
    if (m_hasValidPosition)
    {
        return std::make_tuple(m_lastValidPosition.velocityX,
                               m_lastValidPosition.velocityY,
                               m_lastValidPosition.velocityZ);
    }
    return std::make_tuple(0.0, 0.0, 0.0);
}

void
FlightControlSystem::PrintStatistics(std::ostream& os) const
{
    os << "\n========================================\n";
    os << "Flight Control System " << m_systemId << " Statistics\n";
    os << "========================================\n";
    os << "Messages Received: " << m_messagesReceived << "\n";
    os << "Valid Messages:    " << m_validMessages 
       << " (" << std::fixed << std::setprecision(1) 
       << (m_messagesReceived > 0 ? 100.0 * m_validMessages / m_messagesReceived : 0.0) << "%)\n";
    os << "Invalid Messages:  " << m_invalidMessages 
       << " (" << std::fixed << std::setprecision(1)
       << (m_messagesReceived > 0 ? 100.0 * m_invalidMessages / m_messagesReceived : 0.0) << "%)\n";
    
    if (!m_errorCounts.empty())
    {
        os << "\nError Breakdown:\n";
        for (const auto& pair : m_errorCounts)
        {
            os << "  - " << pair.first << ": " << pair.second << "\n";
        }
    }
    
    if (m_hasValidPosition)
    {
        os << "\nLast Valid Position:\n";
        os << "  X: " << m_lastValidPosition.positionX << " m\n";
        os << "  Y: " << m_lastValidPosition.positionY << " m\n";
        os << "  Z: " << m_lastValidPosition.positionZ << " m (altitude)\n";
        os << "  Vx: " << m_lastValidPosition.velocityX << " m/s\n";
        os << "  Vy: " << m_lastValidPosition.velocityY << " m/s\n";
        os << "  Vz: " << m_lastValidPosition.velocityZ << " m/s\n";
        os << "  Satellites: " << (int)m_lastValidPosition.numSatellites << "\n";
    }
    os << "========================================\n";
}

} // namespace ns3
