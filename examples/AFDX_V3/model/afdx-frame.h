/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Frame Header - ARINC 664 Part 7
 */

#ifndef AFDX_FRAME_H
#define AFDX_FRAME_H

#include "ns3/header.h"
#include "ns3/mac48-address.h"
#include <string>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief AFDX Frame Header (ARINC 664 Part 7)
 *
 * AFDX Frame Structure:
 * - Destination MAC Address (6 bytes)
 * - Source MAC Address (6 bytes)
 * - EtherType (2 bytes) = 0x88B5
 * - VL ID (2 bytes)
 * - Sequence Number (1 byte)
 * - Payload (variable, max 1471 bytes)
 * - FCS (4 bytes) - handled by lower layer
 */
class AfdxFrame : public Header
{
public:
  static TypeId GetTypeId();

  AfdxFrame();
  virtual ~AfdxFrame();

  // Setters
  void SetDestinationAddress(Mac48Address dst);
  void SetSourceAddress(Mac48Address src);
  void SetVirtualLinkId(uint16_t vlId);
  void SetSequenceNumber(uint8_t seqNum);
  void SetPayload(const uint8_t* data, uint32_t length);
  void SetPayloadWithVlRange(const class AfdxVirtualLink& vl, const uint8_t* data, uint32_t length);

  // Getters
  Mac48Address GetDestinationAddress() const;
  Mac48Address GetSourceAddress() const;
  uint16_t GetVirtualLinkId() const;
  uint8_t GetSequenceNumber() const;
  uint32_t GetPayloadSize() const;
  const uint8_t* GetPayload() const;

  // Header serialization
  virtual TypeId GetInstanceTypeId() const;
  virtual void Print(std::ostream& os) const;
  virtual uint32_t GetSerializedSize() const;
  virtual void Serialize(Buffer::Iterator start) const;
  virtual uint32_t Deserialize(Buffer::Iterator start);

private:
  Mac48Address m_destinationAddress;  ///< Destination MAC
  Mac48Address m_sourceAddress;       ///< Source MAC
  uint16_t m_etherType;               ///< EtherType = 0x88B5
  uint16_t m_vlId;                    ///< Virtual Link ID
  uint8_t m_sequenceNumber;           ///< Sequence number (0-255)
  uint8_t m_payload[9000];            ///< Buffer sized for fuzz testing (normal max: 1471)
  uint32_t m_payloadSize;             ///< Actual payload size
};

} // namespace ns3

#endif /* AFDX_FRAME_H */
