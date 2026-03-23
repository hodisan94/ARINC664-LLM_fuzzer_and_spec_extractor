/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Traffic Generator Application Implementation
 */

#include "afdx-traffic-generator.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/packet.h"
#include "ns3/random-variable-stream.h"
#include <iomanip>
#include <sstream>
#include <sys/stat.h>
#include <fstream>
#include <ctime>

// External mutation config from afdx-demo.cc (for AI fuzzer integration - EXTREME MODE)
// Defined outside namespace since afdx-demo.cc defines it globally
struct MutationConfig
{
    uint16_t targetVL;
    double probability;
    int payloadDeltaBytes;
    int timingJitterMs;
    std::string macMutation;
    bool isExtremeTest;
    bool isActive;
    int payloadAppliedBytes;
    int jitterAppliedMs;
    int payloadClampCount;
    int txProbDrops;
    int macSpoofCount;
    int sequenceNumberOverride;
    int seqMutationCount;
    std::string destMacMutation;
    int destMacMutationCount;
    
    MutationConfig() : 
        targetVL(0), probability(0.0), payloadDeltaBytes(0), 
        timingJitterMs(0), macMutation("none"), isExtremeTest(false), isActive(false),
        payloadAppliedBytes(0), jitterAppliedMs(0), payloadClampCount(0), 
        txProbDrops(0), macSpoofCount(0),
        sequenceNumberOverride(0), seqMutationCount(0),
        destMacMutation("none"), destMacMutationCount(0) {}
};
extern MutationConfig g_mutationConfig;

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("AfdxTrafficGenerator");
NS_OBJECT_ENSURE_REGISTERED(AfdxTrafficGenerator);

TypeId
AfdxTrafficGenerator::GetTypeId()
{
  static TypeId tid = TypeId("ns3::AfdxTrafficGenerator")
    .SetParent<Application>()
    .SetGroupName("Afdx")
    .AddConstructor<AfdxTrafficGenerator>();
  return tid;
}

AfdxTrafficGenerator::AfdxTrafficGenerator()
  : m_device(nullptr),
    m_deviceNetworkA(nullptr),
    m_deviceNetworkB(nullptr),
    m_dualNetworkMode(false),
    m_csvEnabled(false),
    m_framesSent(0),
    m_framesReceived(0),
    m_framesRejected(0),
    m_duplicatesDiscarded(0)
{
  NS_LOG_FUNCTION(this);
}

AfdxTrafficGenerator::~AfdxTrafficGenerator()
{
  NS_LOG_FUNCTION(this);
  
  if (m_csvFile.is_open())
  {
    m_csvFile.close();
  }
}

void
AfdxTrafficGenerator::SetNetDevice(Ptr<NetDevice> device)
{
  NS_LOG_FUNCTION(this << device);
  m_device = device;
  m_dualNetworkMode = false;
}

void
AfdxTrafficGenerator::SetDualNetworkDevices(Ptr<NetDevice> networkA, Ptr<NetDevice> networkB)
{
  NS_LOG_FUNCTION(this << networkA << networkB);
  m_deviceNetworkA = networkA;
  m_deviceNetworkB = networkB;
  m_dualNetworkMode = true;
  
  NS_LOG_INFO("AFDX Traffic Generator configured for DUAL NETWORK redundancy");
  NS_LOG_INFO("  Network A: " << networkA);
  NS_LOG_INFO("  Network B: " << networkB);
}

void
AfdxTrafficGenerator::AddVirtualLink(const AfdxVirtualLink& vl, uint32_t payloadSize)
{
  NS_LOG_FUNCTION(this << vl.GetVlId() << payloadSize);
  
  if (payloadSize < vl.GetMinPayloadSize() || payloadSize > vl.GetMaxPayloadSize())
  {
    if (g_mutationConfig.isActive && g_mutationConfig.isExtremeTest)
    {
      NS_LOG_WARN("Fuzz mode: payload " << payloadSize << " outside VL "
                  << vl.GetVlId() << " range [" << vl.GetMinPayloadSize()
                  << "-" << vl.GetMaxPayloadSize() << "] — allowing for switch validation test");
    }
    else
    {
      NS_LOG_ERROR("Payload size " << payloadSize << " out of range ["
                   << vl.GetMinPayloadSize() << "-" << vl.GetMaxPayloadSize()
                   << "] for VL " << vl.GetVlId());
      return;
    }
  }
  
  VLTrafficConfig config;
  config.vl = vl;
  config.payloadSize = payloadSize;
  config.sequenceNumber = 0;
  
  m_vlConfigs[vl.GetVlId()] = config;
  
  NS_LOG_INFO("Added VL " << vl.GetVlId() << " with payload size " << payloadSize);
}

void
AfdxTrafficGenerator::SubscribeToVirtualLink(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  m_subscribedVLs.insert(vlId);
  
  // Initialize redundancy state for this VL
  RedundancyState state;
  state.lastSeqNum = 0;
  state.firstNetwork = "";
  state.receivedThisSeq = false;
  m_redundancyState[vlId] = state;
  
  // Initialize PSN to 0 (first frame will be 1)
  m_previousSeqNum[vlId] = 0;
  
  NS_LOG_INFO("Subscribed to VL " << vlId << " for receiving");
}

void
AfdxTrafficGenerator::EnableCsvLogging(const std::string& filename)
{
  NS_LOG_FUNCTION(this << filename);
  m_csvEnabled = true;
  m_csvFilename = filename;
}

void
AfdxTrafficGenerator::StartApplication()
{
  NS_LOG_FUNCTION(this);
  
  // Validate network devices
  if (m_dualNetworkMode)
  {
    if (!m_deviceNetworkA || !m_deviceNetworkB)
    {
      NS_LOG_ERROR("Dual network mode enabled but devices not set!");
      return;
    }
    
    // ====================================================================
    // RECEIVE CALLBACKS - Setup for dual network reception
    // ====================================================================
    if (!m_subscribedVLs.empty())
    {
      // Set receive callbacks for Network A
      m_deviceNetworkA->SetReceiveCallback(
        MakeCallback(&AfdxTrafficGenerator::ReceiveFromNetworkA, this));
      
      // Set receive callbacks for Network B
      m_deviceNetworkB->SetReceiveCallback(
        MakeCallback(&AfdxTrafficGenerator::ReceiveFromNetworkB, this));
      
      NS_LOG_INFO("AFDX End System configured to RECEIVE on both networks");
      NS_LOG_INFO("  Subscribed to " << m_subscribedVLs.size() << " VLs");
    }
  }
  else
  {
    if (!m_device)
    {
      NS_LOG_ERROR("No network device set!");
      return;
    }
    
    // Legacy single network receive
    if (!m_subscribedVLs.empty())
    {
      m_device->SetReceiveCallback(
        MakeCallback(&AfdxTrafficGenerator::ReceiveFromNetworkA, this));
    }
  }
  
  // Initialize CSV if enabled
  if (m_csvEnabled && !m_csvFile.is_open())
  {
    m_csvFile.open(m_csvFilename);
    m_csvFile << "Timestamp,Event,VL_ID,Action,Details\n";
    m_csvFile.flush();
    
    std::stringstream ss;
    ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
    std::string mode = m_dualNetworkMode ? "DUAL_NETWORK" : "SINGLE_NETWORK";
    std::string role = "";
    if (!m_vlConfigs.empty() && !m_subscribedVLs.empty()) {
      role = " TX+RX";
    } else if (!m_vlConfigs.empty()) {
      role = " TX_ONLY";
    } else if (!m_subscribedVLs.empty()) {
      role = " RX_ONLY";
    }
    LogToCsv(ss.str(), 0, "APP_START", "End System started (" + mode + role + ")");
  }
  
  // Schedule initial transmissions for all VLs (Publisher role)
  for (auto& entry : m_vlConfigs)
  {
    uint16_t vlId = entry.first;
    
    // Start transmitting after a small delay (stagger VLs)
    Time startDelay = MilliSeconds(vlId % 10); // Stagger by VL ID
    entry.second.transmitEvent = Simulator::Schedule(startDelay, 
                                                     &AfdxTrafficGenerator::TransmitFrame,
                                                     this, vlId);
    
    NS_LOG_INFO("Scheduled initial transmission for VL " << vlId 
                << " at +" << startDelay.GetMilliSeconds() << "ms");
  }
  
  // Start mutation polling for AI-driven fuzzing
  NS_LOG_UNCOND("AFDX Fuzzer: Poll started");
  StartMutationPolling(0.5);
}

void
AfdxTrafficGenerator::StopApplication()
{
  NS_LOG_FUNCTION(this);
  
  // Stop mutation polling
  StopMutationPolling();
  
  // Cancel all pending events
  for (auto& entry : m_vlConfigs)
  {
    Simulator::Cancel(entry.second.transmitEvent);
  }
  
  // Log final statistics
  if (m_csvEnabled)
  {
    std::stringstream ss;
    ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
    LogToCsv(ss.str(), 0, "APP_STOP", 
             "Traffic generator stopped, total frames sent: " + std::to_string(m_framesSent));
  }
  
  if (m_csvFile.is_open())
  {
    m_csvFile.close();
  }
}

void
AfdxTrafficGenerator::TransmitFrame(uint16_t vlId)
{
  NS_LOG_FUNCTION(this << vlId);
  
  auto it = m_vlConfigs.find(vlId);
  if (it == m_vlConfigs.end())
  {
    NS_LOG_ERROR("VL " << vlId << " not found in configuration!");
    return;
  }
  
  VLTrafficConfig& config = it->second;
  
  // Initialize sequence number to 1 on first frame (ARINC 664 P7: never use 0)
  if (config.sequenceNumber == 0)
  {
    config.sequenceNumber = 1;
  }
  
  // Sequence-number mutation: override with fuzzer-supplied value
  uint8_t effectiveSeqNum = config.sequenceNumber;
  if (g_mutationConfig.isActive &&
      g_mutationConfig.targetVL == vlId &&
      g_mutationConfig.sequenceNumberOverride > 0)
  {
    effectiveSeqNum = static_cast<uint8_t>(g_mutationConfig.sequenceNumberOverride & 0xFF);
    g_mutationConfig.seqMutationCount++;
    NS_LOG_INFO("SEQ MUTATION: VL " << vlId << " seq overridden from "
                << (int)config.sequenceNumber << " to " << (int)effectiveSeqNum);
  }
  
  // Create AFDX frame
  AfdxFrame frame;
  frame.SetVirtualLinkId(config.vl.GetVlId());
  frame.SetSequenceNumber(effectiveSeqNum);
  
  // Apply MAC mutation if active (EXTREME MODE - for AI fuzzer edge case testing)
  Mac48Address srcMac = config.vl.GetSourceMac();
  Mac48Address dstMac = config.vl.GetDestinationMac();
  
  if (g_mutationConfig.isActive && 
      g_mutationConfig.targetVL == config.vl.GetVlId() &&
      g_mutationConfig.macMutation != "none")
  {
      Ptr<UniformRandomVariable> rng = CreateObject<UniformRandomVariable>();
      
      if (g_mutationConfig.macMutation == "spoof_src")
      {
          // Spoof source MAC with random unicast address
          uint8_t randomMac[6];
          for (int i = 0; i < 6; i++) {
              randomMac[i] = static_cast<uint8_t>(rng->GetInteger(0, 255));
          }
          randomMac[0] &= 0xFE;  // Clear multicast bit (ensure unicast)
          char macStr[18];
          sprintf(macStr, "%02x:%02x:%02x:%02x:%02x:%02x",
                  randomMac[0], randomMac[1], randomMac[2],
                  randomMac[3], randomMac[4], randomMac[5]);
          srcMac = Mac48Address(macStr);
          g_mutationConfig.macSpoofCount++;
          NS_LOG_INFO("MAC SPOOF: Spoofed source MAC to " << srcMac);
      }
      else if (g_mutationConfig.macMutation == "spoof_dst")
      {
          // Spoof destination MAC with random multicast address
          uint8_t randomMac[6];
          for (int i = 0; i < 6; i++) {
              randomMac[i] = static_cast<uint8_t>(rng->GetInteger(0, 255));
          }
          randomMac[0] |= 0x01;  // Set multicast bit
          char macStr[18];
          sprintf(macStr, "%02x:%02x:%02x:%02x:%02x:%02x",
                  randomMac[0], randomMac[1], randomMac[2],
                  randomMac[3], randomMac[4], randomMac[5]);
          dstMac = Mac48Address(macStr);
          g_mutationConfig.macSpoofCount++;
          NS_LOG_INFO("MAC SPOOF: Spoofed destination MAC to " << dstMac);
      }
      else if (g_mutationConfig.macMutation == "broadcast")
      {
          // Set destination to broadcast address
          dstMac = Mac48Address("ff:ff:ff:ff:ff:ff");
          g_mutationConfig.macSpoofCount++;
          NS_LOG_INFO("MAC SPOOF: Set destination to broadcast");
      }
      else if (g_mutationConfig.macMutation == "invalid_src")
      {
          // Set source to multicast (protocol violation!)
          uint8_t randomMac[6];
          for (int i = 0; i < 6; i++) {
              randomMac[i] = static_cast<uint8_t>(rng->GetInteger(0, 255));
          }
          randomMac[0] |= 0x01;  // Set multicast bit (INVALID for source!)
          char macStr[18];
          sprintf(macStr, "%02x:%02x:%02x:%02x:%02x:%02x",
                  randomMac[0], randomMac[1], randomMac[2],
                  randomMac[3], randomMac[4], randomMac[5]);
          srcMac = Mac48Address(macStr);
          g_mutationConfig.macSpoofCount++;
          NS_LOG_WARN("MAC SPOOF VIOLATION: Set source to multicast (invalid!)");
      }
      else if (g_mutationConfig.macMutation == "zero_mac")
      {
          // Set both to all zeros (invalid!)
          srcMac = Mac48Address("00:00:00:00:00:00");
          dstMac = Mac48Address("00:00:00:00:00:00");
          g_mutationConfig.macSpoofCount++;
          NS_LOG_WARN("MAC SPOOF VIOLATION: Set MACs to all zeros (invalid!)");
      }
  }
  
  // Destination MAC mutation: corrupt the constant-field prefix (triggers ES rejection)
  if (g_mutationConfig.isActive &&
      g_mutationConfig.targetVL == config.vl.GetVlId() &&
      g_mutationConfig.destMacMutation != "none")
  {
    if (g_mutationConfig.destMacMutation == "corrupt_prefix")
    {
      // ARINC 664 constant field is 03:00:00:00 in first 4 octets.
      // Corrupt it to 04:00:00:00 so ValidateConstantField() fails.
      uint8_t mac[6];
      dstMac.CopyTo(mac);
      mac[0] = 0x04;
      char macStr[18];
      sprintf(macStr, "%02x:%02x:%02x:%02x:%02x:%02x",
              mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
      dstMac = Mac48Address(macStr);
      NS_LOG_INFO("DEST_MAC MUTATION: corrupted prefix to 04:xx for VL " << vlId);
    }
    else if (g_mutationConfig.destMacMutation == "wrong_vl")
    {
      // Use a valid AFDX prefix but with a different VL's lower bytes
      uint8_t mac[6];
      dstMac.CopyTo(mac);
      mac[4] = static_cast<uint8_t>((mac[4] + 1) & 0xFF);
      char macStr[18];
      sprintf(macStr, "%02x:%02x:%02x:%02x:%02x:%02x",
              mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
      dstMac = Mac48Address(macStr);
      NS_LOG_INFO("DEST_MAC MUTATION: wrong_vl dest MAC for VL " << vlId);
    }
    else if (g_mutationConfig.destMacMutation == "zero")
    {
      dstMac = Mac48Address("00:00:00:00:00:00");
      NS_LOG_INFO("DEST_MAC MUTATION: zeroed dest MAC for VL " << vlId);
    }
    g_mutationConfig.destMacMutationCount++;
  }
  
  frame.SetSourceAddress(srcMac);
  frame.SetDestinationAddress(dstMac);
  
  // Create payload (default filled)
  std::vector<uint8_t> payload(config.payloadSize, 0xAB);

  // Simple mutation logic: if fuzz mode is active, with probability m_fuzzProbability,
  // flip a single random bit in a random byte of the payload.
  if (m_fuzzMode && config.payloadSize > 0)
  {
    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
    double roll = uv->GetValue(0.0, 1.0);
    if (roll <= m_fuzzProbability)
    {
      // choose random byte offset and random bit to flip
      uint32_t offset = uv->GetInteger(0, static_cast<int>(config.payloadSize) - 1);
      uint8_t orig = payload[offset];
      uint8_t bitIndex = static_cast<uint8_t>(uv->GetInteger(0, 7));
      uint8_t bitMask = static_cast<uint8_t>(1u << bitIndex);
      payload[offset] = static_cast<uint8_t>(orig ^ bitMask);

      // Clear formatting for hex printing to avoid affecting later logs
      std::ios oldState(nullptr);
      oldState.copyfmt(std::cout);

      NS_LOG_UNCOND("AFDX Fuzzer: Mutated frame for VL " << vlId
                   << " offset=" << offset
                   << " orig=0x" << std::hex << static_cast<int>(orig)
                   << " new=0x" << static_cast<int>(payload[offset]) << std::dec);

      std::cout.copyfmt(oldState); // restore
    }
  }

  // Apply payload to frame (possibly mutated)
  frame.SetPayload(payload.data(), config.payloadSize);
  
  // Create packet with payload
  Ptr<Packet> packet = Create<Packet>(payload.data(), config.payloadSize);
  
  // Add AFDX frame header
  uint32_t frameSize = frame.GetSerializedSize();
  uint8_t* buffer = new uint8_t[frameSize];
  Buffer b;
  b.AddAtStart(frameSize);
  Buffer::Iterator bufIt = b.Begin();
  frame.Serialize(bufIt);
  b.CopyData(buffer, frameSize);
  packet = Create<Packet>(buffer, frameSize);
  delete[] buffer;
  
  // ====================================================================
  // AI FUZZER: PROBABILISTIC TX-DROP (for quick observable variance)
  // ====================================================================
  if (g_mutationConfig.isActive && g_mutationConfig.targetVL == vlId && g_mutationConfig.probability > 0.0)
  {
    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
    double roll = uv->GetValue(0.0, 1.0);
    if (roll < g_mutationConfig.probability)
    {
      // Simulate frame dropped at sender (before enqueue)
      g_mutationConfig.txProbDrops++;
      NS_LOG_INFO("VL " << vlId << " seq=" << (int)config.sequenceNumber 
                  << " DROPPED by probability=" << g_mutationConfig.probability);
      
      // Skip sequence increment and schedule next frame
      config.sequenceNumber++;
      if (config.sequenceNumber == 0 || config.sequenceNumber > 255)
      {
        config.sequenceNumber = 1;
      }
      
      // Schedule next transmission (with jitter if applicable)
      Time nextSend = config.vl.GetBag();
      if (g_mutationConfig.timingJitterMs != 0)
      {
        Ptr<UniformRandomVariable> jitterRng = CreateObject<UniformRandomVariable>();
        int jitter_ms = g_mutationConfig.timingJitterMs;
        // GetInteger requires min < max, so use [0, 2*jitter] and subtract jitter
        int applied_jitter = static_cast<int>(jitterRng->GetInteger(0, 2 * jitter_ms)) - jitter_ms;
        Time jitterTime = MilliSeconds(applied_jitter);
        nextSend = nextSend + jitterTime;
        if (nextSend.IsNegative() || nextSend < MicroSeconds(100))
        {
          nextSend = MicroSeconds(100);
          applied_jitter = 0;
        }
        g_mutationConfig.jitterAppliedMs = applied_jitter;
      }
      
      config.transmitEvent = Simulator::Schedule(nextSend,
                                                 &AfdxTrafficGenerator::TransmitFrame,
                                                 this, vlId);
      return;  // Skip actual transmission
    }
  }
  
  bool success = false;
  
  // ====================================================================
  // AFDX DUAL NETWORK REDUNDANCY (ARINC 664 P7 §3.2.6)
  // ====================================================================
  if (m_dualNetworkMode)
  {
    // Transmit on Network A (primary)
    // EtherType 0x88B5 is reserved for AFDX (Avionics Full-Duplex Switched Ethernet)
    bool successA = m_deviceNetworkA->Send(packet->Copy(), 
                                           config.vl.GetDestinationMac(), 0x88B5);
    
    // Transmit on Network B (redundant) - within 0.5ms as per ARINC spec
    // Schedule Network B transmission with small delay (100μs = 0.1ms)
    if (successA)
    {
      Simulator::Schedule(MicroSeconds(100),
                         &AfdxTrafficGenerator::TransmitOnNetworkB,
                         this, packet->Copy(), config.vl.GetDestinationMac(),
                         vlId, config.sequenceNumber);
      
      m_framesSent += 2; // Count both network transmissions
      success = true;
      
      NS_LOG_INFO("VL " << vlId << " seq=" << (int)config.sequenceNumber
                  << " transmitted on BOTH networks (redundancy)");
      
      // Log to CSV - Network A
      if (m_csvEnabled)
      {
        std::stringstream ss;
        ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
        
        std::stringstream details;
        details << "Seq=" << (int)config.sequenceNumber 
                << " Size=" << packet->GetSize() 
                << " Payload=" << config.payloadSize
                << " Network=A";
        
        LogToCsv(ss.str(), vlId, "FRAME_TX", details.str());
      }
    }
  }
  else
  {
    // Legacy single network mode
    // EtherType 0x88B5 for AFDX
    success = m_device->Send(packet, config.vl.GetDestinationMac(), 0x88B5);
    
    if (success)
    {
      m_framesSent++;
      
      NS_LOG_INFO("Sent frame for VL " << vlId 
                  << " seq=" << (int)config.sequenceNumber
                  << " size=" << packet->GetSize());
      
      // Log to CSV
      if (m_csvEnabled)
      {
        std::stringstream ss;
        ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
        
        std::stringstream details;
        details << "Seq=" << (int)config.sequenceNumber 
                << " Size=" << packet->GetSize() 
                << " Payload=" << config.payloadSize;
        
        LogToCsv(ss.str(), vlId, "FRAME_TX", details.str());
      }
    }
  }
  
  if (!success)
  {
    NS_LOG_WARN("Failed to send frame for VL " << vlId);
    
    if (m_csvEnabled)
    {
      std::stringstream ss;
      ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
      LogToCsv(ss.str(), vlId, "FRAME_TX_FAILED", "Device send failed");
    }
  }
  
  // ====================================================================
  // ARINC 664 P7 SEQUENCE NUMBER INCREMENT (CRITICAL)
  // ====================================================================
  // Sequence numbers: 1-255, then wrap to 1 (NEVER use 0)
  // Reference: ARINC 664 P7 §3.2.6.2.1
  config.sequenceNumber++;
  if (config.sequenceNumber == 0 || config.sequenceNumber > 255)
  {
    config.sequenceNumber = 1; // Wrap to 1, not 0
  }
  
  // ====================================================================
  // AI FUZZER: TIMING JITTER APPLICATION (applied to next send time)
  // ====================================================================
  Time nextSend = config.vl.GetBag();
  if (g_mutationConfig.isActive && g_mutationConfig.targetVL == vlId && g_mutationConfig.timingJitterMs != 0)
  {
    Ptr<UniformRandomVariable> jitterRng = CreateObject<UniformRandomVariable>();
    int jitter_ms = g_mutationConfig.timingJitterMs;
    // GetInteger requires min < max, so use [0, 2*jitter] and subtract jitter
    int applied_jitter = static_cast<int>(jitterRng->GetInteger(0, 2 * jitter_ms)) - jitter_ms;
    Time jitterTime = MilliSeconds(applied_jitter);
    nextSend = nextSend + jitterTime;
    
    // Safety: never schedule in the past
    if (nextSend.IsNegative() || nextSend < MicroSeconds(100))
    {
      nextSend = MicroSeconds(100);
      applied_jitter = 0;
    }
    
    g_mutationConfig.jitterAppliedMs = applied_jitter;
    NS_LOG_INFO("VL " << vlId << " timing jitter applied: " << applied_jitter << "ms");
  }
  
  // Schedule next transmission (BAG period + optional jitter)
  config.transmitEvent = Simulator::Schedule(nextSend,
                                             &AfdxTrafficGenerator::TransmitFrame,
                                             this, vlId);
}

void
AfdxTrafficGenerator::TransmitOnNetworkB(Ptr<Packet> packet, Mac48Address dest, 
                                         uint16_t vlId, uint8_t seqNum)
{
  NS_LOG_FUNCTION(this << vlId << (int)seqNum);
  
  // EtherType 0x88B5 for AFDX
  bool success = m_deviceNetworkB->Send(packet, dest, 0x88B5);
  
  if (success)
  {
    NS_LOG_INFO("VL " << vlId << " seq=" << (int)seqNum 
                << " transmitted on Network B (redundant copy)");
    
    // Log to CSV - Network B
    if (m_csvEnabled)
    {
      std::stringstream ss;
      ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
      
      std::stringstream details;
      details << "Seq=" << (int)seqNum 
              << " Size=" << packet->GetSize()
              << " Network=B";
      
      LogToCsv(ss.str(), vlId, "FRAME_TX", details.str());
    }
  }
  else
  {
    NS_LOG_WARN("Failed to send frame on Network B for VL " << vlId);
  }
}

// ========================================================================
// RECEIVE SIDE IMPLEMENTATION (Subscriber/Consumer)
// ========================================================================

bool
AfdxTrafficGenerator::ReceiveFromNetworkA(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                          uint16_t protocol, const Address& from)
{
  NS_LOG_FUNCTION(this << device << packet->GetSize() << protocol);
  return ProcessReceivedFrame(packet, "A");
}

bool
AfdxTrafficGenerator::ReceiveFromNetworkB(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                          uint16_t protocol, const Address& from)
{
  NS_LOG_FUNCTION(this << device << packet->GetSize() << protocol);
  return ProcessReceivedFrame(packet, "B");
}

bool
AfdxTrafficGenerator::ProcessReceivedFrame(Ptr<const Packet> packet, const std::string& networkId)
{
  NS_LOG_FUNCTION(this << packet->GetSize() << networkId);
  
  // Create copy for deserialization
  Ptr<Packet> pktCopy = packet->Copy();
  
  // Deserialize AFDX frame
  AfdxFrame frame;
  pktCopy->RemoveHeader(frame);
  
  uint16_t vlId = frame.GetVirtualLinkId();
  uint8_t seqNum = frame.GetSequenceNumber();
  
  NS_LOG_INFO("ES received frame: VL=" << vlId << " Seq=" << (int)seqNum 
              << " from Network " << networkId);
  
  // ====================================================================
  // AFDX VALIDATION STEP 1: Check VL Subscription
  // ====================================================================
  if (!IsSubscribedToVL(vlId))
  {
    NS_LOG_DEBUG("Not subscribed to VL " << vlId << " - ignoring");
    return false; // Silently ignore (not an error)
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 2: Validate Constant Field (ARINC 664 P7 §3.1.1.3.3)
  // ====================================================================
  if (!ValidateConstantField(frame))
  {
    m_framesRejected++;
    if (m_csvEnabled)
    {
      std::stringstream ss;
      ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
      LogToCsv(ss.str(), vlId, "FRAME_RX_REJECTED", 
               "Invalid constant field from Network " + networkId);
    }
    NS_LOG_WARN("VL " << vlId << " rejected - invalid constant field");
    return false;
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 3: Integrity Checking (ARINC 664 P7 §3.2.6.2.1)
  // ====================================================================
  if (!CheckSequenceNumber(vlId, seqNum))
  {
    m_framesRejected++;
    if (m_csvEnabled)
    {
      std::stringstream ss;
      ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
      std::stringstream details;
      details << "Seq=" << (int)seqNum << " invalid (expected [" 
              << (int)((m_previousSeqNum[vlId] == 255) ? 1 : m_previousSeqNum[vlId] + 1)
              << "-" 
              << (int)((m_previousSeqNum[vlId] >= 254) ? ((m_previousSeqNum[vlId] == 254) ? 255 : 1) : m_previousSeqNum[vlId] + 2)
              << "]) from Network " << networkId;
      LogToCsv(ss.str(), vlId, "FRAME_RX_REJECTED", details.str());
    }
    NS_LOG_WARN("VL " << vlId << " Seq=" << (int)seqNum 
                << " rejected - sequence validation failed");
    return false;
  }
  
  // ====================================================================
  // AFDX VALIDATION STEP 4: Redundancy Management (ARINC 664 P7 §3.2.6.2.2)
  // "First Valid Frame Wins"
  // ====================================================================
  if (!ApplyFirstValidFrameWins(vlId, seqNum, networkId))
  {
    m_duplicatesDiscarded++;
    if (m_csvEnabled)
    {
      std::stringstream ss;
      ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
      std::stringstream details;
      details << "Seq=" << (int)seqNum << " duplicate from Network " << networkId
              << " (already received from Network " << m_redundancyState[vlId].firstNetwork << ")";
      LogToCsv(ss.str(), vlId, "FRAME_RX_DUPLICATE", details.str());
    }
    NS_LOG_DEBUG("VL " << vlId << " Seq=" << (int)seqNum 
                 << " duplicate from Network " << networkId << " - discarding");
    return false;
  }
  
  // ====================================================================
  // FRAME ACCEPTED - All validations passed
  // ====================================================================
  m_framesReceived++;
  m_previousSeqNum[vlId] = seqNum;
  
  if (m_csvEnabled)
  {
    std::stringstream ss;
    ss << std::fixed << std::setprecision(6) << Simulator::Now().GetSeconds();
    std::stringstream details;
    details << "Seq=" << (int)seqNum << " Size=" << packet->GetSize()
            << " from Network " << networkId << " ACCEPTED";
    LogToCsv(ss.str(), vlId, "FRAME_RX_ACCEPTED", details.str());
  }
  
  NS_LOG_INFO("VL " << vlId << " Seq=" << (int)seqNum 
              << " ACCEPTED from Network " << networkId);
  
  return true;
}

bool
AfdxTrafficGenerator::ValidateConstantField(const AfdxFrame& frame)
{
  Mac48Address dest = frame.GetDestinationAddress();
  uint8_t mac[6];
  dest.CopyTo(mac);
  
  // ARINC 664 P7 §3.1.1.3.3: Constant field must be 03:00:00:00
  if (mac[0] != 0x03 || mac[1] != 0x00 || mac[2] != 0x00 || mac[3] != 0x00)
  {
    NS_LOG_WARN("Invalid constant field: " 
                << std::hex << (int)mac[0] << ":" << (int)mac[1] << ":" 
                << (int)mac[2] << ":" << (int)mac[3] << std::dec);
    return false;
  }
  
  return true;
}

bool
AfdxTrafficGenerator::IsSubscribedToVL(uint16_t vlId)
{
  return m_subscribedVLs.find(vlId) != m_subscribedVLs.end();
}

bool
AfdxTrafficGenerator::CheckSequenceNumber(uint16_t vlId, uint8_t seqNum)
{
  // ARINC 664 P7 §3.2.6.2.1: Integrity Checking
  // Valid sequence numbers: [PSN+1, PSN+2]
  // Where PSN = Previous Sequence Number
  // Wrap-around: 255 → 1 (sequence 0 is INVALID)
  
  uint8_t psn = m_previousSeqNum[vlId];
  
  // Calculate expected range [PSN+1, PSN+2]
  uint8_t expected1, expected2;
  
  if (psn == 0)
  {
    // First frame - accept any sequence 1-255
    return (seqNum >= 1 && seqNum <= 255);
  }
  else if (psn == 255)
  {
    // Wrap: PSN=255, valid=[1, 2]
    expected1 = 1;
    expected2 = 2;
  }
  else if (psn == 254)
  {
    // Wrap: PSN=254, valid=[255, 1]
    expected1 = 255;
    expected2 = 1;
  }
  else
  {
    // Normal case: PSN+1, PSN+2
    expected1 = psn + 1;
    expected2 = psn + 2;
  }
  
  bool valid = (seqNum == expected1 || seqNum == expected2);
  
  if (!valid)
  {
    NS_LOG_DEBUG("Sequence check failed: PSN=" << (int)psn 
                 << " expected=[" << (int)expected1 << "," << (int)expected2 << "]"
                 << " received=" << (int)seqNum);
  }
  
  return valid;
}

bool
AfdxTrafficGenerator::ApplyFirstValidFrameWins(uint16_t vlId, uint8_t seqNum, 
                                                const std::string& networkId)
{
  // ARINC 664 P7 §3.2.6.2.2: Redundancy Management
  // "First Valid Frame Wins" algorithm
  
  auto& state = m_redundancyState[vlId];
  
  // Check if this is a new sequence number
  if (state.lastSeqNum != seqNum)
  {
    // NEW sequence number - this is the FIRST frame
    state.lastSeqNum = seqNum;
    state.firstNetwork = networkId;
    state.receivedThisSeq = true;
    
    NS_LOG_DEBUG("VL " << vlId << " Seq=" << (int)seqNum 
                 << " - FIRST VALID from Network " << networkId);
    return true; // ACCEPT
  }
  
  // DUPLICATE - same sequence number already received
  NS_LOG_DEBUG("VL " << vlId << " Seq=" << (int)seqNum 
               << " - DUPLICATE from Network " << networkId 
               << " (first was Network " << state.firstNetwork << ")");
  return false; // REJECT
}

void
AfdxTrafficGenerator::LogToCsv(const std::string& timestamp, uint16_t vlId,
                               const std::string& action, const std::string& details)
{
  if (!m_csvEnabled || !m_csvFile.is_open())
    return;
    
  m_csvFile << timestamp << ","
            << "TRAFFIC_GEN" << ","
            << vlId << ","
            << action << ","
            << details << "\n";
  m_csvFile.flush();
}

// ========================================================================
// FUZZING / AI CONTROLLER INTEGRATION
// ========================================================================

// Helper to get file modification time
static std::time_t
GetFileModTime(const std::string& path)
{
  struct stat st;
  if (stat(path.c_str(), &st) == 0)
    {
      return st.st_mtime;
    }
  return 0;
}

void
AfdxTrafficGenerator::EnableFuzzing(double probability)
{
  m_fuzzMode = true;
  m_fuzzProbability = probability;
  NS_LOG_INFO("AFDX Fuzzer: fuzz mode ENABLED, probability=" << m_fuzzProbability);
}

void
AfdxTrafficGenerator::StartMutationPolling(double intervalSeconds)
{
  if (m_pollingEnabled)
    {
      return;
    }

  m_pollingEnabled = true;
  m_mutationPollInterval = intervalSeconds;

  // Schedule first poll immediately
  m_mutationPollEvent = Simulator::Schedule(Seconds(0.0),
                                            &AfdxTrafficGenerator::PollMutations,
                                            this);

  NS_LOG_INFO("AFDX Fuzzer: mutation polling STARTED, interval="
              << m_mutationPollInterval << "s");
}

void
AfdxTrafficGenerator::StopMutationPolling()
{
  m_pollingEnabled = false;
  if (m_mutationPollEvent.IsRunning())
    {
      m_mutationPollEvent.Cancel();
    }
  NS_LOG_INFO("AFDX Fuzzer: mutation polling STOPPED");
}

void
AfdxTrafficGenerator::PollMutations()
{
  // Path where the Python controller writes instructions
  const std::string path = "examples/AFDX_V3/mutations.json";

  // Check if file exists and changed
  std::time_t mt = GetFileModTime(path);

  if (mt != 0 && mt != m_lastMutationFileTime)
    {
      // New content detected
      std::ifstream ifs(path.c_str());
      if (ifs.good())
        {
          std::ostringstream ss;
          ss << ifs.rdbuf();
          std::string content = ss.str();

          NS_LOG_INFO("AFDX Fuzzer: Detected new mutations.json content:\n"
                      << content);

          // Basic behavior for now:
          //   - enable fuzzMode
          //   - record timestamp so we don't reprocess the same file over and over
          m_fuzzMode = true;
          m_lastMutationFileTime = mt;
        }
    }

  // Reschedule next poll if still active
  if (m_pollingEnabled)
    {
      m_mutationPollEvent = Simulator::Schedule(
          Seconds(m_mutationPollInterval),
          &AfdxTrafficGenerator::PollMutations,
          this);
    }
}

} // namespace ns3
