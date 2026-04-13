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
 * GPS Receiver Model Implementation
 */

#include "gps.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include <sstream>
#include <iomanip>
#include <cstring>
#include <iostream>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("Gps");

NS_OBJECT_ENSURE_REGISTERED(GpsReceiver);

// ============================================================================
// GpsMessage Implementation
// ============================================================================

std::string
GpsMessage::ToString() const
{
    std::ostringstream oss;
    oss << "GpsMessage{ID=" << messageId 
        << ", RxID=" << gpsReceiverId
        << ", Time=" << timestampMs << "ms"
        << ", " << satelliteData.ToString()
        << ", CRC=0x" << std::hex << checksum << std::dec
        << "}";
    return oss.str();
}

// ============================================================================
// GpsReceiver Implementation
// ============================================================================

TypeId
GpsReceiver::GetTypeId()
{
    static TypeId tid = TypeId("ns3::GpsReceiver")
        .SetParent<Application>()
        .SetGroupName("Afdx")
        .AddConstructor<GpsReceiver>()
        .AddAttribute("ReceiverId",
                      "GPS Receiver equipment identifier",
                      UintegerValue(1),
                      MakeUintegerAccessor(&GpsReceiver::m_receiverId),
                      MakeUintegerChecker<uint16_t>())
        .AddAttribute("VirtualLinkId",
                      "AFDX Virtual Link ID for GPS data transmission",
                      UintegerValue(100),
                      MakeUintegerAccessor(&GpsReceiver::m_virtualLinkId),
                      MakeUintegerChecker<uint16_t>())
        .AddAttribute("UpdateInterval",
                      "Interval between GPS message transmissions",
                      TimeValue(MilliSeconds(100)),  // 10 Hz default
                      MakeTimeAccessor(&GpsReceiver::m_updateInterval),
                      MakeTimeChecker());
    return tid;
}

GpsReceiver::GpsReceiver()
    : m_endSystem(nullptr),
      m_satGenerator(nullptr),
      m_receiverId(1),
      m_virtualLinkId(100),
      m_updateInterval(MilliSeconds(100)),
      m_messageId(0),
      m_messagesSent(0),
      m_running(false),
      m_txCallback(MakeNullCallback<void, const GpsMessage&, uint16_t>()),
      m_satDataCallback(MakeNullCallback<void, const SatelliteData&>()),
      m_encodeCallback(MakeNullCallback<void, const GpsMessage&>())
{
    NS_LOG_FUNCTION(this);
}

GpsReceiver::~GpsReceiver()
{
    NS_LOG_FUNCTION(this);
}

void
GpsReceiver::DoDispose()
{
    NS_LOG_FUNCTION(this);
    m_endSystem = nullptr;
    m_satGenerator = nullptr;
    Application::DoDispose();
}

void
GpsReceiver::SetAfdxEndSystem(Ptr<AfdxEndSystem> endSystem)
{
    NS_LOG_FUNCTION(this << endSystem);
    m_endSystem = endSystem;
}

void
GpsReceiver::SetSatelliteGenerator(Ptr<SatelliteDataGenerator> generator)
{
    NS_LOG_FUNCTION(this << generator);
    m_satGenerator = generator;
}

void
GpsReceiver::SetReceiverId(uint16_t id)
{
    NS_LOG_FUNCTION(this << id);
    m_receiverId = id;
}

void
GpsReceiver::SetVirtualLinkId(uint16_t vlId)
{
    NS_LOG_FUNCTION(this << vlId);
    m_virtualLinkId = vlId;
}

void
GpsReceiver::SetUpdateInterval(Time interval)
{
    NS_LOG_FUNCTION(this << interval);
    m_updateInterval = interval;
}

void
GpsReceiver::SetTransmitCallback(TransmitCallback callback)
{
    NS_LOG_FUNCTION(this);
    m_txCallback = callback;
}

void
GpsReceiver::SetSatelliteDataCallback(SatelliteDataCallback callback)
{
    NS_LOG_FUNCTION(this);
    m_satDataCallback = callback;
}

void
GpsReceiver::SetGpsEncodeCallback(GpsEncodeCallback callback)
{
    NS_LOG_FUNCTION(this);
    m_encodeCallback = callback;
}

void
GpsReceiver::StartApplication()
{
    NS_LOG_FUNCTION(this);
    
    if (!m_endSystem)
    {
        NS_LOG_ERROR("GPS Receiver " << m_receiverId << " has no AFDX End System configured");
        return;
    }
    
    if (!m_satGenerator)
    {
        NS_LOG_WARN("GPS Receiver " << m_receiverId << " has no satellite generator - creating default");
        m_satGenerator = CreateObject<SatelliteDataGenerator>();
    }
    
    // Add publication authorization for our VL
    m_endSystem->AddPublication(m_virtualLinkId);
    
    m_running = true;
    m_messageId = 0;
    
    NS_LOG_INFO("GPS Receiver " << m_receiverId << " started on VL " << m_virtualLinkId
                << " with update interval " << m_updateInterval.GetMilliSeconds() << "ms");
    
    // Schedule first transmission
    ScheduleNextTransmission();
}

void
GpsReceiver::StopApplication()
{
    NS_LOG_FUNCTION(this);
    
    m_running = false;
    
    if (m_transmitEvent.IsPending())
    {
        Simulator::Cancel(m_transmitEvent);
    }
    
    NS_LOG_INFO("GPS Receiver " << m_receiverId << " stopped. Total messages sent: " << m_messagesSent);
}

void
GpsReceiver::ScheduleNextTransmission()
{
    if (m_running)
    {
        m_transmitEvent = Simulator::Schedule(m_updateInterval,
                                              &GpsReceiver::TransmitGpsData, this);
    }
}

GpsMessage
GpsReceiver::CreateMessage(const SatelliteData& satData)
{
    GpsMessage msg;
    
    msg.messageId = m_messageId++;
    msg.gpsReceiverId = m_receiverId;
    msg.timestampMs = static_cast<uint32_t>(Simulator::Now().GetMilliSeconds());
    msg.satelliteData = satData;
    msg.padding[0] = 0;
    msg.padding[1] = 0;
    
    // Calculate checksum over the message data (excluding checksum field itself)
    std::vector<uint8_t> msgData;
    msgData.reserve(GpsMessage::GetSerializedSize() - 4); // Exclude checksum
    
    // Serialize header
    msgData.push_back((msg.messageId >> 8) & 0xFF);
    msgData.push_back(msg.messageId & 0xFF);
    msgData.push_back((msg.gpsReceiverId >> 8) & 0xFF);
    msgData.push_back(msg.gpsReceiverId & 0xFF);
    msgData.push_back((msg.timestampMs >> 24) & 0xFF);
    msgData.push_back((msg.timestampMs >> 16) & 0xFF);
    msgData.push_back((msg.timestampMs >> 8) & 0xFF);
    msgData.push_back(msg.timestampMs & 0xFF);
    
    // Serialize satellite data
    std::vector<uint8_t> satBytes = SatelliteDataGenerator::Serialize(satData);
    msgData.insert(msgData.end(), satBytes.begin(), satBytes.end());
    
    msg.checksum = CalculateChecksum(msgData.data(), msgData.size());
    
    return msg;
}

void
GpsReceiver::TransmitGpsData()
{
    NS_LOG_FUNCTION(this);
    
    if (!m_running || !m_endSystem || !m_satGenerator)
    {
        return;
    }
    
    // =========================================================================
    // STEP 1: GPS Receiver receives satellite data from Satellite Generator
    // =========================================================================
    SatelliteData satData = m_satGenerator->GenerateData();
    
    std::cout << "\n╔══════════════════════════════════════════════════════════════════════╗\n";
    std::cout << "║  📡 STEP 1: GPS RECEIVER <- SATELLITE DATA                           ║\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  Time: " << std::fixed << std::setprecision(3) << Simulator::Now().GetSeconds() << "s\n";
    std::cout << "║  GPS Receiver ID: " << m_receiverId << "\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  SATELLITE PAYLOAD (58 bytes):\n";
    std::cout << "║  ┌────────────────────────────────────────────────────────────────┐\n";
    std::cout << "║  │ Position X:    " << std::setw(12) << std::setprecision(2) << satData.positionX << " m   (8 bytes, double)      │\n";
    std::cout << "║  │ Position Y:    " << std::setw(12) << satData.positionY << " m   (8 bytes, double)      │\n";
    std::cout << "║  │ Position Z:    " << std::setw(12) << satData.positionZ << " m   (8 bytes, double)      │\n";
    std::cout << "║  │ Velocity Vx:   " << std::setw(12) << satData.velocityX << " m/s (8 bytes, double)      │\n";
    std::cout << "║  │ Velocity Vy:   " << std::setw(12) << satData.velocityY << " m/s (8 bytes, double)      │\n";
    std::cout << "║  │ Velocity Vz:   " << std::setw(12) << satData.velocityZ << " m/s (8 bytes, double)      │\n";
    std::cout << "║  │ TOW:           " << std::setw(12) << std::setprecision(1) << satData.timeOfWeek << " s   (8 bytes, double)      │\n";
    std::cout << "║  │ Num Satellites:" << std::setw(12) << (int)satData.numSatellites << "     (1 byte, uint8)        │\n";
    std::cout << "║  │ Fix Type:      " << std::setw(12) << (int)satData.fixType << "     (1 byte, uint8)        │\n";
    std::cout << "║  │                " << (satData.fixType == 2 ? "       [3D FIX]" : (satData.fixType == 1 ? "       [2D FIX]" : "       [NO FIX]")) << "                         │\n";
    std::cout << "║  └────────────────────────────────────────────────────────────────┘\n";
    std::cout << "╚══════════════════════════════════════════════════════════════════════╝\n";
    
    // Invoke satellite data callback for logging (Step 1 in CSV)
    if (!m_satDataCallback.IsNull())
    {
        m_satDataCallback(satData);
    }
    
    // =========================================================================
    // STEP 2: GPS creates message with header and CRC
    // =========================================================================
    GpsMessage msg = CreateMessage(satData);
    
    std::cout << "\n╔══════════════════════════════════════════════════════════════════════╗\n";
    std::cout << "║  🔧 STEP 2: GPS ENCODES MESSAGE FOR AFDX TRANSMISSION                ║\n";
    std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
    std::cout << "║  GPS MESSAGE STRUCTURE (72 bytes total):\n";
    std::cout << "║  ┌────────────────────────────────────────────────────────────────┐\n";
    std::cout << "║  │ HEADER (8 bytes):                                              │\n";
    std::cout << "║  │   Message ID:     " << std::setw(10) << msg.messageId << "   (2 bytes, uint16)        │\n";
    std::cout << "║  │   GPS Receiver ID:" << std::setw(10) << msg.gpsReceiverId << "   (2 bytes, uint16)        │\n";
    std::cout << "║  │   Timestamp:      " << std::setw(10) << msg.timestampMs << " ms (4 bytes, uint32)       │\n";
    std::cout << "║  ├────────────────────────────────────────────────────────────────┤\n";
    std::cout << "║  │ SATELLITE DATA (58 bytes): [see above]                         │\n";
    std::cout << "║  ├────────────────────────────────────────────────────────────────┤\n";
    std::cout << "║  │ CHECKSUM:   0x" << std::hex << std::setw(8) << std::setfill('0') << msg.checksum << std::dec << std::setfill(' ') << "   (4 bytes, CRC-32)           │\n";
    std::cout << "║  │ PADDING:    0x0000         (2 bytes, alignment)                │\n";
    std::cout << "║  └────────────────────────────────────────────────────────────────┘\n";
    std::cout << "╚══════════════════════════════════════════════════════════════════════╝\n";
    
    // Invoke encode callback for logging (Step 2 in CSV)
    if (!m_encodeCallback.IsNull())
    {
        m_encodeCallback(msg);
    }
    
    // Serialize for AFDX transmission
    std::vector<uint8_t> payload = SerializeMessage(msg);
    
    // =========================================================================
    // STEP 3: Transmit via AFDX End System
    // =========================================================================
    bool success = m_endSystem->SendFrame(m_virtualLinkId, payload);
    
    if (success)
    {
        m_messagesSent++;
        
        std::cout << "\n╔══════════════════════════════════════════════════════════════════════╗\n";
        std::cout << "║  📤 STEP 3: GPS TRANSMITS VIA AFDX (Dual Network)                    ║\n";
        std::cout << "╠══════════════════════════════════════════════════════════════════════╣\n";
        std::cout << "║  Virtual Link ID: " << m_virtualLinkId << "\n";
        std::cout << "║  Payload Size:    " << payload.size() << " bytes\n";
        std::cout << "║  Networks:        Network A ✓, Network B ✓\n";
        std::cout << "╚══════════════════════════════════════════════════════════════════════╝\n\n";
        
        // Invoke callback if set
        if (!m_txCallback.IsNull())
        {
            m_txCallback(msg, m_virtualLinkId);
        }
    }
    else
    {
        NS_LOG_WARN("GPS Receiver " << m_receiverId << " failed to transmit message " << msg.messageId);
    }
    
    // Schedule next transmission
    ScheduleNextTransmission();
}

// ============================================================================
// Serialization Methods
// ============================================================================

std::vector<uint8_t>
GpsReceiver::SerializeMessage(const GpsMessage& msg)
{
    std::vector<uint8_t> buffer;
    buffer.reserve(GpsMessage::GetSerializedSize());
    
    // Message header (8 bytes)
    buffer.push_back((msg.messageId >> 8) & 0xFF);
    buffer.push_back(msg.messageId & 0xFF);
    buffer.push_back((msg.gpsReceiverId >> 8) & 0xFF);
    buffer.push_back(msg.gpsReceiverId & 0xFF);
    buffer.push_back((msg.timestampMs >> 24) & 0xFF);
    buffer.push_back((msg.timestampMs >> 16) & 0xFF);
    buffer.push_back((msg.timestampMs >> 8) & 0xFF);
    buffer.push_back(msg.timestampMs & 0xFF);
    
    // Satellite data (58 bytes)
    std::vector<uint8_t> satBytes = SatelliteDataGenerator::Serialize(msg.satelliteData);
    buffer.insert(buffer.end(), satBytes.begin(), satBytes.end());
    
    // Checksum (4 bytes)
    buffer.push_back((msg.checksum >> 24) & 0xFF);
    buffer.push_back((msg.checksum >> 16) & 0xFF);
    buffer.push_back((msg.checksum >> 8) & 0xFF);
    buffer.push_back(msg.checksum & 0xFF);
    
    // Padding (2 bytes)
    buffer.push_back(msg.padding[0]);
    buffer.push_back(msg.padding[1]);
    
    return buffer;
}

GpsMessage
GpsReceiver::DeserializeMessage(const std::vector<uint8_t>& bytes)
{
    return DeserializeMessage(bytes.data(), bytes.size());
}

GpsMessage
GpsReceiver::DeserializeMessage(const uint8_t* buffer, uint32_t size)
{
    GpsMessage msg;
    
    if (size < GpsMessage::GetSerializedSize())
    {
        NS_LOG_ERROR("Buffer too small for GPS message: " << size 
                     << " < " << GpsMessage::GetSerializedSize());
        std::memset(&msg, 0, sizeof(msg));
        return msg;
    }
    
    const uint8_t* ptr = buffer;
    
    // Message header (8 bytes)
    msg.messageId = (ptr[0] << 8) | ptr[1]; ptr += 2;
    msg.gpsReceiverId = (ptr[0] << 8) | ptr[1]; ptr += 2;
    msg.timestampMs = (ptr[0] << 24) | (ptr[1] << 16) | (ptr[2] << 8) | ptr[3]; ptr += 4;
    
    // Satellite data (58 bytes)
    msg.satelliteData = SatelliteDataGenerator::Deserialize(ptr, 58);
    ptr += 58;
    
    // Checksum (4 bytes)
    msg.checksum = (ptr[0] << 24) | (ptr[1] << 16) | (ptr[2] << 8) | ptr[3]; ptr += 4;
    
    // Padding (2 bytes)
    msg.padding[0] = ptr[0];
    msg.padding[1] = ptr[1];
    
    return msg;
}

uint32_t
GpsReceiver::CalculateChecksum(const uint8_t* data, uint32_t length)
{
    // CRC-32 implementation (IEEE 802.3 polynomial)
    static const uint32_t crcTable[256] = {
        0x00000000, 0x77073096, 0xee0e612c, 0x990951ba, 0x076dc419, 0x706af48f,
        0xe963a535, 0x9e6495a3, 0x0edb8832, 0x79dcb8a4, 0xe0d5e91e, 0x97d2d988,
        0x09b64c2b, 0x7eb17cbd, 0xe7b82d07, 0x90bf1d91, 0x1db71064, 0x6ab020f2,
        0xf3b97148, 0x84be41de, 0x1adad47d, 0x6ddde4eb, 0xf4d4b551, 0x83d385c7,
        0x136c9856, 0x646ba8c0, 0xfd62f97a, 0x8a65c9ec, 0x14015c4f, 0x63066cd9,
        0xfa0f3d63, 0x8d080df5, 0x3b6e20c8, 0x4c69105e, 0xd56041e4, 0xa2677172,
        0x3c03e4d1, 0x4b04d447, 0xd20d85fd, 0xa50ab56b, 0x35b5a8fa, 0x42b2986c,
        0xdbbbc9d6, 0xacbcf940, 0x32d86ce3, 0x45df5c75, 0xdcd60dcf, 0xabd13d59,
        0x26d930ac, 0x51de003a, 0xc8d75180, 0xbfd06116, 0x21b4f4b5, 0x56b3c423,
        0xcfba9599, 0xb8bda50f, 0x2802b89e, 0x5f058808, 0xc60cd9b2, 0xb10be924,
        0x2f6f7c87, 0x58684c11, 0xc1611dab, 0xb6662d3d, 0x76dc4190, 0x01db7106,
        0x98d220bc, 0xefd5102a, 0x71b18589, 0x06b6b51f, 0x9fbfe4a5, 0xe8b8d433,
        0x7807c9a2, 0x0f00f934, 0x9609a88e, 0xe10e9818, 0x7f6a0dbb, 0x086d3d2d,
        0x91646c97, 0xe6635c01, 0x6b6b51f4, 0x1c6c6162, 0x856530d8, 0xf262004e,
        0x6c0695ed, 0x1b01a57b, 0x8208f4c1, 0xf50fc457, 0x65b0d9c6, 0x12b7e950,
        0x8bbeb8ea, 0xfcb9887c, 0x62dd1ddf, 0x15da2d49, 0x8cd37cf3, 0xfbd44c65,
        0x4db26158, 0x3ab551ce, 0xa3bc0074, 0xd4bb30e2, 0x4adfa541, 0x3dd895d7,
        0xa4d1c46d, 0xd3d6f4fb, 0x4369e96a, 0x346ed9fc, 0xad678846, 0xda60b8d0,
        0x44042d73, 0x33031de5, 0xaa0a4c5f, 0xdd0d7a93, 0x5005713c, 0x270241aa,
        0xbe0b1010, 0xc90c2086, 0x5768b525, 0x206f85b3, 0xb966d409, 0xce61e49f,
        0x5edef90e, 0x29d9c998, 0xb0d09822, 0xc7d7a8b4, 0x59b33d17, 0x2eb40d81,
        0xb7bd5c3b, 0xc0ba6cad, 0xedb88320, 0x9abfb3b6, 0x03b6e20c, 0x74b1d29a,
        0xead54739, 0x9dd277af, 0x04db2615, 0x73dc1683, 0xe3630b12, 0x94643b84,
        0x0d6d6a3e, 0x7a6a5aa8, 0xe40ecf0b, 0x9309ff9d, 0x0a00ae27, 0x7d079eb1,
        0xf00f9344, 0x8708a3d2, 0x1e01f268, 0x6906c2fe, 0xf762575d, 0x806567cb,
        0x196c3671, 0x6e6b06e7, 0xfed41b76, 0x89d32be0, 0x10da7a5a, 0x67dd4acc,
        0xf9b9df6f, 0x8ebeeff9, 0x17b7be43, 0x60b08ed5, 0xd6d6a3e8, 0xa1d1937e,
        0x38d8c2c4, 0x4fdff252, 0xd1bb67f1, 0xa6bc5767, 0x3fb506dd, 0x48b2364b,
        0xd80d2bda, 0xaf0a1b4c, 0x36034af6, 0x41047a60, 0xdf60efc3, 0xa867df55,
        0x316e8eef, 0x4669be79, 0xcb61b38c, 0xbc66831a, 0x256fd2a0, 0x5268e236,
        0xcc0c7795, 0xbb0b4703, 0x220216b9, 0x5505262f, 0xc5ba3bbe, 0xb2bd0b28,
        0x2bb45a92, 0x5cb36a04, 0xc2d7ffa7, 0xb5d0cf31, 0x2cd99e8b, 0x5bdeae1d,
        0x9b64c2b0, 0xec63f226, 0x756aa39c, 0x026d930a, 0x9c0906a9, 0xeb0e363f,
        0x72076785, 0x05005713, 0x95bf4a82, 0xe2b87a14, 0x7bb12bae, 0x0cb61b38,
        0x92d28e9b, 0xe5d5be0d, 0x7cdcefb7, 0x0bdbdf21, 0x86d3d2d4, 0xf1d4e242,
        0x68ddb3f8, 0x1fda836e, 0x81be16cd, 0xf6b9265b, 0x6fb077e1, 0x18b74777,
        0x88085ae6, 0xff0f6a70, 0x66063bca, 0x11010b5c, 0x8f659eff, 0xf862ae69,
        0x616bffd3, 0x166ccf45, 0xa00ae278, 0xd70dd2ee, 0x4e048354, 0x3903b3c2,
        0xa7672661, 0xd06016f7, 0x4969474d, 0x3e6e77db, 0xaed16a4a, 0xd9d65adc,
        0x40df0b66, 0x37d83bf0, 0xa9bcae53, 0xdebb9ec5, 0x47b2cf7f, 0x30b5ffe9,
        0xbdbdf21c, 0xcabac28a, 0x53b39330, 0x24b4a3a6, 0xbad03605, 0xcdd706f3,
        0x54de5729, 0x23d967bf, 0xb3667a2e, 0xc4614ab8, 0x5d681b02, 0x2a6f2b94,
        0xb40bbe37, 0xc30c8ea1, 0x5a05df1b, 0x2d02ef8d
    };
    
    uint32_t crc = 0xFFFFFFFF;
    for (uint32_t i = 0; i < length; ++i)
    {
        crc = crcTable[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFF;
}

bool
GpsReceiver::VerifyChecksum(const GpsMessage& msg)
{
    // Recalculate checksum from message data
    std::vector<uint8_t> msgData;
    msgData.reserve(GpsMessage::GetSerializedSize() - 4);
    
    // Serialize header
    msgData.push_back((msg.messageId >> 8) & 0xFF);
    msgData.push_back(msg.messageId & 0xFF);
    msgData.push_back((msg.gpsReceiverId >> 8) & 0xFF);
    msgData.push_back(msg.gpsReceiverId & 0xFF);
    msgData.push_back((msg.timestampMs >> 24) & 0xFF);
    msgData.push_back((msg.timestampMs >> 16) & 0xFF);
    msgData.push_back((msg.timestampMs >> 8) & 0xFF);
    msgData.push_back(msg.timestampMs & 0xFF);
    
    // Serialize satellite data
    std::vector<uint8_t> satBytes = SatelliteDataGenerator::Serialize(msg.satelliteData);
    msgData.insert(msgData.end(), satBytes.begin(), satBytes.end());
    
    uint32_t calculatedCrc = CalculateChecksum(msgData.data(), msgData.size());
    
    return calculatedCrc == msg.checksum;
}

} // namespace ns3
