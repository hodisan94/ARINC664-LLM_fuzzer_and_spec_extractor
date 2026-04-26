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
 * Satellite Data Model Implementation
 */

#include "satellite.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/double.h"
#include <sstream>
#include <iomanip>
#include <cstring>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("Satellite");

NS_OBJECT_ENSURE_REGISTERED(SatelliteDataGenerator);

// ============================================================================
// SatelliteData Implementation
// ============================================================================

std::string
SatelliteData::ToString() const
{
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(2);
    oss << "SatelliteData{"
        << "Pos=(" << positionX << "," << positionY << "," << positionZ << ")m, "
        << "Vel=(" << velocityX << "," << velocityY << "," << velocityZ << ")m/s, "
        << "TOW=" << timeOfWeek << "s, "
        << "Sats=" << (int)numSatellites << ", "
        << "Fix=" << (int)fixType << (IsValidFix() ? "(3D)" : "(invalid)")
        << "}";
    return oss.str();
}

// ============================================================================
// SatelliteDataGenerator Implementation
// ============================================================================

TypeId
SatelliteDataGenerator::GetTypeId()
{
    static TypeId tid = TypeId("ns3::SatelliteDataGenerator")
        .SetParent<Object>()
        .SetGroupName("Afdx")
        .AddConstructor<SatelliteDataGenerator>();
    return tid;
}

SatelliteDataGenerator::SatelliteDataGenerator()
    : m_minX(-100000.0), m_maxX(100000.0),    // ±100km range
      m_minY(-100000.0), m_maxY(100000.0),
      m_minZ(0.0), m_maxZ(15000.0),           // 0-15km altitude
      m_minVx(-300.0), m_maxVx(300.0),        // ±300 m/s (typical aircraft)
      m_minVy(-300.0), m_maxVy(300.0),
      m_minVz(-50.0), m_maxVz(50.0),          // ±50 m/s vertical
      m_minSatellites(4), m_maxSatellites(12),
      m_fixProbability(0.95),                  // 95% valid fix probability
      m_currentTOW(0.0),
      m_lastGenerationTime(Seconds(0))
{
    NS_LOG_FUNCTION(this);
    
    // Initialize random variable streams
    m_positionRng = CreateObject<UniformRandomVariable>();
    m_velocityRng = CreateObject<UniformRandomVariable>();
    m_satelliteRng = CreateObject<UniformRandomVariable>();
    m_fixRng = CreateObject<UniformRandomVariable>();
    
    m_fixRng->SetAttribute("Min", DoubleValue(0.0));
    m_fixRng->SetAttribute("Max", DoubleValue(1.0));
}

SatelliteDataGenerator::~SatelliteDataGenerator()
{
    NS_LOG_FUNCTION(this);
}

void
SatelliteDataGenerator::SetPositionBounds(double minX, double maxX,
                                          double minY, double maxY,
                                          double minZ, double maxZ)
{
    NS_LOG_FUNCTION(this << minX << maxX << minY << maxY << minZ << maxZ);
    m_minX = minX; m_maxX = maxX;
    m_minY = minY; m_maxY = maxY;
    m_minZ = minZ; m_maxZ = maxZ;
}

void
SatelliteDataGenerator::SetVelocityBounds(double minVx, double maxVx,
                                          double minVy, double maxVy,
                                          double minVz, double maxVz)
{
    NS_LOG_FUNCTION(this << minVx << maxVx << minVy << maxVy << minVz << maxVz);
    m_minVx = minVx; m_maxVx = maxVx;
    m_minVy = minVy; m_maxVy = maxVy;
    m_minVz = minVz; m_maxVz = maxVz;
}

void
SatelliteDataGenerator::SetSatelliteVisibility(uint8_t minSats, uint8_t maxSats)
{
    NS_LOG_FUNCTION(this << (int)minSats << (int)maxSats);
    m_minSatellites = minSats;
    m_maxSatellites = maxSats;
}

void
SatelliteDataGenerator::SetFixProbability(double probability)
{
    NS_LOG_FUNCTION(this << probability);
    m_fixProbability = std::max(0.0, std::min(1.0, probability));
}

void
SatelliteDataGenerator::SetInitialTOW(double tow)
{
    NS_LOG_FUNCTION(this << tow);
    m_currentTOW = std::fmod(tow, 604800.0); // Wrap at 1 week (604800 seconds)
}

void
SatelliteDataGenerator::UpdateTOW()
{
    Time now = Simulator::Now();
    double elapsed = (now - m_lastGenerationTime).GetSeconds();
    m_currentTOW = std::fmod(m_currentTOW + elapsed, 604800.0);
    m_lastGenerationTime = now;
}

SatelliteData
SatelliteDataGenerator::GenerateData()
{
    NS_LOG_FUNCTION(this);
    
    UpdateTOW();
    
    SatelliteData data;
    
    // Generate random position
    m_positionRng->SetAttribute("Min", DoubleValue(m_minX));
    m_positionRng->SetAttribute("Max", DoubleValue(m_maxX));
    data.positionX = m_positionRng->GetValue();
    
    m_positionRng->SetAttribute("Min", DoubleValue(m_minY));
    m_positionRng->SetAttribute("Max", DoubleValue(m_maxY));
    data.positionY = m_positionRng->GetValue();
    
    m_positionRng->SetAttribute("Min", DoubleValue(m_minZ));
    m_positionRng->SetAttribute("Max", DoubleValue(m_maxZ));
    data.positionZ = m_positionRng->GetValue();
    
    // Generate random velocity
    m_velocityRng->SetAttribute("Min", DoubleValue(m_minVx));
    m_velocityRng->SetAttribute("Max", DoubleValue(m_maxVx));
    data.velocityX = m_velocityRng->GetValue();
    
    m_velocityRng->SetAttribute("Min", DoubleValue(m_minVy));
    m_velocityRng->SetAttribute("Max", DoubleValue(m_maxVy));
    data.velocityY = m_velocityRng->GetValue();
    
    m_velocityRng->SetAttribute("Min", DoubleValue(m_minVz));
    m_velocityRng->SetAttribute("Max", DoubleValue(m_maxVz));
    data.velocityZ = m_velocityRng->GetValue();
    
    // Set TOW
    data.timeOfWeek = m_currentTOW;
    
    // Generate satellite count
    m_satelliteRng->SetAttribute("Min", DoubleValue(m_minSatellites));
    m_satelliteRng->SetAttribute("Max", DoubleValue(m_maxSatellites + 1));
    data.numSatellites = static_cast<uint8_t>(m_satelliteRng->GetInteger());
    
    // Determine fix type based on probability and satellite count
    double fixRoll = m_fixRng->GetValue();
    if (data.numSatellites >= 4 && fixRoll < m_fixProbability)
    {
        data.fixType = static_cast<uint8_t>(SatelliteFixType::FIX_3D);
    }
    else if (data.numSatellites >= 3 && fixRoll < m_fixProbability * 0.5)
    {
        data.fixType = static_cast<uint8_t>(SatelliteFixType::FIX_2D);
    }
    else
    {
        data.fixType = static_cast<uint8_t>(SatelliteFixType::NO_FIX);
    }
    
    NS_LOG_INFO("Generated satellite data: " << data.ToString());
    
    return data;
}

SatelliteData
SatelliteDataGenerator::GenerateDataAtPosition(double x, double y, double z)
{
    NS_LOG_FUNCTION(this << x << y << z);
    
    SatelliteData data = GenerateData();
    data.positionX = x;
    data.positionY = y;
    data.positionZ = z;
    
    return data;
}

void
SatelliteDataGenerator::SerializeDouble(double value, std::vector<uint8_t>& buffer)
{
    // IEEE 754 double precision (8 bytes)
    uint64_t bits;
    std::memcpy(&bits, &value, sizeof(double));
    
    // Store in big-endian (network byte order)
    for (int i = 7; i >= 0; --i)
    {
        buffer.push_back(static_cast<uint8_t>((bits >> (i * 8)) & 0xFF));
    }
}

double
SatelliteDataGenerator::DeserializeDouble(const uint8_t* buffer)
{
    // Read from big-endian (network byte order)
    uint64_t bits = 0;
    for (int i = 0; i < 8; ++i)
    {
        bits = (bits << 8) | buffer[i];
    }
    
    double value;
    std::memcpy(&value, &bits, sizeof(double));
    return value;
}

std::vector<uint8_t>
SatelliteDataGenerator::Serialize(const SatelliteData& data)
{
    std::vector<uint8_t> buffer;
    buffer.reserve(SatelliteData::GetSerializedSize());
    
    // Serialize position (24 bytes)
    SerializeDouble(data.positionX, buffer);
    SerializeDouble(data.positionY, buffer);
    SerializeDouble(data.positionZ, buffer);
    
    // Serialize velocity (24 bytes)
    SerializeDouble(data.velocityX, buffer);
    SerializeDouble(data.velocityY, buffer);
    SerializeDouble(data.velocityZ, buffer);
    
    // Serialize TOW (8 bytes)
    SerializeDouble(data.timeOfWeek, buffer);
    
    // Serialize satellite count (1 byte)
    buffer.push_back(data.numSatellites);
    
    // Serialize fix type (1 byte)
    buffer.push_back(data.fixType);
    
    NS_LOG_DEBUG("Serialized satellite data: " << buffer.size() << " bytes");
    
    return buffer;
}

SatelliteData
SatelliteDataGenerator::Deserialize(const std::vector<uint8_t>& bytes)
{
    return Deserialize(bytes.data(), bytes.size());
}

SatelliteData
SatelliteDataGenerator::Deserialize(const uint8_t* buffer, uint32_t size)
{
    SatelliteData data;
    
    if (size < SatelliteData::GetSerializedSize())
    {
        NS_LOG_ERROR("Buffer too small for satellite data deserialization: " 
                     << size << " < " << SatelliteData::GetSerializedSize());
        // Return zeroed data
        data.positionX = data.positionY = data.positionZ = 0.0;
        data.velocityX = data.velocityY = data.velocityZ = 0.0;
        data.timeOfWeek = 0.0;
        data.numSatellites = 0;
        data.fixType = 0;
        return data;
    }
    
    const uint8_t* ptr = buffer;
    
    // Deserialize position (24 bytes)
    data.positionX = DeserializeDouble(ptr); ptr += 8;
    data.positionY = DeserializeDouble(ptr); ptr += 8;
    data.positionZ = DeserializeDouble(ptr); ptr += 8;
    
    // Deserialize velocity (24 bytes)
    data.velocityX = DeserializeDouble(ptr); ptr += 8;
    data.velocityY = DeserializeDouble(ptr); ptr += 8;
    data.velocityZ = DeserializeDouble(ptr); ptr += 8;
    
    // Deserialize TOW (8 bytes)
    data.timeOfWeek = DeserializeDouble(ptr); ptr += 8;
    
    // Deserialize satellite count (1 byte)
    data.numSatellites = *ptr; ptr += 1;
    
    // Deserialize fix type (1 byte)
    data.fixType = *ptr;
    
    NS_LOG_DEBUG("Deserialized satellite data: " << data.ToString());
    
    return data;
}

} // namespace ns3
