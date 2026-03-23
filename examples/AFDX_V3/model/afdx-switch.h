/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Switch - ARINC 664 Part 7 Compliant Switch
 *
 * Implements AFDX switch functionality according to ARINC 664 Part 7:
 * - Filtering and policing (CRC, frame size, MAC, VL authorization, BAG)
 * - Forwarding based on static switching table
 * - Per-VL statistics and monitoring
 */

#ifndef AFDX_SWITCH_H
#define AFDX_SWITCH_H

#include "ns3/application.h"
#include "ns3/net-device.h"
#include "ns3/mac48-address.h"
#include "ns3/packet.h"
#include "afdx-frame.h"
#include "afdx-virtual-link.h"
#include <map>
#include <set>
#include <vector>
#include <queue>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief AFDX Switch implementing ARINC 664 Part 7
 *
 * Performs:
 * 1. Filtering & Policing: CRC, frame size, MAC validity, VL authorization, BAG policing
 * 2. Forwarding: Static port mapping based on VL configuration
 * 3. Monitoring: Per-VL counters and logs
 */
class AfdxSwitch : public Application
{
public:
  static TypeId GetTypeId(void);
  
  AfdxSwitch();
  virtual ~AfdxSwitch();

  /**
   * \brief Set the switch identifier
   * \param switchId Unique switch ID (e.g., 1 for Switch A, 2 for Switch B)
   */
  void SetSwitchId(uint32_t switchId);

  /**
   * \brief Get the switch identifier
   */
  uint32_t GetSwitchId() const;

  /**
   * \brief Add a network device (port) to this switch
   * \param port The NetDevice to add
   */
  void AddSwitchPort(Ptr<NetDevice> port);

  /**
   * \brief Configure a Virtual Link for this switch
   * \param vl The Virtual Link configuration
   * \param outputPorts List of output port indices for this VL
   */
  void ConfigureVirtualLink(const AfdxVirtualLink& vl, const std::vector<uint32_t>& outputPorts);

  /**
   * \brief Get total frames received on this switch
   */
  uint64_t GetFramesReceived() const;

  /**
   * \brief Get total frames forwarded by this switch
   */
  uint64_t GetFramesForwarded() const;

  /**
   * \brief Get total frames dropped by this switch
   */
  uint64_t GetFramesDropped() const;

  /**
   * \brief Get frames dropped due to policing violations
   */
  uint64_t GetFramesDroppedPolicing() const;

  /**
   * \brief Get frames dropped due to invalid VL
   */
  uint64_t GetFramesDroppedInvalidVL() const;

  /**
   * \brief Get frames dropped due to frame errors (CRC, size)
   */
  uint64_t GetFramesDroppedFrameError() const;

  /**
   * \brief Get frames dropped due to buffer overflow
   */
  uint64_t GetFramesDroppedBufferOverflow() const;

  /**
   * \brief Get frames dropped due to age timeout (max latency exceeded)
   */
  uint64_t GetFramesDroppedAgedOut() const;

  /**
   * \brief Get detailed discard statistics by reason
   * \param reason Output map: reason string -> count
   */
  void GetDiscardReasons(std::map<std::string, uint64_t>& reasons) const;

  /**
   * \brief Set maximum frame age (latency threshold)
   * \param maxAge Maximum age before frame is discarded
   */
  void SetMaxFrameAge(Time maxAge);

  /**
   * \brief Get maximum frame age setting
   */
  Time GetMaxFrameAge() const;

  /**
   * \brief Get per-VL statistics
   * \param vlId Virtual Link identifier
   * \param forwarded Output: frames forwarded for this VL
   * \param dropped Output: frames dropped for this VL
   * \param policingViolations Output: BAG policing violations
   * \return true if VL exists, false otherwise
   */
  bool GetVLStatistics(uint16_t vlId, uint64_t& forwarded, uint64_t& dropped, 
                       uint64_t& policingViolations) const;

  /**
   * \brief Get token bucket credits for a VL
   * \param vlId Virtual Link identifier
   * \return Current credit level (in bytes), -1 if VL not found
   */
  double GetTokenBucketCredits(uint16_t vlId) const;

  /**
   * \brief Print switch statistics
   */
  void PrintStatistics(std::ostream& os) const;

  /**
   * \brief Get per-port statistics (Phase 5)
   * \param port Port index
   * \param rxFrames Output: frames received on this port
   * \param txFrames Output: frames transmitted on this port
   * \param rxErrors Output: receive errors
   * \param txErrors Output: transmit errors
   * \param queueDepth Output: current queue depth across all priorities
   * \return true if port exists
   */
  bool GetPortStatistics(uint32_t port, uint64_t& rxFrames, uint64_t& txFrames,
                         uint64_t& rxErrors, uint64_t& txErrors, uint32_t& queueDepth) const;

  /**
   * \brief Get queue statistics for a priority level
   * \param priority Priority level
   * \param enqueued Output: total frames enqueued
   * \param transmitted Output: total frames transmitted
   * \param dropped Output: total frames dropped
   * \return true if valid priority
   */
  bool GetQueueStatistics(AfdxPriority priority, uint64_t& enqueued,
                          uint64_t& transmitted, uint64_t& dropped) const;

  /**
   * \brief Get average latency for a VL (Phase 5)
   * \param vlId Virtual Link ID
   * \return Average latency in microseconds, -1 if no data
   */
  double GetAverageLatency(uint16_t vlId) const;

  /**
   * \brief Reset all statistics counters
   */
  void ResetStatistics();

  /**
   * \brief Export statistics in MIB format (SNMP-like)
   * \param os Output stream
   */
  void ExportMIB(std::ostream& os) const;

  /**
   * \brief Enable/disable strict BAG policing
   * \param enable If true, enforce BAG policing strictly
   */
  void SetStrictBagPolicing(bool enable);

  /**
   * \brief Enable/disable frame validation (CRC, size)
   * \param enable If true, validate frames
   */
  void SetFrameValidation(bool enable);

protected:
  virtual void StartApplication(void);
  virtual void StopApplication(void);

private:
  /**
   * \brief Callback when frame arrives on a port (normal mode)
   */
  bool ReceiveFromDevice(Ptr<NetDevice> device, Ptr<const Packet> packet,
                         uint16_t protocol, const Address& from);

  /**
   * \brief Callback when frame arrives on a port (promiscuous mode)
   * This allows the switch to see ALL traffic on the channel
   */
  bool PromiscReceiveFromDevice(Ptr<NetDevice> device, Ptr<const Packet> packet,
                                uint16_t protocol, const Address& from,
                                const Address& to, NetDevice::PacketType packetType);

  /**
   * \brief Process incoming frame
   * \return true if forwarded, false if dropped
   */
  bool ProcessFrame(Ptr<const Packet> packet, uint32_t inPort);

  /**
   * \brief Validate frame integrity (CRC, size, structure)
   * \return true if valid, false otherwise
   */
  bool ValidateFrame(const AfdxFrame& frame) const;

  /**
   * \brief Check if VL is authorized on this switch
   */
  bool IsVLAuthorized(uint16_t vlId) const;

  /**
   * \brief Perform BAG policing check
   * \return true if frame passes policing, false if violates BAG
   */
  bool CheckBagPolicing(uint16_t vlId);

  /**
   * \brief Get output ports for a given VL
   */
  std::vector<uint32_t> GetOutputPorts(uint16_t vlId) const;

  /**
   * \brief Forward frame to specified ports
   */
  void ForwardFrame(Ptr<Packet> packet, const std::vector<uint32_t>& ports, uint32_t inPort);

  /**
   * \brief Enqueue frame in priority queue (ARINC 664 Part 7 QoS)
   * \param packet Packet to enqueue
   * \param port Output port
   * \param priority Priority level
   * \return true if enqueued, false if queue full (head-drop policy)
   */
  bool EnqueueFrame(Ptr<Packet> packet, uint32_t port, AfdxPriority priority);

  /**
   * \brief Process priority queues and transmit frames
   * 
   * Implements strict priority scheduling:
   * - Check queues in order: CRITICAL → HIGH → MEDIUM → LOW
   * - Transmit from highest priority non-empty queue
   */
  void ProcessQueues();

  /**
   * \brief Schedule next queue processing event
   */
  void ScheduleQueueProcessing();

  /**
   * \brief Log drop event
   */
  void LogDrop(uint16_t vlId, const std::string& reason);

  // Switch configuration
  uint32_t m_switchId;
  bool m_strictBagPolicing;
  bool m_frameValidation;
  Time m_maxFrameAge;  ///< Maximum frame age before discard (ARINC 664 latency limit)

  // Network ports
  std::vector<Ptr<NetDevice>> m_ports;

  // VL configuration: VL ID -> VL config
  std::map<uint16_t, AfdxVirtualLink> m_vlConfig;

  // Forwarding table: VL ID -> output port indices
  std::map<uint16_t, std::vector<uint32_t>> m_forwardingTable;

  // BAG policing: VL ID -> last frame arrival time
  std::map<uint16_t, Time> m_lastFrameTime;

  // Token Bucket Policing (ARINC 664 Part 7 §6.4.4)
  struct TokenBucket
  {
    double credits;           // Current token credits (in bytes)
    Time lastUpdate;          // Last time credits were updated
    double maxCredits;        // Maximum burst size (Lmax + Jmax per ARINC 664)
    double refillRate;        // Bytes per second based on BAG
    uint32_t consecutiveViolations;  // For babbling idiot detection
    
    TokenBucket() 
      : credits(0.0), 
        lastUpdate(Seconds(0)), 
        maxCredits(0.0), 
        refillRate(0.0),
        consecutiveViolations(0) 
    {}
  };
  std::map<uint16_t, TokenBucket> m_tokenBuckets;

  // Priority Queuing (ARINC 664 Part 7 QoS)
  struct QueuedFrame
  {
    Ptr<Packet> packet;
    uint16_t vlId;
    Time timestamp;  ///< Time when frame entered switch (for age calculation)
    
    QueuedFrame(Ptr<Packet> pkt, uint16_t vl, Time ts) 
      : packet(pkt), vlId(vl), timestamp(ts) {}
  };

  // Per-port priority queues: port index -> priority level -> queue of frames
  std::map<uint32_t, std::map<AfdxPriority, std::queue<QueuedFrame>>> m_priorityQueues;
  
  // Queue configuration
  static const uint32_t MAX_QUEUE_SIZE = 100;  ///< Max frames per priority queue
  Time m_queueProcessingInterval;              ///< How often to process queues
  EventId m_queueProcessingEvent;              ///< Scheduled queue processing event
  
  // Queue statistics
  std::map<AfdxPriority, uint64_t> m_queueDrops;  ///< Drops per priority level
  std::map<AfdxPriority, uint64_t> m_queueTx;     ///< Transmissions per priority level

  /**
   * \brief Initialize token bucket for a VL
   */
  void InitializeTokenBucket(uint16_t vlId);

  /**
   * \brief Update token bucket credits based on elapsed time
   */
  void RefillTokenBucket(uint16_t vlId);

  /**
   * \brief Check if frame can be forwarded (sufficient credits)
   * \param vlId Virtual Link ID
   * \param frameSize Frame size in bytes
   * \return true if sufficient credits, false otherwise
   */
  bool CheckTokenBucket(uint16_t vlId, uint32_t frameSize);

  /**
   * \brief Debit tokens for transmitted frame
   */
  void DebitTokenBucket(uint16_t vlId, uint32_t frameSize);

  // Statistics - Global
  uint64_t m_framesReceived;
  uint64_t m_framesForwarded;
  uint64_t m_framesDropped;
  uint64_t m_framesDroppedPolicing;
  uint64_t m_framesDroppedInvalidVL;
  uint64_t m_framesDroppedFrameError;
  uint64_t m_framesDroppedMACError;        ///< Frames dropped due to source MAC mismatch
  uint64_t m_framesDroppedBufferOverflow;  ///< Frames dropped due to queue overflow
  uint64_t m_framesDroppedAgedOut;         ///< Frames dropped due to age timeout

  // Detailed discard tracking (ARINC 664 Part 7 §3.5 Monitoring)
  std::map<std::string, uint64_t> m_discardReasons;  ///< Detailed discard reason counters

  // Statistics - Per VL
  struct VLStats
  {
    uint64_t framesForwarded;
    uint64_t framesDropped;
    uint64_t policingViolations;
    uint64_t sequenceErrors;        // Phase 5: Sequence number errors
    double totalLatency;            // Phase 5: Sum of latencies for averaging
    uint32_t latencySamples;        // Phase 5: Number of latency samples
    Time firstFrameTime;            // Phase 5: Time of first frame
    Time lastFrameTime;             // Phase 5: Time of last frame
    
    VLStats() 
      : framesForwarded(0), framesDropped(0), policingViolations(0),
        sequenceErrors(0), totalLatency(0.0), latencySamples(0),
        firstFrameTime(Seconds(0)), lastFrameTime(Seconds(0)) {}
  };
  std::map<uint16_t, VLStats> m_vlStats;

  // Statistics - Per Port (Phase 5)
  struct PortStats
  {
    uint64_t rxFrames;
    uint64_t txFrames;
    uint64_t rxErrors;
    uint64_t txErrors;
    
    PortStats() : rxFrames(0), txFrames(0), rxErrors(0), txErrors(0) {}
  };
  std::map<uint32_t, PortStats> m_portStats;

  // Statistics - Queue (Phase 5)
  std::map<AfdxPriority, uint64_t> m_queueEnqueued;  // Total enqueued per priority
};

} // namespace ns3

#endif /* AFDX_SWITCH_H */
