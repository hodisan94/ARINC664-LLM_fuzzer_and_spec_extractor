/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX End System Implementation
 */

#include "afdx-end-system.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/csma-net-device.h"
#include <iomanip>
#include <sstream>
#include <fstream>
#include <cstring>
#include <algorithm>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("AfdxEndSystem");

NS_OBJECT_ENSURE_REGISTERED(AfdxEndSystem);

TypeId
AfdxEndSystem::GetTypeId()
{
  static TypeId tid = TypeId("ns3::AfdxEndSystem")
                          .SetParent<Application>()
                          .SetGroupName("Afdx")
                          .AddConstructor<AfdxEndSystem>();
  return tid;
}

AfdxEndSystem::AfdxEndSystem()
    : m_nodeId(0),
      m_csvFilename(""),
      m_framesSent(0),
      m_framesReceived(0),
      m_framesRejected(0),
      m_duplicatesDiscarded(0)
{
  NS_LOG_FUNCTION(this);
}

AfdxEndSystem::~AfdxEndSystem()
{
  NS_LOG_FUNCTION(this);
}

void
AfdxEndSystem::SetNodeId(uint32_t nodeId)
{
  m_nodeId = nodeId;
}

void
AfdxEndSystem::SetCsvFile(const std::string& filename)
{
  m_csvFilename = filename;
}

void
AfdxEndSystem::AddTransmitVL(const AfdxVirtualLink& vl)
{
  NS_LOG_FUNCTION(this << vl.GetVlId());
  
  if (!vl.IsValid())
  {
    NS_LOG_ERROR("Invalid VL configuration for VL " << vl.GetVlId());
    return;
  }

  m_transmitVLs[vl.GetVlId()] = vl;
  m_sequenceNumbers[vl.GetVlId()] = 0;
  
  NS_LOG_INFO("ES" << m_nodeId << " added TX VL " << vl.GetVlId() 
              << " BAG=" << vl.GetBag().GetMilliSeconds() << "ms");
}

void
AfdxEndSystem::AddReceiveVL(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  m_receiveVLs.push_back(vlId);
  
  // Initialize reception state
  FrameReceptionState state;
  state.lastValidSeqNum = 255;  // Invalid initial value
  state.acceptedNetwork = "";
  state.frameReceived = false;
  m_receptionState[vlId] = state;
  
  NS_LOG_INFO("ES" << m_nodeId << " subscribed to RX VL " << vlId);
}

void
AfdxEndSystem::SetNetworkADevice(Ptr<NetDevice> device)
{
  m_deviceA = device;
  device->SetReceiveCallback(MakeCallback(&AfdxEndSystem::ReceiveFromNetworkA, this));
  NS_LOG_INFO("ES" << m_nodeId << " connected to Network A");
}

void
AfdxEndSystem::SetNetworkBDevice(Ptr<NetDevice> device)
{
  m_deviceB = device;
  device->SetReceiveCallback(MakeCallback(&AfdxEndSystem::ReceiveFromNetworkB, this));
  NS_LOG_INFO("ES" << m_nodeId << " connected to Network B");
}

void
AfdxEndSystem::StartApplication()
{
  NS_LOG_FUNCTION(this);
  
  InitializeCsvFile();
  
  // Schedule first transmission for each VL
  for (auto& entry : m_transmitVLs)
  {
    uint16_t vlId = entry.first;
    Time bag = entry.second.GetBag();
    
    // Start at different times to avoid synchronization
    Time startTime = MilliSeconds(10 + vlId % 50);
    
    EventId event = Simulator::Schedule(startTime, 
                                        &AfdxEndSystem::SendFrameInternal, 
                                        this, vlId);
    m_transmissionEvents[vlId] = event;
    
    NS_LOG_INFO("ES" << m_nodeId << " scheduled VL" << vlId 
                << " first TX at " << startTime.GetSeconds() << "s");
  }
}

void
AfdxEndSystem::StopApplication()
{
  NS_LOG_FUNCTION(this);
  
  // Cancel all scheduled transmissions
  for (auto& entry : m_transmissionEvents)
  {
    Simulator::Cancel(entry.second);
  }
  m_transmissionEvents.clear();
  
  // Log final statistics
  NS_LOG_INFO("ES" << m_nodeId << " Statistics:");
  NS_LOG_INFO("  Frames Sent: " << m_framesSent);
  NS_LOG_INFO("  Frames Received: " << m_framesReceived);
  NS_LOG_INFO("  Frames Rejected: " << m_framesRejected);
  NS_LOG_INFO("  Duplicates Discarded: " << m_duplicatesDiscarded);
  
  if (m_csvFile.is_open())
  {
    m_csvFile << "\n# Statistics for ES" << m_nodeId << "\n";
    m_csvFile << "# Frames Sent: " << m_framesSent << "\n";
    m_csvFile << "# Frames Received: " << m_framesReceived << "\n";
    m_csvFile << "# Frames Rejected: " << m_framesRejected << "\n";
    m_csvFile << "# Duplicates Discarded: " << m_duplicatesDiscarded << "\n";
    m_csvFile.close();
  }
}

void
AfdxEndSystem::SendFrameInternal(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  auto it = m_transmitVLs.find(vlId);
  if (it == m_transmitVLs.end())
  {
    NS_LOG_ERROR("ES" << m_nodeId << " attempted to send on unconfigured VL " << vlId);
    return;
  }
  
  const AfdxVirtualLink& vl = it->second;
  
  // Get current sequence number
  uint8_t seqNum = m_sequenceNumbers[vlId];
  
  // Create AFDX frame
  AfdxFrame frame;
  frame.SetVirtualLinkId(vlId);
  frame.SetSequenceNumber(seqNum);
  frame.SetSourceAddress(vl.GetSourceMac());
  frame.SetDestinationAddress(vl.GetDestinationMac());
  
  // Determine payload size: use VL's max payload size (or derive from max frame size)
  // ARINC 664 Part 7: Payload can vary within VL's configured range
  uint32_t maxPayload = vl.GetMaxPayloadSize();
  
  // Use max payload size for this VL (typical case: use maximum bandwidth)
  uint32_t targetPayloadSize = maxPayload;

  // Create payload data
  std::vector<uint8_t> payloadData(targetPayloadSize, 0);
  std::string dataStr = "AFDX_VL" + std::to_string(vlId) + 
                        "_SEQ" + std::to_string((uint32_t)seqNum) +
                        "_ES" + std::to_string(m_nodeId) +
                        "_DATA";

  // Copy data string to payload (rest will be zero-padded)
  size_t copySize = std::min(dataStr.length(), (size_t)targetPayloadSize);
  memcpy(payloadData.data(), dataStr.c_str(), copySize);
  
  // Use VL range validation
  frame.SetPayloadWithVlRange(vl, payloadData.data(), targetPayloadSize);
  
  // Create packet
  Ptr<Packet> packet = Create<Packet>();
  packet->AddHeader(frame);
  
  uint32_t packetSize = packet->GetSize();
  
  // Transmit on both networks (redundancy)
  if (m_deviceA)
  {
    TransmitOnNetwork(packet->Copy(), m_deviceA, vl.GetDestinationMac());
    LogTxEvent(vlId, seqNum, "NetworkA", packetSize);
  }
  
  if (m_deviceB)
  {
    TransmitOnNetwork(packet->Copy(), m_deviceB, vl.GetDestinationMac());
    LogTxEvent(vlId, seqNum, "NetworkB", packetSize);
  }
  
  m_framesSent++;
  
  // Increment sequence number (wraps at 256)
  m_sequenceNumbers[vlId] = (seqNum + 1) % 256;
  
  NS_LOG_INFO("ES" << m_nodeId << " sent VL" << vlId << " Seq=" << (uint32_t)seqNum);
  
  // Schedule next transmission (BAG)
  ScheduleNextTransmission(vlId);
}

void
AfdxEndSystem::TransmitOnNetwork(Ptr<Packet> packet, Ptr<NetDevice> device, Mac48Address dst)
{
  // AFDX EtherType = 0x88B5
  uint16_t protocol = 0x88B5;
  
  device->Send(packet, dst, protocol);
}

void
AfdxEndSystem::ScheduleNextTransmission(uint16_t vlId)
{
  auto it = m_transmitVLs.find(vlId);
  if (it == m_transmitVLs.end())
  {
    return;
  }
  
  Time bag = it->second.GetBag();
  
  EventId event = Simulator::Schedule(bag, 
                                      &AfdxEndSystem::SendFrameInternal, 
                                      this, vlId);
  m_transmissionEvents[vlId] = event;
}

bool
AfdxEndSystem::ReceiveFromNetworkA(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                   uint16_t protocol, const Address& from)
{
  NS_LOG_FUNCTION(this << protocol);
  
  // Check for AFDX EtherType
  if (protocol != 0x88B5)
  {
    return false;
  }
  
  ProcessReceivedFrame(packet, "NetworkA");
  return true;
}

bool
AfdxEndSystem::ReceiveFromNetworkB(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                   uint16_t protocol, const Address& from)
{
  NS_LOG_FUNCTION(this << protocol);
  
  // Check for AFDX EtherType
  if (protocol != 0x88B5)
  {
    return false;
  }
  
  ProcessReceivedFrame(packet, "NetworkB");
  return true;
}

void
AfdxEndSystem::ProcessReceivedFrame(Ptr<const Packet> packet, const std::string& networkId)
{
  NS_LOG_FUNCTION(this << networkId);
  
  // Extract AFDX frame
  Ptr<Packet> copyPacket = packet->Copy();
  AfdxFrame frame;
  copyPacket->RemoveHeader(frame);
  
  uint16_t vlId = frame.GetVirtualLinkId();
  uint8_t seqNum = frame.GetSequenceNumber();
  uint32_t frameSize = packet->GetSize();
  
  NS_LOG_DEBUG("ES" << m_nodeId << " received VL" << vlId 
               << " Seq=" << (uint32_t)seqNum 
               << " from " << networkId);
  
  // ====================================================================
  // AFDX VALIDATION STEP 1: Frame Size Check
  // ====================================================================
  if (!ValidateFrame(frame, frameSize))
  {
    m_framesRejected++;
    LogRxEvent(vlId, seqNum, networkId, "REJECTED", "Invalid frame size");
    NS_LOG_WARN("ES" << m_nodeId << " rejected VL" << vlId << " - invalid frame size");
    return;
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 2: VL Subscription Check
  // ====================================================================
  if (!CheckVLSubscription(vlId))
  {
    m_framesRejected++;
    LogRxEvent(vlId, seqNum, networkId, "REJECTED", "Not subscribed");
    NS_LOG_DEBUG("ES" << m_nodeId << " rejected VL" << vlId << " - not subscribed");
    return;
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 3: Sequence Number Check
  // ====================================================================
  if (!CheckSequenceNumber(vlId, seqNum))
  {
    m_framesRejected++;
    LogRxEvent(vlId, seqNum, networkId, "REJECTED", "Invalid sequence number");
    NS_LOG_WARN("ES" << m_nodeId << " rejected VL" << vlId << " - sequence error");
    return;
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 4: First Valid Frame Wins (Redundancy Management)
  // ====================================================================
  if (!ApplyFirstValidFrameWins(vlId, networkId))
  {
    m_duplicatesDiscarded++;
    LogRxEvent(vlId, seqNum, networkId, "DUPLICATE", "First Valid Frame Wins");
    NS_LOG_DEBUG("ES" << m_nodeId << " discarded VL" << vlId 
                 << " duplicate from " << networkId);
    return;
  }
  
  // ====================================================================
  // FRAME ACCEPTED
  // ====================================================================
  m_framesReceived++;
  m_receptionState[vlId].lastValidSeqNum = seqNum;
  LogRxEvent(vlId, seqNum, networkId, "ACCEPTED", "Valid frame");
  
  NS_LOG_INFO("ES" << m_nodeId << " accepted VL" << vlId 
              << " Seq=" << (uint32_t)seqNum 
              << " from " << networkId);
}

bool
AfdxEndSystem::ValidateFrame(const AfdxFrame& frame, uint32_t frameSize)
{
  // Check frame size bounds (min 64, max 1518 bytes for Ethernet)
  if (frameSize < 64 || frameSize > 1518)
  {
    return false;
  }
  
  // Check VL ID is valid (non-zero)
  if (frame.GetVirtualLinkId() == 0)
  {
    return false;
  }

  // If we have a configured VL for this VL ID, validate payload size is within range
  uint16_t vlId = frame.GetVirtualLinkId();
  auto it = m_transmitVLs.find(vlId);
  if (it != m_transmitVLs.end())
  {
    const AfdxVirtualLink& vl = it->second;
    uint32_t minPayload = vl.GetMinPayloadSize();
    uint32_t maxPayload = vl.GetMaxPayloadSize();
    uint32_t payloadSize = frame.GetPayloadSize();
    
    if (payloadSize < minPayload || payloadSize > maxPayload)
    {
      NS_LOG_WARN("ES" << m_nodeId << " rejected VL" << vlId << " payload size " 
                  << payloadSize << " not in VL range [" << minPayload << "," << maxPayload << "]");
      return false;
    }
  }
  else
  {
    // If no VL config, allow ARINC 664 Part 7 global payload range 1..1471
    uint32_t payloadSize = frame.GetPayloadSize();
    if (payloadSize < 1 || payloadSize > 1471)
    {
      NS_LOG_WARN("ES" << m_nodeId << " rejected VL" << vlId << " payload " 
                  << payloadSize << " out of AFDX range [1,1471]");
      return false;
    }
  }

  return true;
}

bool
AfdxEndSystem::CheckVLSubscription(uint16_t vlId)
{
  // Check if this ES is subscribed to receive this VL
  for (uint16_t subscribedVlId : m_receiveVLs)
  {
    if (subscribedVlId == vlId)
    {
      return true;
    }
  }
  return false;
}

bool
AfdxEndSystem::CheckSequenceNumber(uint16_t vlId, uint8_t seqNum)
{
  auto it = m_receptionState.find(vlId);
  if (it == m_receptionState.end())
  {
    return true;  // First frame, accept any sequence number
  }
  
  uint8_t lastSeqNum = it->second.lastValidSeqNum;
  
  // First frame for this VL
  if (lastSeqNum == 255 && !it->second.frameReceived)
  {
    return true;
  }
  
  // Expected next sequence number (wraps at 256)
  uint8_t expectedSeqNum = (lastSeqNum + 1) % 256;
  
  // Allow the expected sequence number
  // In real systems, might allow small gaps for skipped frames
  if (seqNum == expectedSeqNum)
  {
    return true;
  }
  
  // Sequence number error
  NS_LOG_WARN("ES" << m_nodeId << " VL" << vlId 
              << " sequence error: expected " << (uint32_t)expectedSeqNum
              << " got " << (uint32_t)seqNum);
  
  // Update to new sequence number (recovery)
  return true;  // Still accept but log the error
}

bool
AfdxEndSystem::ApplyFirstValidFrameWins(uint16_t vlId, const std::string& networkId)
{
  auto it = m_receptionState.find(vlId);
  if (it == m_receptionState.end())
  {
    return true;  // Should not happen, but accept
  }
  
  FrameReceptionState& state = it->second;
  
  // First frame with this sequence number?
  if (!state.frameReceived || state.acceptedNetwork.empty())
  {
    // Accept and mark which network it came from
    state.acceptedNetwork = networkId;
    state.frameReceived = true;
    return true;
  }
  
  // Duplicate from redundant network - discard
  if (state.acceptedNetwork != networkId)
  {
    NS_LOG_DEBUG("ES" << m_nodeId << " VL" << vlId 
                 << " duplicate from " << networkId 
                 << " (already accepted from " << state.acceptedNetwork << ")");
    return false;
  }
  
  // Same network sending duplicate - should not happen in normal operation
  return false;
}

void
AfdxEndSystem::InitializeCsvFile()
{
  if (m_csvFilename.empty())
  {
    return;
  }
  
  // Check if file exists to determine if we need to write header
  bool fileExists = false;
  std::ifstream testFile(m_csvFilename);
  if (testFile.good())
  {
    fileExists = true;
  }
  testFile.close();
  
  // Open in append mode to allow multiple End Systems to write to same file
  m_csvFile.open(m_csvFilename, std::ios::app);
  if (!m_csvFile.is_open())
  {
    NS_LOG_ERROR("Failed to open CSV file: " << m_csvFilename);
    return;
  }
  
  // Write CSV header only if file is new - comprehensive 36-column format
  if (!fileExists)
  {
    m_csvFile << "Timestamp,Event,NodeID,NodeName,VL_ID,SequenceNum,Network,IsDuplicate,NetworkSelector,"
              << "EthSrcMAC,EthDstMAC,EthType,IPv4Version,IPv4HeaderLen,IPv4ToS,IPv4TotalLen,IPv4ID,"
              << "IPv4Flags,IPv4FragOffset,IPv4TTL,IPv4Protocol,IPv4Checksum,IPv4SrcIP,IPv4DstIP,"
              << "UDPSrcPort,UDPDstPort,UDPLength,UDPChecksum,AFDXNetworkID,AFDXEquipmentID,"
              << "AFDXInterfaceID,AFDXPartitionID,PacketSize,PayloadHex,RawFrameHex,Description\n";
    m_csvFile.flush();
  }
  
  NS_LOG_INFO("ES" << m_nodeId << " CSV logging initialized: " << m_csvFilename);
}

void
AfdxEndSystem::LogComprehensiveCsvEvent(const std::string& event, uint16_t vlId, uint8_t seqNum, 
                                       const std::string& network, bool isDuplicate,
                                       const std::string& srcMac, const std::string& dstMac,
                                       uint32_t packetSize, const std::string& description)
{
  if (!m_csvFile.is_open())
  {
    return;
  }
  
  double timestamp = Simulator::Now().GetSeconds();
  
  // Node Name mapping
  std::string nodeName;
  switch (m_nodeId)
  {
    case 1: nodeName = "ES1_Flight_Control"; break;
    case 2: nodeName = "ES2_Air_Data"; break;
    case 3: nodeName = "ES3_Navigation"; break;
    case 4: nodeName = "ES4_Cabin_Systems"; break;
    default: nodeName = "ES" + std::to_string(m_nodeId); break;
  }
  
  // Network conversion
  std::string networkId = (network == "NetworkA") ? "A" : "B";
  
  // Generate Ethernet MAC addresses if needed
  std::string ethSrcMAC = srcMac;
  std::string ethDstMAC = dstMac;
  
  if (ethSrcMAC == "N/A" && event == "TX")
  {
    // Generate source MAC based on network and node
    if (networkId == "A")
    {
      ethSrcMAC = "02:00:0a:01:0" + std::to_string(m_nodeId) + ":01";
    }
    else
    {
      ethSrcMAC = "02:00:0b:01:0" + std::to_string(m_nodeId) + ":01";
    }
  }
  
  if (ethDstMAC.find("03:00:00:00:") == std::string::npos)
  {
    // Generate AFDX multicast destination MAC
    std::ostringstream dstStream;
    dstStream << "03:00:00:00:" 
              << std::hex << std::setfill('0') << std::setw(2) << ((vlId >> 8) & 0xFF) 
              << ":" << std::hex << std::setfill('0') << std::setw(2) << (vlId & 0xFF);
    ethDstMAC = dstStream.str();
  }
  
  // Protocol fields
  uint16_t ethType = 2048;  // IP EtherType (0x0800)
  uint8_t ipv4Version = 4;
  uint8_t ipv4HeaderLen = 5;
  uint8_t ipv4ToS = 0;
  uint16_t ipv4TotalLen = 120;
  uint16_t ipv4ID = 0;
  uint16_t ipv4Flags = 0;
  uint16_t ipv4FragOffset = 0;
  uint8_t ipv4TTL = 64;
  uint8_t ipv4Protocol = 17;  // UDP
  uint16_t ipv4Checksum = 0;
  
  // IP addresses based on network
  std::string ipv4SrcIP = (networkId == "A") ? "10.1.1." + std::to_string(m_nodeId) : 
                                              "10.2.1." + std::to_string(m_nodeId);
  std::string ipv4DstIP = "224.1.0.1";  // Multicast
  
  // UDP fields
  uint16_t udpSrcPort = 5000 + vlId;
  uint16_t udpDstPort = 6000;
  uint16_t udpLength = 8;
  uint16_t udpChecksum = 0;
  
  // AFDX specific fields
  uint8_t afdxNetworkID = 1;
  uint8_t afdxEquipmentID = m_nodeId;
  uint8_t afdxInterfaceID = 1;
  uint8_t afdxPartitionID = 1;
  
  // Generate payload hex
  std::ostringstream payloadHex;
  payloadHex << std::setfill('0') << std::setw(2) << std::hex << ((vlId >> 8) & 0xFF) << " "
             << std::setfill('0') << std::setw(2) << std::hex << (vlId & 0xFF) << " "
             << std::setfill('0') << std::setw(2) << std::hex << (uint32_t)seqNum << " "
             << "00 00 00 00 00";
  
  // Generate raw frame hex (simplified header)
  std::ostringstream rawFrameHex;
  rawFrameHex << "03 00 00 00 " << std::setfill('0') << std::setw(2) << std::hex 
              << ((vlId >> 8) & 0xFF) << " " << std::setfill('0') << std::setw(2) 
              << (vlId & 0xFF) << " 02 00 " << networkId.substr(0,1) << "a 01 00 01 "
              << "08 00 45 00 00 80 00 00 40 00 40 11 ... [truncated]";
  
  // Generate description based on VL ID
  std::string fullDescription;
  if (vlId >= 1001 && vlId <= 1002)
  {
    fullDescription = "Flight Control " + description + " (Network " + networkId + ")";
  }
  else if (vlId == 2001)
  {
    fullDescription = "Air Data Computer " + description + " (Network " + networkId + ")";
  }
  else if (vlId == 3001)
  {
    fullDescription = "Navigation Display " + description + " (Network " + networkId + ")";
  }
  else if (vlId == 4001)
  {
    fullDescription = "Cabin Pressure " + description + " (Network " + networkId + ")";
  }
  else
  {
    fullDescription = "VL" + std::to_string(vlId) + " " + description + " (Network " + networkId + ")";
  }
  
  // Write comprehensive CSV line (36 columns)
  m_csvFile << std::fixed << std::setprecision(6) << timestamp << ","
            << event << ","
            << m_nodeId << ","
            << nodeName << ","
            << vlId << ","
            << (uint32_t)seqNum << ","
            << networkId << ","
            << (isDuplicate ? "true" : "false") << ","
            << "A_AND_B" << ","
            << ethSrcMAC << ","
            << ethDstMAC << ","
            << ethType << ","
            << (uint32_t)ipv4Version << ","
            << (uint32_t)ipv4HeaderLen << ","
            << (uint32_t)ipv4ToS << ","
            << ipv4TotalLen << ","
            << ipv4ID << ","
            << ipv4Flags << ","
            << ipv4FragOffset << ","
            << (uint32_t)ipv4TTL << ","
            << (uint32_t)ipv4Protocol << ","
            << ipv4Checksum << ","
            << ipv4SrcIP << ","
            << ipv4DstIP << ","
            << udpSrcPort << ","
            << udpDstPort << ","
            << udpLength << ","
            << udpChecksum << ","
            << (uint32_t)afdxNetworkID << ","
            << (uint32_t)afdxEquipmentID << ","
            << (uint32_t)afdxInterfaceID << ","
            << (uint32_t)afdxPartitionID << ","
            << packetSize << ","
            << payloadHex.str() << ","
            << rawFrameHex.str() << ","
            << fullDescription << "\n";
  m_csvFile.flush();
}

void
AfdxEndSystem::LogTxEvent(uint16_t vlId, uint8_t seqNum, const std::string& network, uint32_t size)
{
  if (!m_csvFile.is_open())
  {
    return;
  }
  
  auto it = m_transmitVLs.find(vlId);
  if (it == m_transmitVLs.end())
  {
    return;
  }
  
  const AfdxVirtualLink& vl = it->second;
  
  // Convert Mac48Address to string
  std::ostringstream srcMacStream, dstMacStream;
  srcMacStream << vl.GetSourceMac();
  dstMacStream << vl.GetDestinationMac();
  
  LogComprehensiveCsvEvent("TX", vlId, seqNum, network, false, srcMacStream.str(), 
                          dstMacStream.str(), size, "Frame transmission");
}

void
AfdxEndSystem::LogRxEvent(uint16_t vlId, uint8_t seqNum, const std::string& network,
                          const std::string& status, const std::string& reason)
{
  if (!m_csvFile.is_open())
  {
    return;
  }
  
  // For RX events, we don't have the original MAC addresses readily available,
  // so we'll generate them based on VL ID and network
  std::string srcMac = "N/A";
  std::ostringstream dstMacStream;
  dstMacStream << "03:00:00:00:" 
               << std::hex << std::setfill('0') << std::setw(2) << ((vlId >> 8) & 0xFF) 
               << ":" << std::hex << std::setfill('0') << std::setw(2) << (vlId & 0xFF);
  std::string dstMac = dstMacStream.str();
  
  bool isDuplicate = (status == "DUPLICATE");
  LogComprehensiveCsvEvent("RX", vlId, seqNum, network, isDuplicate, srcMac, dstMac, 146, reason);
}

void
AfdxEndSystem::SetName(const std::string& name)
{
  m_name = name;
}

void
AfdxEndSystem::SetNetworkInterfaces(Ptr<NetDevice> devA, Ptr<NetDevice> devB)
{
  SetNetworkADevice(devA);
  SetNetworkBDevice(devB);
}

void
AfdxEndSystem::AddPublication(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  m_publications.insert(vlId);
}

void
AfdxEndSystem::AddSubscription(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  m_subscriptions.insert(vlId);
}

bool
AfdxEndSystem::SendFrame(uint16_t vlId, const std::vector<uint8_t>& payload)
{
  NS_LOG_FUNCTION(this << vlId << payload.size());
  if (m_publications.find(vlId) == m_publications.end())
  {
    NS_LOG_WARN("VL " << vlId << " not in publication list");
    return false;
  }
  SendFrameInternal(vlId);
  return true;
}

void
AfdxEndSystem::SetFrameReceiveCallback(Callback<void, uint16_t, const std::vector<uint8_t>&, uint8_t> cb)
{
  m_frameReceiveCallback = cb;
}

} // namespace ns3
