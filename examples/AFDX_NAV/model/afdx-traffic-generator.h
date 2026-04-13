/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Traffic Generator Application
 * 
 * This application generates AFDX traffic for testing and simulation purposes.
 * It respects BAG (Bandwidth Allocation Gap) constraints and generates
 * realistic AFDX frames.
 */

#ifndef AFDX_TRAFFIC_GENERATOR_H
#define AFDX_TRAFFIC_GENERATOR_H

#include "ns3/application.h"
#include "ns3/net-device.h"
#include "ns3/packet.h"
#include "ns3/mac48-address.h"
#include "ns3/nstime.h"
#include "ns3/event-id.h"
#include "afdx-virtual-link.h"
#include "afdx-frame.h"
#include <map>
#include <set>
#include <fstream>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief AFDX End System Application (Complete TX/RX)
 *
 * Complete AFDX End System implementing ARINC 664 Part 7:
 * 
 * TRANSMIT (Publisher):
 * - Dual network transmission (Network A & B)
 * - BAG-compliant traffic generation
 * - Sequence numbering (1-255, wraps to 1)
 * - Multiple VL support
 * 
 * RECEIVE (Subscriber):
 * - Dual network reception
 * - Integrity checking (sequence validation [PSN+1, PSN+2])
 * - Redundancy management ("First Valid Frame Wins")
 * - Constant field validation (03:00:00:00)
 * - Duplicate frame rejection
 */
class AfdxTrafficGenerator : public Application
{
public:
  static TypeId GetTypeId();

  AfdxTrafficGenerator();
  virtual ~AfdxTrafficGenerator();

  /**
   * \brief Set the network device to transmit on (DEPRECATED - use SetDualNetworkDevices)
   */
  void SetNetDevice(Ptr<NetDevice> device);

  /**
   * \brief Set dual network devices for AFDX redundancy (ARINC 664 P7 §3.2.6)
   * \param networkA Network A device (primary)
   * \param networkB Network B device (redundant)
   * 
   * AFDX requires dual redundant transmission. Each frame is sent on both
   * Network A and Network B within 0.5ms of each other for fault tolerance.
   */
  void SetDualNetworkDevices(Ptr<NetDevice> networkA, Ptr<NetDevice> networkB);

  /**
   * \brief Add a Virtual Link to generate traffic for (Publisher)
   * \param vl The Virtual Link configuration
   * \param payloadSize Size of payload to generate (must be within VL min/max range)
   */
  void AddVirtualLink(const AfdxVirtualLink& vl, uint32_t payloadSize);

  /**
   * \brief Subscribe to a Virtual Link for receiving (Subscriber)
   * \param vlId Virtual Link ID to subscribe to
   * 
   * Enables this End System to receive frames for the specified VL.
   * Implements integrity checking and redundancy management.
   */
  void SubscribeToVirtualLink(uint16_t vlId);

  /**
   * \brief Enable CSV logging
   */
  void EnableCsvLogging(const std::string& filename);

  /**
   * \brief Get number of frames sent
   */
  uint32_t GetFramesSent() const { return m_framesSent; }

  /**
   * \brief Get number of frames received
   */
  uint32_t GetFramesReceived() const { return m_framesReceived; }

  /**
   * \brief Get number of frames rejected (failed validation)
   */
  uint32_t GetFramesRejected() const { return m_framesRejected; }

  /**
   * \brief Get number of duplicate frames discarded
   */
  uint32_t GetDuplicatesDiscarded() const { return m_duplicatesDiscarded; }

protected:
  virtual void StartApplication();
  virtual void StopApplication();

private:
  // ====================================================================
  // TRANSMIT SIDE (Publisher)
  // ====================================================================
  
  /**
   * \brief Schedule next transmission for a VL
   */
  void ScheduleTransmit(uint16_t vlId);

  /**
   * \brief Transmit a frame for a VL
   */
  void TransmitFrame(uint16_t vlId);

  /**
   * \brief Transmit on Network B (delayed for redundancy)
   */
  void TransmitOnNetworkB(Ptr<Packet> packet, Mac48Address dest, uint16_t vlId, uint8_t seqNum);

  // ====================================================================
  // RECEIVE SIDE (Subscriber)
  // ====================================================================
  
  /**
   * \brief Receive callback for Network A
   */
  bool ReceiveFromNetworkA(Ptr<NetDevice> device, Ptr<const Packet> packet,
                           uint16_t protocol, const Address& from);

  /**
   * \brief Receive callback for Network B
   */
  bool ReceiveFromNetworkB(Ptr<NetDevice> device, Ptr<const Packet> packet,
                           uint16_t protocol, const Address& from);

  /**
   * \brief Process received frame (common for both networks)
   * \param packet The received packet
   * \param networkId "A" or "B"
   * \return true if frame accepted, false if rejected/duplicate
   */
  bool ProcessReceivedFrame(Ptr<const Packet> packet, const std::string& networkId);

  /**
   * \brief Validate constant field in MAC address (ARINC 664 P7 §3.1.1.3.3)
   * \param frame The AFDX frame to validate
   * \return true if constant field is valid (03:00:00:00)
   */
  bool ValidateConstantField(const AfdxFrame& frame);

  /**
   * \brief Check if this ES is subscribed to a VL
   */
  bool IsSubscribedToVL(uint16_t vlId);

  /**
   * \brief Integrity Checking: Validate sequence number (ARINC 664 P7 §3.2.6.2.1)
   * \param vlId Virtual Link ID
   * \param seqNum Received sequence number
   * \return true if sequence is valid [PSN+1, PSN+2], false otherwise
   * 
   * Valid range is [PSN+1, PSN+2] where PSN = Previous Sequence Number.
   * Handles wrap-around: 255 → 1 (sequence 0 is INVALID per ARINC spec).
   */
  bool CheckSequenceNumber(uint16_t vlId, uint8_t seqNum);

  /**
   * \brief Redundancy Management: "First Valid Frame Wins" (ARINC 664 P7 §3.2.6.2.2)
   * \param vlId Virtual Link ID
   * \param seqNum Sequence number of received frame
   * \param networkId "A" or "B"
   * \return true if this is the first valid frame, false if duplicate
   * 
   * Accepts the first valid frame from either Network A or B.
   * Rejects duplicate frame from the other network.
   */
  bool ApplyFirstValidFrameWins(uint16_t vlId, uint8_t seqNum, const std::string& networkId);

  /**
   * \brief Log event to CSV
   */
  void LogToCsv(const std::string& event, uint16_t vlId, 
                const std::string& action, const std::string& details);

  // ====================================================================
  // NETWORK DEVICES (Dual redundancy)
  // ====================================================================
  Ptr<NetDevice> m_device;          // Legacy single device (for backward compatibility)
  Ptr<NetDevice> m_deviceNetworkA;  // Network A (primary)
  Ptr<NetDevice> m_deviceNetworkB;  // Network B (redundant)
  bool m_dualNetworkMode;            // True if using dual networks

  // ====================================================================
  // TRANSMIT SIDE - VL Configuration
  // ====================================================================
  struct VLTrafficConfig
  {
    AfdxVirtualLink vl;
    uint32_t payloadSize;
    uint8_t sequenceNumber;
    EventId transmitEvent;
  };
  std::map<uint16_t, VLTrafficConfig> m_vlConfigs;

  // ====================================================================
  // RECEIVE SIDE - Subscription and Validation
  // ====================================================================
  
  // VL subscriptions (which VLs this ES receives)
  std::set<uint16_t> m_subscribedVLs;
  
  // Redundancy management state per VL
  struct RedundancyState
  {
    uint8_t lastSeqNum;           // Last accepted sequence number
    std::string firstNetwork;     // Which network delivered first ("A" or "B")
    bool receivedThisSeq;         // True if already received this sequence
  };
  std::map<uint16_t, RedundancyState> m_redundancyState;
  
  // Integrity checking: Previous Sequence Number (PSN) per VL
  std::map<uint16_t, uint8_t> m_previousSeqNum;

  // ====================================================================
  // CSV LOGGING
  // ====================================================================
  bool m_csvEnabled;
  std::string m_csvFilename;
  std::ofstream m_csvFile;

  // ====================================================================
  // STATISTICS
  // ====================================================================
  // Transmit statistics
  uint32_t m_framesSent;
  
  // Receive statistics
  uint32_t m_framesReceived;        // Successfully received and accepted
  uint32_t m_framesRejected;        // Failed validation (sequence, constant field, etc.)
  uint32_t m_duplicatesDiscarded;   // Duplicate frames rejected (redundancy mgmt)

};

} // namespace ns3

#endif /* AFDX_TRAFFIC_GENERATOR_H */
