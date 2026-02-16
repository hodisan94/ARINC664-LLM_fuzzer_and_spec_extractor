/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Frame Implementation
 */

#include "afdx-frame.h"
#include "afdx-virtual-link.h"
#include "ns3/log.h"
#include <cstring>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("AfdxFrame");

NS_OBJECT_ENSURE_REGISTERED(AfdxFrame);

TypeId
AfdxFrame::GetTypeId()
{
  static TypeId tid = TypeId("ns3::AfdxFrame")
                          .SetParent<Header>()
                          .SetGroupName("Afdx")
                          .AddConstructor<AfdxFrame>();
  return tid;
}

AfdxFrame::AfdxFrame()
    : m_etherType(0x88B5),  // AFDX EtherType
      m_vlId(0),
      m_sequenceNumber(0),
      m_payloadSize(0)
{
  memset(m_payload, 0, sizeof(m_payload));
}

AfdxFrame::~AfdxFrame()
{
}

void
AfdxFrame::SetDestinationAddress(Mac48Address dst)
{
  // AFDX destination addresses should follow multicast format: 03:00:00:00:XX:XX
  // Where XX:XX represents the VL ID
  // We accept any address but log warning if not AFDX standard
  uint8_t dstBuf[6];
  dst.CopyTo(dstBuf);
  
  if (dstBuf[0] != 0x03 || dstBuf[1] != 0x00 || dstBuf[2] != 0x00 || dstBuf[3] != 0x00)
  {
    NS_LOG_WARN("Destination MAC " << dst << " does not follow AFDX multicast format (03:00:00:00:XX:XX)");
  }
  
  m_destinationAddress = dst;
}

void
AfdxFrame::SetSourceAddress(Mac48Address src)
{
  uint8_t srcBuf[6];
  src.CopyTo(srcBuf);
  
  // Validate source MAC address according to Ethernet/AFDX rules
  
  // Check 1: Source cannot be broadcast address (FF:FF:FF:FF:FF:FF)
  bool isBroadcast = true;
  for (int i = 0; i < 6; i++)
  {
    if (srcBuf[i] != 0xFF)
    {
      isBroadcast = false;
      break;
    }
  }
  NS_ASSERT_MSG(!isBroadcast, "Source MAC cannot be broadcast address (FF:FF:FF:FF:FF:FF)");
  
  // Check 2: Source cannot be multicast (bit 0 of first octet must be 0)
  // Multicast addresses have the least significant bit of the first byte set to 1
  bool isMulticast = (srcBuf[0] & 0x01) != 0;
  NS_ASSERT_MSG(!isMulticast, "Source MAC cannot be multicast address (bit 0 of first octet is set)");
  
  // Check 3: Source cannot be all zeros (00:00:00:00:00:00)
  bool isAllZeros = true;
  for (int i = 0; i < 6; i++)
  {
    if (srcBuf[i] != 0x00)
    {
      isAllZeros = false;
      break;
    }
  }
  NS_ASSERT_MSG(!isAllZeros, "Source MAC cannot be all zeros (00:00:00:00:00:00)");
  
  m_sourceAddress = src;
}

void
AfdxFrame::SetVirtualLinkId(uint16_t vlId)
{
  // AFDX VL ID is a 12-bit field (0-4095)
  // ARINC 664 Part 7 specification
  NS_ASSERT_MSG(vlId <= 4095, 
                "Virtual Link ID must be 12-bit (0-4095). Received: " << vlId);
  
  m_vlId = vlId;
}

void
AfdxFrame::SetSequenceNumber(uint8_t seqNum)
{
  m_sequenceNumber = seqNum;
}

void
AfdxFrame::SetPayload(const uint8_t* data, uint32_t length)
{
  // ARINC 664 Part 7: Payload range is 1-1471 bytes (variable per VL)
  // Minimum Ethernet frame is 64 bytes (17-byte header + 47-byte payload minimum)
  // But ARINC allows payloads down to 1 byte with padding
  // Maximum is 1471 bytes (to make 1488-byte frame with 17-byte header)
  
  NS_ASSERT_MSG(length >= 1, 
                "Payload must be at least 1 byte (ARINC 664 Part 7). Received: " << length);
  NS_ASSERT_MSG(length <= 1471, 
                "Payload exceeds maximum AFDX frame size (1471 bytes). Received: " << length);
  
  m_payloadSize = length;
  memcpy(m_payload, data, length);
}

void
AfdxFrame::SetPayloadWithVlRange(const AfdxVirtualLink& vl, const uint8_t* data, uint32_t length)
{
  // Validate payload is within VL's configured range
  uint32_t minPayload = vl.GetMinPayloadSize();
  uint32_t maxPayload = vl.GetMaxPayloadSize();
  
  NS_ASSERT_MSG(length >= minPayload && length <= maxPayload,
                "Payload length (" << length << ") must be within VL payload range [" 
                << minPayload << "," << maxPayload << "] for VL " << vl.GetVlId());
  
  // Use standard SetPayload for actual storage
  SetPayload(data, length);
}

Mac48Address
AfdxFrame::GetDestinationAddress() const
{
  return m_destinationAddress;
}

Mac48Address
AfdxFrame::GetSourceAddress() const
{
  return m_sourceAddress;
}

uint16_t
AfdxFrame::GetVirtualLinkId() const
{
  return m_vlId;
}

uint8_t
AfdxFrame::GetSequenceNumber() const
{
  return m_sequenceNumber;
}

uint32_t
AfdxFrame::GetPayloadSize() const
{
  return m_payloadSize;
}

const uint8_t*
AfdxFrame::GetPayload() const
{
  return m_payload;
}

TypeId
AfdxFrame::GetInstanceTypeId() const
{
  return GetTypeId();
}

void
AfdxFrame::Print(std::ostream& os) const
{
  os << "AFDX [VL=" << m_vlId 
     << " Seq=" << (uint32_t)m_sequenceNumber
     << " Dst=" << m_destinationAddress
     << " Src=" << m_sourceAddress
     << " Size=" << m_payloadSize << "]";
}

uint32_t
AfdxFrame::GetSerializedSize() const
{
  // MAC dst (6) + MAC src (6) + EtherType (2) + VL ID (2) + Seq (1) + Payload
  return 6 + 6 + 2 + 2 + 1 + m_payloadSize;
}

void
AfdxFrame::Serialize(Buffer::Iterator start) const
{
  // Pre-serialization validation checks
  
  // Check 1: Source and destination cannot be the same (loopback not allowed)
  NS_ASSERT_MSG(m_sourceAddress != m_destinationAddress,
                "Source and destination MAC addresses cannot be identical (no loopback)");
  
  // Check 2: VL ID consistency with destination MAC (AFDX requirement)
  // In AFDX, the last 2 bytes of destination MAC should match the VL ID
  uint8_t dstBuf[6];
  m_destinationAddress.CopyTo(dstBuf);
  uint16_t macVlId = (dstBuf[4] << 8) | dstBuf[5];
  
  if (macVlId != m_vlId)
  {
    NS_LOG_WARN("VL ID (" << m_vlId << ") does not match destination MAC last 2 bytes (" 
                << macVlId << "). AFDX requires consistency.");
  }
  
  // Check 3: Frame size validation
  uint32_t totalSize = 6 + 6 + 2 + 2 + 1 + m_payloadSize;
  NS_ASSERT_MSG(totalSize >= 64, 
                "Total frame size (" << totalSize << " bytes) is below Ethernet minimum (64 bytes)");
  NS_ASSERT_MSG(totalSize <= 1518, 
                "Total frame size (" << totalSize << " bytes) exceeds Ethernet maximum (1518 bytes)");
  
  // Serialize frame fields
  
  // Destination MAC Address (6 bytes)
  uint8_t dstBuf2[6];
  m_destinationAddress.CopyTo(dstBuf2);
  start.Write(dstBuf2, 6);

  // Source MAC Address (6 bytes)
  uint8_t srcBuf[6];
  m_sourceAddress.CopyTo(srcBuf);
  start.Write(srcBuf, 6);

  // EtherType (2 bytes) - 0x88B5 for AFDX
  start.WriteHtonU16(m_etherType);

  // Virtual Link ID (2 bytes)
  start.WriteHtonU16(m_vlId);

  // Sequence Number (1 byte)
  start.WriteU8(m_sequenceNumber);

  // Payload
  start.Write(m_payload, m_payloadSize);
}

uint32_t
AfdxFrame::Deserialize(Buffer::Iterator start)
{
  // Check if we have enough data for minimum AFDX frame
  uint32_t availableSize = start.GetRemainingSize();
  uint32_t minFrameSize = 64;  // Ethernet minimum
  
  if (availableSize < minFrameSize)
  {
    NS_LOG_WARN("Buffer too small for valid AFDX frame. Available: " 
                << availableSize << " bytes, Minimum: " << minFrameSize << " bytes");
    // Return 0 to indicate deserialization failure
    return 0;
  }
  
  // Destination MAC Address (6 bytes)
  uint8_t dstBuf[6];
  start.Read(dstBuf, 6);
  m_destinationAddress.CopyFrom(dstBuf);

  // Source MAC Address (6 bytes)
  uint8_t srcBuf[6];
  start.Read(srcBuf, 6);
  m_sourceAddress.CopyFrom(srcBuf);

  // EtherType (2 bytes)
  m_etherType = start.ReadNtohU16();
  
  // Validate EtherType is AFDX (0x88B5)
  if (m_etherType != 0x88B5)
  {
    NS_LOG_WARN("Invalid EtherType: 0x" << std::hex << m_etherType 
                << " (expected 0x88B5 for AFDX)");
    // Continue anyway for compatibility, but log the issue
  }

  // Virtual Link ID (2 bytes)
  m_vlId = start.ReadNtohU16();
  
  // Validate VL ID range
  if (m_vlId > 4095)
  {
    NS_LOG_ERROR("Invalid VL ID: " << m_vlId << " (maximum is 4095)");
  }

  // Sequence Number (1 byte)
  m_sequenceNumber = start.ReadU8();

  // Calculate remaining payload size
  uint32_t headerSize = 6 + 6 + 2 + 2 + 1;
  m_payloadSize = start.GetRemainingSize();
  
  // Validate payload size
  if (m_payloadSize > 1471)
  {
    NS_LOG_ERROR("Payload size (" << m_payloadSize 
                 << " bytes) exceeds AFDX maximum (1471 bytes)");
    m_payloadSize = 1471;  // Truncate to maximum
  }
  
  if (m_payloadSize > 0)
  {
    start.Read(m_payload, m_payloadSize);
  }

  return headerSize + m_payloadSize;
}

} // namespace ns3
