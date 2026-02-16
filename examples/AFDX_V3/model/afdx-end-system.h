/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX End System - ARINC 664 Part 7
 */

#ifndef AFDX_END_SYSTEM_H
#define AFDX_END_SYSTEM_H

#include "ns3/application.h"
#include "ns3/node.h"
#include "ns3/net-device.h"
#include "ns3/packet.h"
#include "ns3/mac48-address.h"
#include "afdx-virtual-link.h"
#include "afdx-frame.h"
#include <map>
#include <vector>
#include <fstream>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief AFDX End System Application
 *
 * Implements ARINC 664 Part 7 End System logic:
 * - VL management and transmission
 * - Frame validation (5 steps)
 * - First Valid Frame Wins (redundancy management)
 * - Sequence number checking
 * - BAG enforcement
 */
class AfdxEndSystem : public Application
{
public:
  static TypeId GetTypeId();

  AfdxEndSystem();
  virtual ~AfdxEndSystem();

  // Configuration
  void SetNodeId(uint32_t nodeId);
  void SetCsvFile(const std::string& filename);
  
  // VL Management
  void AddTransmitVL(const AfdxVirtualLink& vl);
  void AddReceiveVL(uint16_t vlId);
  
  // Network interfaces (for redundancy)
  void SetNetworkADevice(Ptr<NetDevice> device);
  void SetNetworkBDevice(Ptr<NetDevice> device);

protected:
  virtual void StartApplication();
  virtual void StopApplication();

private:
  // Transmission
  void ScheduleNextTransmission(uint16_t vlId);
  void SendFrame(uint16_t vlId);
  void TransmitOnNetwork(Ptr<Packet> packet, Ptr<NetDevice> device, Mac48Address dst);

  // Reception
  bool ReceiveFromNetworkA(Ptr<NetDevice> device, Ptr<const Packet> packet,
                           uint16_t protocol, const Address& from);
  bool ReceiveFromNetworkB(Ptr<NetDevice> device, Ptr<const Packet> packet,
                           uint16_t protocol, const Address& from);
  void ProcessReceivedFrame(Ptr<const Packet> packet, const std::string& networkId);

  // AFDX Protocol Logic
  bool ValidateFrame(const AfdxFrame& frame, uint32_t frameSize);
  bool CheckVLSubscription(uint16_t vlId);
  bool CheckSequenceNumber(uint16_t vlId, uint8_t seqNum);
  bool ApplyFirstValidFrameWins(uint16_t vlId, const std::string& networkId);

  // CSV Logging
  void InitializeCsvFile();
  void LogEvent(const std::string& eventType, const std::string& details);
  void LogComprehensiveCsvEvent(const std::string& event, uint16_t vlId, uint8_t seqNum, 
                               const std::string& network, bool isDuplicate,
                               const std::string& srcMac, const std::string& dstMac,
                               uint32_t packetSize, const std::string& description);
  void LogTxEvent(uint16_t vlId, uint8_t seqNum, const std::string& network, uint32_t size);
  void LogRxEvent(uint16_t vlId, uint8_t seqNum, const std::string& network, 
                  const std::string& status, const std::string& reason);

  // Member variables
  uint32_t m_nodeId;
  std::string m_csvFilename;
  std::ofstream m_csvFile;

  // Network interfaces
  Ptr<NetDevice> m_deviceA;  // Network A (redundancy)
  Ptr<NetDevice> m_deviceB;  // Network B (redundancy)

  // Virtual Links
  std::map<uint16_t, AfdxVirtualLink> m_transmitVLs;  // VLs this ES transmits
  std::vector<uint16_t> m_receiveVLs;                 // VLs this ES receives

  // Transmission state
  std::map<uint16_t, uint8_t> m_sequenceNumbers;      // Current seq num per VL
  std::map<uint16_t, EventId> m_transmissionEvents;   // Scheduled TX events

  // Reception state - First Valid Frame Wins
  struct FrameReceptionState
  {
    uint8_t lastValidSeqNum;
    std::string acceptedNetwork;  // "A" or "B"
    bool frameReceived;
  };
  std::map<uint16_t, FrameReceptionState> m_receptionState;

  // Statistics
  uint32_t m_framesSent;
  uint32_t m_framesReceived;
  uint32_t m_framesRejected;
  uint32_t m_duplicatesDiscarded;
};

} // namespace ns3

#endif /* AFDX_END_SYSTEM_H */
