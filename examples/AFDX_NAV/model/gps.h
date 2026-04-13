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
 * GPS Receiver Model for AFDX Navigation Application
 * Receives satellite data and encodes it for AFDX frame transmission
 */

#ifndef GPS_H
#define GPS_H

#include "satellite.h"
#include "afdx-end-system.h"
#include "ns3/object.h"
#include "ns3/application.h"
#include "ns3/event-id.h"
#include "ns3/nstime.h"
#include "ns3/callback.h"
#include <vector>
#include <functional>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief GPS Data Message for AFDX transmission
 * 
 * Encapsulates satellite data with additional GPS receiver metadata
 * for AFDX frame payload. Compliant with ARINC 664 Part 7 payload requirements.
 * 
 * AFDX Frame constraints:
 * - Minimum payload: 17 bytes
 * - Maximum payload: 1471 bytes (for 1518 byte max frame)
 * 
 * GPS Message Structure (72 bytes total):
 * - Message header: 8 bytes
 *   - Message ID: 2 bytes
 *   - GPS Receiver ID: 2 bytes  
 *   - Timestamp (ms): 4 bytes
 * - Satellite data: 58 bytes
 * - Checksum: 4 bytes
 * - Padding: 2 bytes (for alignment)
 */
struct GpsMessage
{
    // Message header (8 bytes)
    uint16_t messageId;        ///< Message identifier for sequencing
    uint16_t gpsReceiverId;    ///< GPS receiver equipment ID
    uint32_t timestampMs;      ///< Timestamp in milliseconds
    
    // Satellite data payload (58 bytes)
    SatelliteData satelliteData;
    
    // Integrity (4 bytes)
    uint32_t checksum;         ///< CRC-32 checksum for data integrity
    
    // Padding (2 bytes for 8-byte alignment)
    uint8_t padding[2];
    
    /**
     * \brief Get total message size
     * \return Size in bytes (72 bytes)
     */
    static constexpr uint32_t GetSerializedSize() { return 72; }
    
    /**
     * \brief Convert to string representation
     */
    std::string ToString() const;
};

/**
 * \ingroup afdx
 * \brief GPS Receiver Application for AFDX End System
 * 
 * This application models a GPS receiver that:
 * 1. Receives satellite data from SatelliteDataGenerator
 * 2. Packages it into GPS messages with proper headers
 * 3. Transmits via AFDX Virtual Link to Flight Control systems
 * 
 * Implements ARINC 664 Part 7 compliant transmission with:
 * - Configurable update rate (1-50 Hz typical for aviation GPS)
 * - BAG (Bandwidth Allocation Gap) compliance
 * - Proper AFDX frame encapsulation
 */
class GpsReceiver : public Application
{
public:
    /**
     * \brief Get the type ID
     * \return the object TypeId
     */
    static TypeId GetTypeId();
    
    GpsReceiver();
    virtual ~GpsReceiver();
    
    // ============================================================================
    // Configuration Methods
    // ============================================================================
    
    /**
     * \brief Set the AFDX End System for this GPS receiver
     * \param endSystem Pointer to the AFDX End System
     */
    void SetAfdxEndSystem(Ptr<AfdxEndSystem> endSystem);
    
    /**
     * \brief Set the satellite data generator
     * \param generator Pointer to satellite data generator
     */
    void SetSatelliteGenerator(Ptr<SatelliteDataGenerator> generator);
    
    /**
     * \brief Set the GPS receiver equipment ID
     * \param id Equipment identifier (used in AFDX addressing)
     */
    void SetReceiverId(uint16_t id);
    
    /**
     * \brief Set the Virtual Link ID for GPS data transmission
     * \param vlId Virtual Link identifier
     */
    void SetVirtualLinkId(uint16_t vlId);
    
    /**
     * \brief Set the update interval for GPS data transmission
     * \param interval Update interval (typical: 50ms to 1s for aviation)
     */
    void SetUpdateInterval(Time interval);
    
    /**
     * \brief Set callback for transmitted GPS messages
     * \param callback Function called when GPS message is transmitted
     */
    typedef Callback<void, const GpsMessage&, uint16_t> TransmitCallback;
    void SetTransmitCallback(TransmitCallback callback);
    
    /**
     * \brief Set callback for satellite data reception
     * \param callback Function called when satellite data is received from generator
     */
    typedef Callback<void, const SatelliteData&> SatelliteDataCallback;
    void SetSatelliteDataCallback(SatelliteDataCallback callback);
    
    /**
     * \brief Set callback for GPS message encoding
     * \param callback Function called when GPS message is encoded (before transmission)
     */
    typedef Callback<void, const GpsMessage&> GpsEncodeCallback;
    void SetGpsEncodeCallback(GpsEncodeCallback callback);
    
    // ============================================================================
    // Data Methods
    // ============================================================================
    
    /**
     * \brief Serialize GPS message to byte array for AFDX payload
     * \param msg GPS message to serialize
     * \return Vector of bytes for AFDX frame payload
     */
    static std::vector<uint8_t> SerializeMessage(const GpsMessage& msg);
    
    /**
     * \brief Deserialize byte array to GPS message
     * \param bytes Input byte array
     * \return Deserialized GPS message
     */
    static GpsMessage DeserializeMessage(const std::vector<uint8_t>& bytes);
    
    /**
     * \brief Deserialize from raw byte pointer
     * \param buffer Pointer to byte buffer
     * \param size Size of buffer
     * \return Deserialized GPS message
     */
    static GpsMessage DeserializeMessage(const uint8_t* buffer, uint32_t size);
    
    /**
     * \brief Calculate CRC-32 checksum
     * \param data Data buffer
     * \param length Data length
     * \return CRC-32 checksum value
     */
    static uint32_t CalculateChecksum(const uint8_t* data, uint32_t length);
    
    /**
     * \brief Verify message checksum
     * \param msg GPS message to verify
     * \return true if checksum is valid
     */
    static bool VerifyChecksum(const GpsMessage& msg);
    
    // ============================================================================
    // Statistics
    // ============================================================================
    
    /**
     * \brief Get number of messages transmitted
     * \return Count of transmitted messages
     */
    uint32_t GetMessagesSent() const { return m_messagesSent; }
    
    /**
     * \brief Get current message ID
     * \return Current message sequence number
     */
    uint16_t GetCurrentMessageId() const { return m_messageId; }

protected:
    virtual void DoDispose();

private:
    virtual void StartApplication();
    virtual void StopApplication();
    
    /**
     * \brief Generate and transmit GPS message
     */
    void TransmitGpsData();
    
    /**
     * \brief Schedule next transmission
     */
    void ScheduleNextTransmission();
    
    /**
     * \brief Create GPS message from satellite data
     * \param satData Satellite data
     * \return Complete GPS message with headers and checksum
     */
    GpsMessage CreateMessage(const SatelliteData& satData);
    
    // Configuration
    Ptr<AfdxEndSystem> m_endSystem;
    Ptr<SatelliteDataGenerator> m_satGenerator;
    uint16_t m_receiverId;
    uint16_t m_virtualLinkId;
    Time m_updateInterval;
    
    // State
    uint16_t m_messageId;
    uint32_t m_messagesSent;
    EventId m_transmitEvent;
    bool m_running;
    
    // Callbacks
    TransmitCallback m_txCallback;
    SatelliteDataCallback m_satDataCallback;
    GpsEncodeCallback m_encodeCallback;
};

} // namespace ns3

#endif /* GPS_H */
