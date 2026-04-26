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
 * Satellite Data Model for AFDX Navigation Application
 * Simulates satellite position/velocity data transmitted to GPS receivers
 */

#ifndef SATELLITE_H
#define SATELLITE_H

#include "ns3/object.h"
#include "ns3/random-variable-stream.h"
#include "ns3/nstime.h"
#include <cstdint>
#include <vector>
#include <array>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief Satellite Navigation Data Structure
 * 
 * Contains navigation data transmitted by satellites to GPS receivers
 * according to typical GNSS message format.
 * 
 * Total payload size: 58 bytes
 * - Position X, Y, Z: 8 bytes each (double) = 24 bytes
 * - Velocity Vx, Vy, Vz: 8 bytes each (double) = 24 bytes
 * - Time of Week (TOW): 8 bytes (double) = 8 bytes
 * - Number of satellites used: 1 byte (uint8_t) = 1 byte
 * - Fix type: 1 byte (uint8_t) = 1 byte
 */
struct SatelliteData
{
    // Position in meters (ECEF or local coordinates)
    double positionX;     ///< Position X (meters) - 8 bytes
    double positionY;     ///< Position Y (meters) - 8 bytes
    double positionZ;     ///< Position Z (meters) - 8 bytes
    
    // Velocity in m/s
    double velocityX;     ///< Velocity X (m/s) - 8 bytes
    double velocityY;     ///< Velocity Y (m/s) - 8 bytes
    double velocityZ;     ///< Velocity Z (m/s) - 8 bytes
    
    // Time information
    double timeOfWeek;    ///< Time of Week in seconds (0-604799) - 8 bytes
    
    // Status information
    uint8_t numSatellites; ///< Number of satellites used (0-32) - 1 byte
    uint8_t fixType;       ///< Fix type: 0=none, 1=2D, 2=3D - 1 byte
    
    /**
     * \brief Get the total serialized size of satellite data
     * \return Size in bytes (58 bytes total)
     */
    static constexpr uint32_t GetSerializedSize() { return 58; }
    
    /**
     * \brief Check if the fix is valid (3D fix)
     * \return true if fix type is 3D (value 2)
     */
    bool IsValidFix() const { return fixType == 2; }
    
    /**
     * \brief Convert to string representation
     * \return String describing the satellite data
     */
    std::string ToString() const;
};

/**
 * \ingroup afdx
 * \brief Fix type enumeration
 */
enum class SatelliteFixType : uint8_t
{
    NO_FIX = 0,    ///< No GPS fix available
    FIX_2D = 1,    ///< 2D fix (latitude/longitude only)
    FIX_3D = 2     ///< 3D fix (latitude/longitude/altitude)
};

/**
 * \ingroup afdx
 * \brief Satellite Data Generator
 * 
 * Generates realistic satellite navigation data with configurable
 * parameters for position, velocity, and status fields.
 * Simulates satellite signal characteristics including:
 * - Random position within defined airspace
 * - Realistic velocity vectors for aircraft
 * - Time-based TOW generation
 * - Variable satellite visibility
 */
class SatelliteDataGenerator : public Object
{
public:
    /**
     * \brief Get the type ID
     * \return the object TypeId
     */
    static TypeId GetTypeId();
    
    SatelliteDataGenerator();
    virtual ~SatelliteDataGenerator();
    
    // ============================================================================
    // Configuration Methods
    // ============================================================================
    
    /**
     * \brief Set position bounds for random generation (meters)
     * \param minX Minimum X position
     * \param maxX Maximum X position
     * \param minY Minimum Y position
     * \param maxY Maximum Y position
     * \param minZ Minimum Z position (altitude)
     * \param maxZ Maximum Z position (altitude)
     */
    void SetPositionBounds(double minX, double maxX,
                          double minY, double maxY,
                          double minZ, double maxZ);
    
    /**
     * \brief Set velocity bounds for random generation (m/s)
     * \param minVx Minimum X velocity
     * \param maxVx Maximum X velocity
     * \param minVy Minimum Y velocity
     * \param maxVy Maximum Y velocity
     * \param minVz Minimum Z velocity
     * \param maxVz Maximum Z velocity
     */
    void SetVelocityBounds(double minVx, double maxVx,
                          double minVy, double maxVy,
                          double minVz, double maxVz);
    
    /**
     * \brief Set satellite visibility parameters
     * \param minSats Minimum number of visible satellites
     * \param maxSats Maximum number of visible satellites
     */
    void SetSatelliteVisibility(uint8_t minSats, uint8_t maxSats);
    
    /**
     * \brief Set the probability of valid 3D fix (0.0 to 1.0)
     * \param probability Probability of generating valid fix
     */
    void SetFixProbability(double probability);
    
    /**
     * \brief Set the initial Time of Week
     * \param tow Initial TOW in seconds
     */
    void SetInitialTOW(double tow);
    
    // ============================================================================
    // Data Generation Methods
    // ============================================================================
    
    /**
     * \brief Generate random satellite data
     * \return SatelliteData structure with random values
     */
    SatelliteData GenerateData();
    
    /**
     * \brief Generate satellite data with specific position
     * \param x X position
     * \param y Y position
     * \param z Z position
     * \return SatelliteData with specified position, random other values
     */
    SatelliteData GenerateDataAtPosition(double x, double y, double z);
    
    /**
     * \brief Serialize satellite data to byte array
     * \param data The satellite data to serialize
     * \return Vector of bytes (58 bytes total)
     */
    static std::vector<uint8_t> Serialize(const SatelliteData& data);
    
    /**
     * \brief Deserialize byte array to satellite data
     * \param bytes Input byte array (must be at least 58 bytes)
     * \return Deserialized SatelliteData structure
     */
    static SatelliteData Deserialize(const std::vector<uint8_t>& bytes);
    
    /**
     * \brief Deserialize from raw byte pointer
     * \param buffer Pointer to byte buffer
     * \param size Size of buffer (must be at least 58 bytes)
     * \return Deserialized SatelliteData structure
     */
    static SatelliteData Deserialize(const uint8_t* buffer, uint32_t size);
    
private:
    // Position bounds (meters)
    double m_minX, m_maxX;
    double m_minY, m_maxY;
    double m_minZ, m_maxZ;
    
    // Velocity bounds (m/s)
    double m_minVx, m_maxVx;
    double m_minVy, m_maxVy;
    double m_minVz, m_maxVz;
    
    // Satellite visibility
    uint8_t m_minSatellites;
    uint8_t m_maxSatellites;
    
    // Fix probability
    double m_fixProbability;
    
    // Time tracking
    double m_currentTOW;
    Time m_lastGenerationTime;
    
    // Random variable streams
    Ptr<UniformRandomVariable> m_positionRng;
    Ptr<UniformRandomVariable> m_velocityRng;
    Ptr<UniformRandomVariable> m_satelliteRng;
    Ptr<UniformRandomVariable> m_fixRng;
    
    /**
     * \brief Update TOW based on simulation time
     */
    void UpdateTOW();
    
    /**
     * \brief Helper to serialize a double to 8 bytes (IEEE 754)
     */
    static void SerializeDouble(double value, std::vector<uint8_t>& buffer);
    
    /**
     * \brief Helper to deserialize 8 bytes to double
     */
    static double DeserializeDouble(const uint8_t* buffer);
};

} // namespace ns3

#endif /* SATELLITE_H */
