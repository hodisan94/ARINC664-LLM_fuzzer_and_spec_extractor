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
 * Flight Control Application for AFDX Navigation System
 * Receives and validates GPS data from GPS receivers
 */

#ifndef CONTROL_FLIGHT_H
#define CONTROL_FLIGHT_H

#include "gps.h"
#include "satellite.h"
#include "afdx-end-system.h"
#include "ns3/object.h"
#include "ns3/application.h"
#include "ns3/callback.h"
#include <vector>
#include <map>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief Validation result for GPS data
 */
struct GpsValidationResult
{
    bool isValid;               ///< Overall validity
    bool checksumValid;         ///< CRC checksum verification
    bool fixValid;              ///< GPS fix type is 3D
    bool positionValid;         ///< Position within acceptable bounds
    bool velocityValid;         ///< Velocity within acceptable limits
    bool towValid;              ///< Time of Week is reasonable
    bool satelliteCountValid;   ///< Sufficient satellites visible
    std::string errorMessage;   ///< Detailed error description
    
    /**
     * \brief Convert to string representation
     */
    std::string ToString() const;
};

/**
 * \ingroup afdx
 * \brief Position validation bounds
 */
struct PositionBounds
{
    double minX, maxX;
    double minY, maxY;
    double minZ, maxZ;  // Altitude bounds
    
    PositionBounds()
        : minX(-1e9), maxX(1e9),
          minY(-1e9), maxY(1e9),
          minZ(-1000), maxZ(100000) // -1km to 100km altitude
    {}
};

/**
 * \ingroup afdx
 * \brief Velocity validation limits
 */
struct VelocityLimits
{
    double maxHorizontal;  ///< Maximum horizontal velocity (m/s)
    double maxVertical;    ///< Maximum vertical velocity (m/s)
    
    VelocityLimits()
        : maxHorizontal(400.0),  // ~Mach 1.2 for typical aircraft
          maxVertical(100.0)     // 100 m/s vertical
    {}
};

/**
 * \ingroup afdx
 * \brief Flight Control System Application
 * 
 * This application models a Flight Control Computer that:
 * 1. Receives GPS data via AFDX Virtual Links
 * 2. Validates all GPS parameters for safety
 * 3. Tracks GPS data statistics and health
 * 4. Reports validation failures
 * 
 * Validation checks performed:
 * - Checksum integrity verification
 * - GPS fix type validation (requires 3D fix)
 * - Position bounds checking
 * - Velocity limits validation
 * - Time of Week reasonableness
 * - Minimum satellite count verification
 */
class FlightControlSystem : public Application
{
public:
    /**
     * \brief Get the type ID
     * \return the object TypeId
     */
    static TypeId GetTypeId();
    
    FlightControlSystem();
    virtual ~FlightControlSystem();
    
    // ============================================================================
    // Configuration Methods
    // ============================================================================
    
    /**
     * \brief Set the AFDX End System for this flight control system
     * \param endSystem Pointer to the AFDX End System
     */
    void SetAfdxEndSystem(Ptr<AfdxEndSystem> endSystem);
    
    /**
     * \brief Set the Flight Control System ID
     * \param id System identifier
     */
    void SetSystemId(uint16_t id);
    
    /**
     * \brief Subscribe to GPS data Virtual Link
     * \param vlId Virtual Link ID for GPS data
     */
    void SubscribeToGpsData(uint16_t vlId);
    
    /**
     * \brief Set position validation bounds
     * \param bounds Position bounds structure
     */
    void SetPositionBounds(const PositionBounds& bounds);
    
    /**
     * \brief Set velocity validation limits
     * \param limits Velocity limits structure
     */
    void SetVelocityLimits(const VelocityLimits& limits);
    
    /**
     * \brief Set minimum required satellites for valid fix
     * \param minSats Minimum satellite count (default: 4)
     */
    void SetMinimumSatellites(uint8_t minSats);
    
    /**
     * \brief Set callback for validation events
     * \param callback Function called on each GPS data validation
     */
    typedef Callback<void, const GpsMessage&, const GpsValidationResult&> ValidationCallback;
    void SetValidationCallback(ValidationCallback callback);
    
    // ============================================================================
    // Validation Methods
    // ============================================================================
    
    /**
     * \brief Validate GPS message
     * \param msg GPS message to validate
     * \return Validation result with detailed status
     */
    GpsValidationResult ValidateGpsMessage(const GpsMessage& msg);
    
    /**
     * \brief Validate satellite data parameters
     * \param data Satellite data to validate
     * \return Validation result
     */
    GpsValidationResult ValidateSatelliteData(const SatelliteData& data);
    
    // ============================================================================
    // Statistics Methods
    // ============================================================================
    
    /**
     * \brief Get total messages received
     * \return Count of received messages
     */
    uint32_t GetMessagesReceived() const { return m_messagesReceived; }
    
    /**
     * \brief Get count of valid messages
     * \return Count of messages passing all validation
     */
    uint32_t GetValidMessages() const { return m_validMessages; }
    
    /**
     * \brief Get count of invalid messages
     * \return Count of messages failing validation
     */
    uint32_t GetInvalidMessages() const { return m_invalidMessages; }
    
    /**
     * \brief Get last received GPS message
     * \return Most recent GPS message
     */
    GpsMessage GetLastGpsMessage() const { return m_lastGpsMessage; }
    
    /**
     * \brief Get last validation result
     * \return Most recent validation result
     */
    GpsValidationResult GetLastValidationResult() const { return m_lastValidationResult; }
    
    /**
     * \brief Get current aircraft position from last valid GPS
     * \return Position vector (X, Y, Z)
     */
    std::tuple<double, double, double> GetCurrentPosition() const;
    
    /**
     * \brief Get current aircraft velocity from last valid GPS
     * \return Velocity vector (Vx, Vy, Vz)
     */
    std::tuple<double, double, double> GetCurrentVelocity() const;
    
    /**
     * \brief Print statistics summary
     * \param os Output stream
     */
    void PrintStatistics(std::ostream& os) const;
    
    // ============================================================================
    // Frame Processing Methods (Public for external integration)
    // ============================================================================
    
    /**
     * \brief Handle received AFDX frame containing GPS data
     * \param vlId Virtual Link ID
     * \param payload Frame payload data
     * \param seqNum Sequence number
     * 
     * This method can be called externally to process GPS data received
     * via AFDX frames, allowing integration with the AFDX End System
     * event callback mechanism.
     */
    void HandleReceivedFrame(uint16_t vlId, const std::vector<uint8_t>& payload, uint8_t seqNum);

protected:
    virtual void DoDispose();

private:
    virtual void StartApplication();
    virtual void StopApplication();
    
    /**
     * \brief Validate position bounds
     * \param x X position
     * \param y Y position
     * \param z Z position
     * \return true if position is within bounds
     */
    bool ValidatePosition(double x, double y, double z) const;
    
    /**
     * \brief Validate velocity limits
     * \param vx X velocity
     * \param vy Y velocity
     * \param vz Z velocity
     * \return true if velocity is within limits
     */
    bool ValidateVelocity(double vx, double vy, double vz) const;
    
    /**
     * \brief Validate Time of Week
     * \param tow Time of Week in seconds
     * \return true if TOW is reasonable (0-604799)
     */
    bool ValidateTOW(double tow) const;
    
    // Configuration
    Ptr<AfdxEndSystem> m_endSystem;
    uint16_t m_systemId;
    std::vector<uint16_t> m_gpsVirtualLinks;
    PositionBounds m_positionBounds;
    VelocityLimits m_velocityLimits;
    uint8_t m_minSatellites;
    
    // State
    GpsMessage m_lastGpsMessage;
    GpsValidationResult m_lastValidationResult;
    SatelliteData m_lastValidPosition;
    bool m_hasValidPosition;
    
    // Statistics
    uint32_t m_messagesReceived;
    uint32_t m_validMessages;
    uint32_t m_invalidMessages;
    std::map<std::string, uint32_t> m_errorCounts;  // Count by error type
    
    // Callbacks
    ValidationCallback m_validationCallback;
};

} // namespace ns3

#endif /* CONTROL_FLIGHT_H */
