/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * Virtual Link Implementation
 */

#include "afdx-virtual-link.h"

namespace ns3 {

AfdxVirtualLink::AfdxVirtualLink()
    : m_vlId(0),
      m_name(""),
      m_bag(MilliSeconds(0)),
      m_maxFrameSize(1518),
      m_minFrameSize(64),
      m_minPayloadSize(1),      // ARINC 664 Part 7: minimum 1 byte payload
      m_maxPayloadSize(1471),   // ARINC 664 Part 7: maximum 1471 bytes payload
      m_priority(AFDX_PRIORITY_MEDIUM)  // Default to medium priority
{
}

AfdxVirtualLink::~AfdxVirtualLink()
{
}

void
AfdxVirtualLink::SetVlId(uint16_t vlId)
{
  m_vlId = vlId;
}

void
AfdxVirtualLink::SetName(const std::string& name)
{
  m_name = name;
}

void
AfdxVirtualLink::SetSourceMac(Mac48Address srcMac)
{
  m_sourceMac = srcMac;
}

void
AfdxVirtualLink::SetDestinationMac(Mac48Address dstMac)
{
  m_destinationMac = dstMac;
}

void
AfdxVirtualLink::SetBag(Time bag)
{
  m_bag = bag;
}

void
AfdxVirtualLink::SetMaxFrameSize(uint32_t maxSize)
{
  m_maxFrameSize = maxSize;
  uint32_t headerSize = 17; // 6+6+2+2+1
  if (maxSize > headerSize)
  {
    m_maxPayloadSize = maxSize - headerSize;
  }
}

void
AfdxVirtualLink::SetMinFrameSize(uint32_t minSize)
{
  m_minFrameSize = minSize;
  uint32_t headerSize = 17;
  if (minSize > headerSize)
  {
    m_minPayloadSize = minSize - headerSize;
  }
}

void
AfdxVirtualLink::SetMinPayloadSize(uint32_t minPayload)
{
  // ARINC 664 Part 7: Variable payload per VL, range 1-1471 bytes
  // Note: Minimum Ethernet frame is 64 bytes, so min payload is typically 47 bytes
  // But ARINC allows payloads down to 1 byte (with padding to meet 64-byte minimum)
  NS_ASSERT_MSG(minPayload >= 1 && minPayload <= 1471,
                "VL min payload must be 1-1471 bytes (ARINC 664 Part 7)");
  NS_ASSERT_MSG(minPayload <= m_maxPayloadSize,
                "VL min payload (" << minPayload << ") cannot exceed max payload (" << m_maxPayloadSize << ")");
  m_minPayloadSize = minPayload;
}

void
AfdxVirtualLink::SetMaxPayloadSize(uint32_t maxPayload)
{
  // ARINC 664 Part 7: Variable payload per VL, range 1-1471 bytes
  NS_ASSERT_MSG(maxPayload >= 1 && maxPayload <= 1471,
                "VL max payload must be 1-1471 bytes (ARINC 664 Part 7)");
  NS_ASSERT_MSG(maxPayload >= m_minPayloadSize,
                "VL max payload (" << maxPayload << ") cannot be less than min payload (" << m_minPayloadSize << ")");
  m_maxPayloadSize = maxPayload;
}

uint16_t
AfdxVirtualLink::GetVlId() const
{
  return m_vlId;
}

std::string
AfdxVirtualLink::GetName() const
{
  return m_name;
}

Mac48Address
AfdxVirtualLink::GetSourceMac() const
{
  return m_sourceMac;
}

Mac48Address
AfdxVirtualLink::GetDestinationMac() const
{
  return m_destinationMac;
}

Time
AfdxVirtualLink::GetBag() const
{
  return m_bag;
}

uint32_t
AfdxVirtualLink::GetMaxFrameSize() const
{
  return m_maxFrameSize;
}

uint32_t
AfdxVirtualLink::GetMinFrameSize() const
{
  return m_minFrameSize;
}

uint32_t
AfdxVirtualLink::GetMinPayloadSize() const
{
  return m_minPayloadSize;
}

uint32_t
AfdxVirtualLink::GetMaxPayloadSize() const
{
  return m_maxPayloadSize;
}

void
AfdxVirtualLink::SetPriority(AfdxPriority priority)
{
  m_priority = priority;
}

AfdxPriority
AfdxVirtualLink::GetPriority() const
{
  return m_priority;
}

bool
AfdxVirtualLink::IsValid() const
{
  if (m_vlId == 0) return false;
  if (m_bag.IsZero() || m_bag.IsNegative()) return false;
  if (m_minFrameSize > m_maxFrameSize) return false;
  if (m_sourceMac == Mac48Address() || m_destinationMac == Mac48Address()) return false;
  return true;
}

} // namespace ns3
