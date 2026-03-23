/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Switch Implementation - ARINC 664 Part 7 Compliant
 */

#include "afdx-switch.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/uinteger.h"
#include "ns3/boolean.h"
#include "ns3/csma-net-device.h"
#include <iomanip>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("AfdxSwitch");
NS_OBJECT_ENSURE_REGISTERED(AfdxSwitch);

TypeId
AfdxSwitch::GetTypeId(void)
{
  static TypeId tid = TypeId("ns3::AfdxSwitch")
    .SetParent<Application>()
    .SetGroupName("Afdx")
    .AddConstructor<AfdxSwitch>()
    .AddAttribute("SwitchId",
                  "Unique identifier for this switch",
                  UintegerValue(0),
                  MakeUintegerAccessor(&AfdxSwitch::m_switchId),
                  MakeUintegerChecker<uint32_t>())
    .AddAttribute("StrictBagPolicing",
                  "Enable strict BAG policing (ARINC 664 Part 7)",
                  BooleanValue(true),
                  MakeBooleanAccessor(&AfdxSwitch::m_strictBagPolicing),
                  MakeBooleanChecker())
    .AddAttribute("FrameValidation",
                  "Enable frame validation (CRC, size checks)",
                  BooleanValue(true),
                  MakeBooleanAccessor(&AfdxSwitch::m_frameValidation),
                  MakeBooleanChecker());
  return tid;
}

AfdxSwitch::AfdxSwitch()
  : m_switchId(0),
    m_strictBagPolicing(true),
    m_frameValidation(true),
    m_maxFrameAge(MilliSeconds(100)),  // Default: 100ms max latency (ARINC 664 typical)
    m_queueProcessingInterval(MicroSeconds(10)),  // Process queues every 10μs
    m_framesReceived(0),
    m_framesForwarded(0),
    m_framesDropped(0),
    m_framesDroppedPolicing(0),
    m_framesDroppedInvalidVL(0),
    m_framesDroppedFrameError(0),
    m_framesDroppedMACError(0),
    m_framesDroppedBufferOverflow(0),
    m_framesDroppedAgedOut(0)
{
  NS_LOG_FUNCTION(this);
  
  // Initialize queue statistics
  m_queueDrops[AFDX_PRIORITY_CRITICAL] = 0;
  m_queueDrops[AFDX_PRIORITY_HIGH] = 0;
  m_queueDrops[AFDX_PRIORITY_MEDIUM] = 0;
  m_queueDrops[AFDX_PRIORITY_LOW] = 0;
  
  m_queueTx[AFDX_PRIORITY_CRITICAL] = 0;
  m_queueTx[AFDX_PRIORITY_HIGH] = 0;
  m_queueTx[AFDX_PRIORITY_MEDIUM] = 0;
  m_queueTx[AFDX_PRIORITY_LOW] = 0;

  // Phase 5: Initialize queue enqueued statistics
  m_queueEnqueued[AFDX_PRIORITY_CRITICAL] = 0;
  m_queueEnqueued[AFDX_PRIORITY_HIGH] = 0;
  m_queueEnqueued[AFDX_PRIORITY_MEDIUM] = 0;
  m_queueEnqueued[AFDX_PRIORITY_LOW] = 0;
  
  // Initialize discard reason counters
  m_discardReasons["CRC_Error"] = 0;
  m_discardReasons["Frame_Size_Error"] = 0;
  m_discardReasons["Invalid_VL"] = 0;
  m_discardReasons["BAG_Violation"] = 0;
  m_discardReasons["Buffer_Overflow"] = 0;
  m_discardReasons["Age_Timeout"] = 0;
  m_discardReasons["VL_Payload_Size_Error"] = 0;
}

AfdxSwitch::~AfdxSwitch()
{
  NS_LOG_FUNCTION(this);
}

void
AfdxSwitch::SetSwitchId(uint32_t switchId)
{
  m_switchId = switchId;
}

uint32_t
AfdxSwitch::GetSwitchId() const
{
  return m_switchId;
}

void
AfdxSwitch::AddSwitchPort(Ptr<NetDevice> port)
{
  NS_LOG_FUNCTION(this << port);
  m_ports.push_back(port);
  NS_LOG_INFO("Switch " << m_switchId << " added port " << (m_ports.size() - 1));
}

void
AfdxSwitch::ConfigureVirtualLink(const AfdxVirtualLink& vl, const std::vector<uint32_t>& outputPorts)
{
  NS_LOG_FUNCTION(this << vl.GetVlId());
  
  uint16_t vlId = vl.GetVlId();
  m_vlConfig[vlId] = vl;
  m_forwardingTable[vlId] = outputPorts;
  
  // Initialize VL statistics
  m_vlStats[vlId] = VLStats();
  
  // Initialize token bucket for this VL (ARINC 664 Part 7 §6.4.4)
  InitializeTokenBucket(vlId);
  
  NS_LOG_INFO("Switch " << m_switchId << " configured VL " << vlId 
              << " with " << outputPorts.size() << " output ports");
}

void
AfdxSwitch::SetStrictBagPolicing(bool enable)
{
  m_strictBagPolicing = enable;
  NS_LOG_INFO("Switch " << m_switchId << " BAG policing: " 
              << (enable ? "ENABLED" : "DISABLED"));
}

void
AfdxSwitch::SetFrameValidation(bool enable)
{
  m_frameValidation = enable;
  NS_LOG_INFO("Switch " << m_switchId << " frame validation: " 
              << (enable ? "ENABLED" : "DISABLED"));
}

void
AfdxSwitch::StartApplication(void)
{
  NS_LOG_FUNCTION(this);
  NS_LOG_INFO("Switch " << m_switchId << " starting with " << m_ports.size() << " ports");
  
  // Use ONLY promiscuous receive — registering both callbacks causes
  // each frame to be processed twice (double-counting bug).
  for (size_t i = 0; i < m_ports.size(); i++)
  {
    Ptr<CsmaNetDevice> csmaPort = DynamicCast<CsmaNetDevice>(m_ports[i]);
    if (csmaPort)
    {
      csmaPort->SetPromiscReceiveCallback(MakeCallback(&AfdxSwitch::PromiscReceiveFromDevice, this));
    }
  }
  
  // Start priority queue processing
  ScheduleQueueProcessing();
}

void
AfdxSwitch::StopApplication(void)
{
  NS_LOG_FUNCTION(this);
  
  // Cancel scheduled queue processing
  if (m_queueProcessingEvent.IsPending())
  {
    Simulator::Cancel(m_queueProcessingEvent);
  }
  
  NS_LOG_INFO("Switch " << m_switchId << " stopping. Statistics:");
  PrintStatistics(std::cout);
}

bool
AfdxSwitch::ReceiveFromDevice(Ptr<NetDevice> device, Ptr<const Packet> packet,
                               uint16_t protocol, const Address& from)
{
  NS_LOG_FUNCTION(this << device << packet->GetSize() << protocol);
  
  // Find which port this came from
  uint32_t inPort = 0;
  for (size_t i = 0; i < m_ports.size(); i++)
  {
    if (m_ports[i] == device)
    {
      inPort = i;
      break;
    }
  }
  
  m_framesReceived++;
  
  // Phase 5: Track per-port RX statistics
  m_portStats[inPort].rxFrames++;
  
  // Process the frame
  return ProcessFrame(packet, inPort);
}

bool
AfdxSwitch::PromiscReceiveFromDevice(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                     uint16_t protocol, const Address& from,
                                     const Address& to, NetDevice::PacketType packetType)
{
  NS_LOG_FUNCTION(this << device << packet->GetSize() << protocol);
  
  // Find which port this packet arrived on
  uint32_t inPort = 0;
  for (size_t i = 0; i < m_ports.size(); i++)
  {
    if (m_ports[i] == device)
    {
      inPort = i;
      break;
    }
  }
  
  m_framesReceived++;
  
  // Phase 5: Track per-port RX statistics
  m_portStats[inPort].rxFrames++;
  
  // Process the frame
  return ProcessFrame(packet, inPort);
}

bool
AfdxSwitch::ProcessFrame(Ptr<const Packet> packet, uint32_t inPort)
{
  NS_LOG_FUNCTION(this << packet->GetSize() << inPort);
  
  // Create a copy for processing
  Ptr<Packet> pktCopy = packet->Copy();
  
  // Deserialize AFDX frame
  AfdxFrame frame;
  pktCopy->RemoveHeader(frame);
  
  uint16_t vlId = frame.GetVirtualLinkId();
  
  NS_LOG_DEBUG("Switch " << m_switchId << " processing VL " << vlId 
               << " from port " << inPort);
  
  // Phase 5: Track timestamps for latency calculation
  Time now = Simulator::Now();
  if (m_vlStats[vlId].firstFrameTime.IsZero())
  {
    m_vlStats[vlId].firstFrameTime = now;
  }
  m_vlStats[vlId].lastFrameTime = now;
  
  // Step 1: Frame validation (CRC, size)
  if (m_frameValidation && !ValidateFrame(frame))
  {
    m_framesDropped++;
    m_framesDroppedFrameError++;
    if (m_vlStats.find(vlId) != m_vlStats.end())
    {
      m_vlStats[vlId].framesDropped++;
    }
    LogDrop(vlId, "Frame_Size_Error");
    return false;
  }
  
  // Step 2: VL authorization check
  if (!IsVLAuthorized(vlId))
  {
    m_framesDropped++;
    m_framesDroppedInvalidVL++;
    LogDrop(vlId, "Invalid_VL");
    return false;
  }
  
  // Step 2b: Source MAC validation (ARINC 664 Part 7 §6.4.3)
  {
    Mac48Address frameSrcMac = frame.GetSourceAddress();
    Mac48Address expectedSrcMac = m_vlConfig[vlId].GetSourceMac();
    if (frameSrcMac != expectedSrcMac)
    {
      m_framesDropped++;
      m_framesDroppedMACError++;
      if (m_vlStats.find(vlId) != m_vlStats.end())
      {
        m_vlStats[vlId].framesDropped++;
      }
      LogDrop(vlId, "MAC_Source_Mismatch");
      return false;
    }
  }
  
  // Step 3: BAG policing check
  if (m_strictBagPolicing && !CheckBagPolicing(vlId))
  {
    m_framesDropped++;
    m_framesDroppedPolicing++;
    m_vlStats[vlId].framesDropped++;
    m_vlStats[vlId].policingViolations++;
    LogDrop(vlId, "BAG_Violation");
    return false;
  }
  
  // Step 4: Token Bucket Policing (ARINC 664 Part 7 §6.4.4)
  uint32_t frameSize = packet->GetSize();
  if (!CheckTokenBucket(vlId, frameSize))
  {
    m_framesDropped++;
    m_framesDroppedPolicing++;
    m_vlStats[vlId].framesDropped++;
    m_vlStats[vlId].policingViolations++;
    LogDrop(vlId, "BAG_Violation");
    return false;
  }
  
  // Debit tokens for this frame
  DebitTokenBucket(vlId, frameSize);
  
  // Step 5: Get output ports from forwarding table
  std::vector<uint32_t> outputPorts = GetOutputPorts(vlId);
  
  if (outputPorts.empty())
  {
    m_framesDropped++;
    m_vlStats[vlId].framesDropped++;
    LogDrop(vlId, "No output ports configured");
    return false;
  }
  
  // Step 5: Forward frame to output ports
  ForwardFrame(packet->Copy(), outputPorts, inPort);
  
  m_framesForwarded++;
  m_vlStats[vlId].framesForwarded++;
  
  NS_LOG_DEBUG("Switch " << m_switchId << " forwarded VL " << vlId 
               << " to " << outputPorts.size() << " ports");
  
  return true;
}

bool
AfdxSwitch::ValidateFrame(const AfdxFrame& frame) const
{
  NS_LOG_FUNCTION(this);
  
  // ARINC 664 Part 7: Frame size validation
  // Valid Ethernet frame: 64 to 1518 bytes (including FCS)
  uint32_t frameSize = frame.GetSerializedSize();
  
  if (frameSize < 64 || frameSize > 1518)
  {
    NS_LOG_WARN("Switch " << m_switchId << " invalid frame size: " << frameSize);
    return false;
  }
  
  // Additional validations could include:
  // - CRC/FCS check (if available in packet metadata)
  // - Sequence number validity
  // - Payload size within VL bounds
  
  uint16_t vlId = frame.GetVirtualLinkId();
  if (m_vlConfig.find(vlId) != m_vlConfig.end())
  {
    const AfdxVirtualLink& vl = m_vlConfig.at(vlId);
    uint32_t payloadSize = frame.GetPayloadSize();
    
    if (payloadSize < vl.GetMinPayloadSize() || payloadSize > vl.GetMaxPayloadSize())
    {
      NS_LOG_WARN("Switch " << m_switchId << " VL " << vlId 
                  << " payload " << payloadSize << " out of range ["
                  << vl.GetMinPayloadSize() << ", " << vl.GetMaxPayloadSize() << "]");
      return false;
    }
  }
  
  return true;
}

bool
AfdxSwitch::IsVLAuthorized(uint16_t vlId) const
{
  return m_vlConfig.find(vlId) != m_vlConfig.end();
}

bool
AfdxSwitch::CheckBagPolicing(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  // Get VL configuration
  if (m_vlConfig.find(vlId) == m_vlConfig.end())
  {
    return false;  // VL not configured
  }
  
  const AfdxVirtualLink& vl = m_vlConfig[vlId];
  Time bag = vl.GetBag();
  Time now = Simulator::Now();
  
  // Check if this VL has been seen before
  if (m_lastFrameTime.find(vlId) == m_lastFrameTime.end())
  {
    // First frame for this VL - allow it
    m_lastFrameTime[vlId] = now;
    return true;
  }
  
  // Calculate time since last frame
  Time timeSinceLastFrame = now - m_lastFrameTime[vlId];
  
  // ARINC 664 Part 7: BAG policing
  // Frames arriving faster than BAG rate should be dropped
  // Allow small tolerance (1% of BAG) for jitter
  Time tolerance = MilliSeconds(bag.GetMilliSeconds() * 0.01);
  Time minGap = bag - tolerance;
  
  if (timeSinceLastFrame < minGap)
  {
    NS_LOG_WARN("Switch " << m_switchId << " VL " << vlId 
                << " BAG violation: gap=" << timeSinceLastFrame.GetMilliSeconds()
                << "ms, expected>=" << minGap.GetMilliSeconds() << "ms");
    return false;
  }
  
  // Update last frame time
  m_lastFrameTime[vlId] = now;
  return true;
}

void
AfdxSwitch::InitializeTokenBucket(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  if (m_vlConfig.find(vlId) == m_vlConfig.end())
  {
    NS_LOG_ERROR("Cannot initialize token bucket: VL " << vlId << " not configured");
    return;
  }
  
  const AfdxVirtualLink& vl = m_vlConfig[vlId];
  TokenBucket& bucket = m_tokenBuckets[vlId];
  
  // ARINC 664 Part 7 §6.4.4: Token Bucket Parameters
  // BAG (Bandwidth Allocation Gap) defines the transmission rate
  double bagSeconds = vl.GetBag().GetSeconds();
  uint32_t maxFrameSize = vl.GetMaxPayloadSize() + 20; // Payload + AFDX header overhead
  
  // Refill rate = max frame size / BAG (bytes per second)
  // This allows VL to send maxFrameSize bytes every BAG interval
  bucket.refillRate = maxFrameSize / bagSeconds;
  
  // Maximum credits = Lmax + Jmax (per ARINC 664 Part 7)
  // Lmax = maximum frame size
  // Jmax = jitter allowance (typically 1-2 frames worth)
  bucket.maxCredits = maxFrameSize * 2.0;  // Allow burst of 2 frames
  
  // Initialize with full credits
  bucket.credits = bucket.maxCredits;
  bucket.lastUpdate = Simulator::Now();
  bucket.consecutiveViolations = 0;
  
  NS_LOG_INFO("Switch " << m_switchId << " initialized token bucket for VL " << vlId
              << ": refillRate=" << bucket.refillRate << " bytes/s"
              << ", maxCredits=" << bucket.maxCredits << " bytes");
}

void
AfdxSwitch::RefillTokenBucket(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  auto it = m_tokenBuckets.find(vlId);
  if (it == m_tokenBuckets.end())
  {
    return;
  }
  
  TokenBucket& bucket = it->second;
  Time now = Simulator::Now();
  double elapsed = (now - bucket.lastUpdate).GetSeconds();
  
  if (elapsed > 0)
  {
    // Add credits based on elapsed time and refill rate
    double newCredits = bucket.credits + (bucket.refillRate * elapsed);
    
    // Cap at maximum credits (prevent unbounded accumulation)
    bucket.credits = std::min(newCredits, bucket.maxCredits);
    bucket.lastUpdate = now;
    
    NS_LOG_DEBUG("Switch " << m_switchId << " VL " << vlId 
                 << " refilled: credits=" << bucket.credits 
                 << " (elapsed=" << elapsed << "s)");
  }
}

bool
AfdxSwitch::CheckTokenBucket(uint16_t vlId, uint32_t frameSize)
{
  NS_LOG_FUNCTION(this << vlId << frameSize);
  
  // First, refill the bucket based on elapsed time
  RefillTokenBucket(vlId);
  
  auto it = m_tokenBuckets.find(vlId);
  if (it == m_tokenBuckets.end())
  {
    NS_LOG_WARN("Token bucket not found for VL " << vlId);
    return true;  // Allow if not configured (fail-open)
  }
  
  TokenBucket& bucket = it->second;
  
  // Check if we have enough credits for this frame
  if (bucket.credits >= frameSize)
  {
    // Reset consecutive violations counter on success
    bucket.consecutiveViolations = 0;
    return true;
  }
  else
  {
    // Policing violation
    bucket.consecutiveViolations++;
    
    NS_LOG_WARN("Switch " << m_switchId << " VL " << vlId 
                << " token bucket violation: credits=" << bucket.credits
                << ", required=" << frameSize
                << ", consecutive violations=" << bucket.consecutiveViolations);
    
    // ARINC 664 Part 7: Babbling Idiot Protection
    // If sustained overage (e.g., 10+ consecutive violations), it's a babbling source
    if (bucket.consecutiveViolations >= 10)
    {
      NS_LOG_ERROR("Switch " << m_switchId << " VL " << vlId 
                   << " BABBLING IDIOT DETECTED: " << bucket.consecutiveViolations 
                   << " consecutive violations");
    }
    
    return false;
  }
}

void
AfdxSwitch::DebitTokenBucket(uint16_t vlId, uint32_t frameSize)
{
  NS_LOG_FUNCTION(this << vlId << frameSize);
  
  auto it = m_tokenBuckets.find(vlId);
  if (it == m_tokenBuckets.end())
  {
    return;
  }
  
  TokenBucket& bucket = it->second;
  
  // Debit the credits
  bucket.credits -= frameSize;
  
  NS_LOG_DEBUG("Switch " << m_switchId << " VL " << vlId 
               << " debited " << frameSize << " bytes, credits=" << bucket.credits);
}

double
AfdxSwitch::GetTokenBucketCredits(uint16_t vlId) const
{
  auto it = m_tokenBuckets.find(vlId);
  if (it != m_tokenBuckets.end())
  {
    return it->second.credits;
  }
  return -1.0;  // VL not found
}

std::vector<uint32_t>
AfdxSwitch::GetOutputPorts(uint16_t vlId) const
{
  auto it = m_forwardingTable.find(vlId);
  if (it != m_forwardingTable.end())
  {
    return it->second;
  }
  return std::vector<uint32_t>();
}

void
AfdxSwitch::ForwardFrame(Ptr<Packet> packet, const std::vector<uint32_t>& ports, uint32_t inPort)
{
  NS_LOG_FUNCTION(this << packet->GetSize() << ports.size() << inPort);
  
  // Extract VL ID to determine priority
  Ptr<Packet> pktCopy = packet->Copy();
  AfdxFrame frame;
  pktCopy->RemoveHeader(frame);
  uint16_t vlId = frame.GetVirtualLinkId();
  
  // Get VL configuration to determine priority
  AfdxPriority priority = AFDX_PRIORITY_MEDIUM;  // Default
  auto vlIt = m_vlConfig.find(vlId);
  if (vlIt != m_vlConfig.end())
  {
    priority = vlIt->second.GetPriority();
  }
  
  for (uint32_t port : ports)
  {
    // Don't forward back to input port (split horizon)
    if (port == inPort)
    {
      continue;
    }
    
    if (port >= m_ports.size())
    {
      NS_LOG_ERROR("Switch " << m_switchId << " invalid output port: " << port);
      continue;
    }
    
    // Enqueue frame in priority queue (ARINC 664 Part 7 QoS)
    Ptr<Packet> frameCopy = packet->Copy();
    if (EnqueueFrame(frameCopy, port, priority))
    {
      NS_LOG_DEBUG("Switch " << m_switchId << " enqueued VL " << vlId 
                   << " to port " << port << " priority " << (int)priority);
    }
    else
    {
      NS_LOG_WARN("Switch " << m_switchId << " queue full, dropped VL " << vlId 
                  << " priority " << (int)priority);
    }
  }
}

void
AfdxSwitch::LogDrop(uint16_t vlId, const std::string& reason)
{
  NS_LOG_WARN("Switch " << m_switchId << " dropped VL " << vlId << ": " << reason);
  
  // Track detailed discard reasons (ARINC 664 Part 7 §3.5.11)
  if (m_discardReasons.find(reason) != m_discardReasons.end())
  {
    m_discardReasons[reason]++;
  }
  else
  {
    // Unknown reason, track as "Other"
    m_discardReasons["Other"]++;
  }
}

uint64_t
AfdxSwitch::GetFramesReceived() const
{
  return m_framesReceived;
}

uint64_t
AfdxSwitch::GetFramesForwarded() const
{
  return m_framesForwarded;
}

uint64_t
AfdxSwitch::GetFramesDropped() const
{
  return m_framesDropped;
}

uint64_t
AfdxSwitch::GetFramesDroppedPolicing() const
{
  return m_framesDroppedPolicing;
}

uint64_t
AfdxSwitch::GetFramesDroppedInvalidVL() const
{
  return m_framesDroppedInvalidVL;
}

uint64_t
AfdxSwitch::GetFramesDroppedFrameError() const
{
  return m_framesDroppedFrameError;
}

uint64_t
AfdxSwitch::GetFramesDroppedBufferOverflow() const
{
  return m_framesDroppedBufferOverflow;
}

uint64_t
AfdxSwitch::GetFramesDroppedAgedOut() const
{
  return m_framesDroppedAgedOut;
}

void
AfdxSwitch::GetDiscardReasons(std::map<std::string, uint64_t>& reasons) const
{
  reasons = m_discardReasons;
}

void
AfdxSwitch::SetMaxFrameAge(Time maxAge)
{
  m_maxFrameAge = maxAge;
  NS_LOG_INFO("Switch " << m_switchId << " max frame age set to " 
              << maxAge.GetMicroSeconds() << " μs");
}

Time
AfdxSwitch::GetMaxFrameAge() const
{
  return m_maxFrameAge;
}

bool
AfdxSwitch::GetVLStatistics(uint16_t vlId, uint64_t& forwarded, uint64_t& dropped,
                            uint64_t& policingViolations) const
{
  auto it = m_vlStats.find(vlId);
  if (it == m_vlStats.end())
  {
    return false;
  }
  
  forwarded = it->second.framesForwarded;
  dropped = it->second.framesDropped;
  policingViolations = it->second.policingViolations;
  return true;
}

void
AfdxSwitch::PrintStatistics(std::ostream& os) const
{
  os << "\n=== Switch " << m_switchId << " Statistics ===\n";
  os << "Global Counters:\n";
  os << "  Frames Received:        " << m_framesReceived << "\n";
  os << "  Frames Forwarded:       " << m_framesForwarded << "\n";
  os << "  Frames Dropped:         " << m_framesDropped << "\n";
  os << "    - Frame Errors:       " << m_framesDroppedFrameError << "\n";
  os << "    - MAC Errors:         " << m_framesDroppedMACError << "\n";
  os << "    - Invalid VL:         " << m_framesDroppedInvalidVL << "\n";
  os << "    - Policing:           " << m_framesDroppedPolicing << "\n";
  os << "    - Buffer Overflow:    " << m_framesDroppedBufferOverflow << "\n";
  os << "    - Aged Out:           " << m_framesDroppedAgedOut << "\n";
  
  os << "\nDetailed Discard Reasons:\n";
  for (const auto& pair : m_discardReasons)
  {
    if (pair.second > 0)
    {
      os << "  " << pair.first << ": " << pair.second << "\n";
    }
  }
  
  os << "\nPer-VL Statistics:\n";
  os << "  VL ID | Forwarded | Dropped | Policing Violations\n";
  os << "  ------|-----------|---------|-------------------\n";
  
  for (const auto& pair : m_vlStats)
  {
    os << "  " << std::setw(5) << pair.first 
       << " | " << std::setw(9) << pair.second.framesForwarded
       << " | " << std::setw(7) << pair.second.framesDropped
       << " | " << std::setw(19) << pair.second.policingViolations << "\n";
  }
  os << "======================================\n";
}

bool
AfdxSwitch::EnqueueFrame(Ptr<Packet> packet, uint32_t port, AfdxPriority priority)
{
  NS_LOG_FUNCTION(this << packet->GetSize() << port << (int)priority);
  
  // Get the queue for this port and priority
  auto& queue = m_priorityQueues[port][priority];
  
  // Check if queue is full (head-drop policy per ARINC 664 Part 7)
  if (queue.size() >= MAX_QUEUE_SIZE)
  {
    // Extract VL ID for logging (need to parse packet)
    Ptr<Packet> pktCopy = packet->Copy();
    AfdxFrame frame;
    pktCopy->RemoveHeader(frame);
    uint16_t vlId = frame.GetVirtualLinkId();
    
    m_queueDrops[priority]++;
    m_framesDropped++;
    m_framesDroppedBufferOverflow++;
    m_vlStats[vlId].framesDropped++;
    LogDrop(vlId, "Buffer_Overflow");
    
    NS_LOG_WARN("Switch " << m_switchId << " queue full for port " << port 
                << " priority " << (int)priority << " VL " << vlId << " (head-drop)");
    return false;
  }
  
  // Extract VL ID for tracking
  Ptr<Packet> pktCopy = packet->Copy();
  AfdxFrame frame;
  pktCopy->RemoveHeader(frame);
  uint16_t vlId = frame.GetVirtualLinkId();
  
  // Get current time for age tracking (ARINC 664 Part 7 §3.3.10-12)
  Time now = Simulator::Now();
  
  // Enqueue the frame with timestamp
  queue.push(QueuedFrame(packet, vlId, now));
  
  // Phase 5: Track enqueued statistics
  m_queueEnqueued[priority]++;
  
  NS_LOG_DEBUG("Switch " << m_switchId << " enqueued VL " << vlId 
               << " to port " << port << " priority " << (int)priority 
               << " (queue size=" << queue.size() << ")");
  
  return true;
}

void
AfdxSwitch::ProcessQueues()
{
  NS_LOG_FUNCTION(this);
  
  // Process each output port
  for (uint32_t port = 0; port < m_ports.size(); port++)
  {
    // Strict priority scheduling: Check queues in priority order
    // CRITICAL → HIGH → MEDIUM → LOW
    // Transmit from highest priority non-empty queue
    
    bool transmitted = false;
    
    for (int p = AFDX_PRIORITY_CRITICAL; p >= AFDX_PRIORITY_LOW && !transmitted; p--)
    {
      AfdxPriority priority = static_cast<AfdxPriority>(p);
      auto& queue = m_priorityQueues[port][priority];
      
      if (!queue.empty())
      {
        // Get frame from queue
        QueuedFrame qf = queue.front();
        
        // Check frame age (ARINC 664 Part 7 §3.3.10-12)
        Time now = Simulator::Now();
        Time frameAge = now - qf.timestamp;
        
        if (frameAge > m_maxFrameAge)
        {
          // Frame too old, discard (aged out)
          queue.pop();
          m_framesDropped++;
          m_framesDroppedAgedOut++;
          m_vlStats[qf.vlId].framesDropped++;
          LogDrop(qf.vlId, "Age_Timeout");
          
          NS_LOG_WARN("Switch " << m_switchId << " aged frame VL " << qf.vlId 
                      << " age=" << frameAge.GetMicroSeconds() << "μs"
                      << " max=" << m_maxFrameAge.GetMicroSeconds() << "μs");
          
          // Try next frame in queue (don't mark transmitted)
          continue;
        }
        
        // Frame is valid, remove from queue
        queue.pop();
        
        // Transmit the frame
        m_ports[port]->Send(qf.packet, m_ports[port]->GetBroadcast(), 0x88B5);
        
        m_queueTx[priority]++;
        transmitted = true;
        
        // Phase 5: Track per-port TX statistics
        m_portStats[port].txFrames++;
        
        NS_LOG_DEBUG("Switch " << m_switchId << " transmitted VL " << qf.vlId 
                     << " from port " << port << " priority " << (int)priority
                     << " age=" << frameAge.GetMicroSeconds() << "μs"
                     << " (queue remaining=" << queue.size() << ")");
      }
    }
  }
  
  // Schedule next queue processing
  ScheduleQueueProcessing();
}

void
AfdxSwitch::ScheduleQueueProcessing()
{
  NS_LOG_FUNCTION(this);
  
  m_queueProcessingEvent = Simulator::Schedule(m_queueProcessingInterval, 
                                               &AfdxSwitch::ProcessQueues, this);
}

// =====================================================================
// Phase 5: Enhanced Statistics & MIB Implementation
// =====================================================================

bool
AfdxSwitch::GetPortStatistics(uint32_t port, uint64_t& rxFrames, uint64_t& txFrames,
                               uint64_t& rxErrors, uint64_t& txErrors, uint32_t& queueDepth) const
{
  if (port >= m_ports.size())
  {
    return false;
  }
  
  auto it = m_portStats.find(port);
  if (it != m_portStats.end())
  {
    rxFrames = it->second.rxFrames;
    txFrames = it->second.txFrames;
    rxErrors = it->second.rxErrors;
    txErrors = it->second.txErrors;
  }
  else
  {
    rxFrames = txFrames = rxErrors = txErrors = 0;
  }
  
  // Calculate current queue depth
  queueDepth = 0;
  auto queueIt = m_priorityQueues.find(port);
  if (queueIt != m_priorityQueues.end())
  {
    for (const auto& prioQueue : queueIt->second)
    {
      queueDepth += prioQueue.second.size();
    }
  }
  
  return true;
}

bool
AfdxSwitch::GetQueueStatistics(AfdxPriority priority, uint64_t& enqueued,
                                uint64_t& transmitted, uint64_t& dropped) const
{
  auto enqIt = m_queueEnqueued.find(priority);
  auto txIt = m_queueTx.find(priority);
  auto dropIt = m_queueDrops.find(priority);
  
  enqueued = (enqIt != m_queueEnqueued.end()) ? enqIt->second : 0;
  transmitted = (txIt != m_queueTx.end()) ? txIt->second : 0;
  dropped = (dropIt != m_queueDrops.end()) ? dropIt->second : 0;
  
  return true;
}

double
AfdxSwitch::GetAverageLatency(uint16_t vlId) const
{
  auto it = m_vlStats.find(vlId);
  if (it == m_vlStats.end() || it->second.latencySamples == 0)
  {
    return -1.0;  // No data
  }
  
  return it->second.totalLatency / it->second.latencySamples;
}

void
AfdxSwitch::ResetStatistics()
{
  NS_LOG_FUNCTION(this);
  
  // Reset global statistics
  m_framesReceived = 0;
  m_framesForwarded = 0;
  m_framesDropped = 0;
  m_framesDroppedPolicing = 0;
  m_framesDroppedInvalidVL = 0;
  m_framesDroppedFrameError = 0;
  m_framesDroppedMACError = 0;
  m_framesDroppedBufferOverflow = 0;
  m_framesDroppedAgedOut = 0;
  
  // Reset discard reasons
  for (auto& pair : m_discardReasons)
  {
    pair.second = 0;
  }
  
  // Reset per-VL statistics
  m_vlStats.clear();
  
  // Reset per-port statistics
  m_portStats.clear();
  
  // Reset queue statistics
  for (auto& pair : m_queueDrops)
  {
    pair.second = 0;
  }
  for (auto& pair : m_queueTx)
  {
    pair.second = 0;
  }
  for (auto& pair : m_queueEnqueued)
  {
    pair.second = 0;
  }
  
  NS_LOG_INFO("Switch " << m_switchId << " statistics reset");
}

void
AfdxSwitch::ExportMIB(std::ostream& os) const
{
  NS_LOG_FUNCTION(this);
  
  // MIB-style export (SNMP-like OID structure)
  os << "# AFDX Switch MIB Export (SNMP-like format)\n";
  os << "# Switch ID: " << m_switchId << "\n";
  os << "# Timestamp: " << Simulator::Now().GetSeconds() << "s\n\n";
  
  // System group (OID: 1.3.6.1.4.1.AFDX.1)
  os << "# System Group\n";
  os << "afdxSwitchId.0 = " << m_switchId << "\n";
  os << "afdxSwitchUptime.0 = " << Simulator::Now().GetSeconds() << "\n";
  os << "afdxSwitchPorts.0 = " << m_ports.size() << "\n\n";
  
  // Global statistics (OID: 1.3.6.1.4.1.AFDX.2)
  os << "# Global Statistics\n";
  os << "afdxFramesReceived.0 = " << m_framesReceived << "\n";
  os << "afdxFramesForwarded.0 = " << m_framesForwarded << "\n";
  os << "afdxFramesDropped.0 = " << m_framesDropped << "\n";
  os << "afdxFramesDroppedPolicing.0 = " << m_framesDroppedPolicing << "\n";
  os << "afdxFramesDroppedInvalidVL.0 = " << m_framesDroppedInvalidVL << "\n";
  os << "afdxFramesDroppedFrameError.0 = " << m_framesDroppedFrameError << "\n";
  os << "afdxFramesDroppedMACError.0 = " << m_framesDroppedMACError << "\n\n";
  
  // Per-VL statistics (OID: 1.3.6.1.4.1.AFDX.3.VL_ID)
  os << "# Per-VL Statistics\n";
  for (const auto& pair : m_vlStats)
  {
    uint16_t vlId = pair.first;
    const VLStats& stats = pair.second;
    
    os << "afdxVLForwarded." << vlId << " = " << stats.framesForwarded << "\n";
    os << "afdxVLDropped." << vlId << " = " << stats.framesDropped << "\n";
    os << "afdxVLPolicingViolations." << vlId << " = " << stats.policingViolations << "\n";
    os << "afdxVLSequenceErrors." << vlId << " = " << stats.sequenceErrors << "\n";
    
    if (stats.latencySamples > 0)
    {
      double avgLatency = stats.totalLatency / stats.latencySamples;
      os << "afdxVLAvgLatency." << vlId << " = " << avgLatency << " us\n";
    }
    
    if (!stats.firstFrameTime.IsZero() && !stats.lastFrameTime.IsZero())
    {
      double duration = (stats.lastFrameTime - stats.firstFrameTime).GetSeconds();
      if (duration > 0)
      {
        double throughput = stats.framesForwarded / duration;
        os << "afdxVLThroughput." << vlId << " = " << throughput << " fps\n";
      }
    }
  }
  os << "\n";
  
  // Per-port statistics (OID: 1.3.6.1.4.1.AFDX.4.PORT_ID)
  os << "# Per-Port Statistics\n";
  for (const auto& pair : m_portStats)
  {
    uint32_t port = pair.first;
    const PortStats& stats = pair.second;
    
    os << "afdxPortRxFrames." << port << " = " << stats.rxFrames << "\n";
    os << "afdxPortTxFrames." << port << " = " << stats.txFrames << "\n";
    os << "afdxPortRxErrors." << port << " = " << stats.rxErrors << "\n";
    os << "afdxPortTxErrors." << port << " = " << stats.txErrors << "\n";
    
    // Current queue depth
    uint32_t queueDepth = 0;
    auto queueIt = m_priorityQueues.find(port);
    if (queueIt != m_priorityQueues.end())
    {
      for (const auto& prioQueue : queueIt->second)
      {
        queueDepth += prioQueue.second.size();
      }
    }
    os << "afdxPortQueueDepth." << port << " = " << queueDepth << "\n";
  }
  os << "\n";
  
  // Queue statistics by priority (OID: 1.3.6.1.4.1.AFDX.5.PRIORITY)
  os << "# Queue Statistics by Priority\n";
  const char* priorityNames[] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"};
  for (int p = 0; p <= 3; p++)
  {
    AfdxPriority priority = static_cast<AfdxPriority>(p);
    
    auto enqIt = m_queueEnqueued.find(priority);
    auto txIt = m_queueTx.find(priority);
    auto dropIt = m_queueDrops.find(priority);
    
    os << "afdxQueueEnqueued." << priorityNames[p] << " = " 
       << (enqIt != m_queueEnqueued.end() ? enqIt->second : 0) << "\n";
    os << "afdxQueueTransmitted." << priorityNames[p] << " = " 
       << (txIt != m_queueTx.end() ? txIt->second : 0) << "\n";
    os << "afdxQueueDropped." << priorityNames[p] << " = " 
       << (dropIt != m_queueDrops.end() ? dropIt->second : 0) << "\n";
  }
  os << "\n";
  
  // Token bucket statistics (OID: 1.3.6.1.4.1.AFDX.6.VL_ID)
  os << "# Token Bucket Statistics\n";
  for (const auto& pair : m_tokenBuckets)
  {
    uint16_t vlId = pair.first;
    const TokenBucket& bucket = pair.second;
    
    os << "afdxTokenBucketCredits." << vlId << " = " << bucket.credits << " bytes\n";
    os << "afdxTokenBucketMaxCredits." << vlId << " = " << bucket.maxCredits << " bytes\n";
    os << "afdxTokenBucketRefillRate." << vlId << " = " << bucket.refillRate << " bytes/s\n";
    os << "afdxTokenBucketViolations." << vlId << " = " << bucket.consecutiveViolations << "\n";
  }
  
  os << "\n# End of MIB Export\n";
}

} // namespace ns3
