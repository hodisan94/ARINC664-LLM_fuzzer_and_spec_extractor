/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * Virtual Link Configuration
 */

#ifndef AFDX_VIRTUAL_LINK_H
#define AFDX_VIRTUAL_LINK_H

#include "ns3/nstime.h"
#include "ns3/mac48-address.h"
#include <string>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief AFDX Virtual Link Priority Levels (ARINC 664 Part 7)
 * 
 * Four priority levels for Quality of Service (QoS):
 * - CRITICAL: Safety-critical, real-time control (highest priority)
 * - HIGH: Important operational data
 * - MEDIUM: Standard operational traffic
 * - LOW: Non-critical, background traffic (lowest priority)
 */
enum AfdxPriority : uint8_t
{
  AFDX_PRIORITY_LOW = 0,       ///< Low priority (background traffic)
  AFDX_PRIORITY_MEDIUM = 1,    ///< Medium priority (standard traffic)
  AFDX_PRIORITY_HIGH = 2,      ///< High priority (important traffic)
  AFDX_PRIORITY_CRITICAL = 3   ///< Critical priority (safety-critical)
};

/**
 * \ingroup afdx
 * \brief AFDX Virtual Link
 *
 * A Virtual Link defines a unidirectional logical connection
 * from one source End System to one or more destination End Systems.
 */
class AfdxVirtualLink
{
public:
  AfdxVirtualLink();
  ~AfdxVirtualLink();

  // Configuration setters
  void SetVlId(uint16_t vlId);
  void SetName(const std::string& name);
  void SetSourceMac(Mac48Address srcMac);
  void SetDestinationMac(Mac48Address dstMac);
  void SetBag(Time bag);  // Bandwidth Allocation Gap
  void SetMaxFrameSize(uint32_t maxSize);
  void SetMinFrameSize(uint32_t minSize);
  void SetMinPayloadSize(uint32_t minPayload);  // ARINC 664 Part 7: Min payload per VL
  void SetMaxPayloadSize(uint32_t maxPayload);  // ARINC 664 Part 7: Max payload per VL
  void SetPriority(AfdxPriority priority);      // ARINC 664 Part 7: QoS priority level

  // Configuration getters
  uint16_t GetVlId() const;
  std::string GetName() const;
  Mac48Address GetSourceMac() const;
  Mac48Address GetDestinationMac() const;
  Time GetBag() const;
  uint32_t GetMaxFrameSize() const;
  uint32_t GetMinFrameSize() const;
  uint32_t GetMinPayloadSize() const;  // ARINC 664 Part 7: Payload range
  uint32_t GetMaxPayloadSize() const;  // ARINC 664 Part 7: Payload range
  AfdxPriority GetPriority() const;    // ARINC 664 Part 7: QoS priority level

  // Validation
  bool IsValid() const;

private:
  uint16_t m_vlId;              ///< Virtual Link Identifier
  std::string m_name;           ///< VL name
  Mac48Address m_sourceMac;     ///< Source MAC
  Mac48Address m_destinationMac; ///< Destination MAC
  Time m_bag;                   ///< Bandwidth Allocation Gap
  uint32_t m_maxFrameSize;      ///< Max frame size
  uint32_t m_minFrameSize;      ///< Min frame size
  uint32_t m_minPayloadSize;    ///< Min payload size (ARINC 664 Part 7: variable payload)
  uint32_t m_maxPayloadSize;    ///< Max payload size (ARINC 664 Part 7: variable payload)
  AfdxPriority m_priority;      ///< Priority level (ARINC 664 Part 7: QoS)
};

} // namespace ns3

#endif /* AFDX_VIRTUAL_LINK_H */
