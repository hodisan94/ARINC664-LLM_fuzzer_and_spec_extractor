/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Helper - Simplifies AFDX network setup
 */

#ifndef AFDX_HELPER_H
#define AFDX_HELPER_H

#include "ns3/node-container.h"
#include "ns3/net-device-container.h"
#include "ns3/application-container.h"
#include "ns3/csma-helper.h"
#include "ns3/bridge-helper.h"
#include "ns3/internet-stack-helper.h"
#include "../model/afdx-end-system.h"
#include "../model/afdx-virtual-link.h"
#include <string>

namespace ns3 {

/**
 * \ingroup afdx
 * \brief Helper to create AFDX star topology with redundant networks
 *
 * Simplifies creation of AFDX networks with:
 * - Redundant switches (Network A and Network B)
 * - End Systems with dual network interfaces
 * - VL configuration and management
 */
class AfdxHelper
{
public:
  AfdxHelper();
  ~AfdxHelper();

  /**
   * \brief Create AFDX star topology
   * \param numEndSystems Number of End Systems
   * \return Container with End System nodes
   */
  NodeContainer CreateStarTopology(uint32_t numEndSystems);

  /**
   * \brief Get switch node for Network A
   */
  Ptr<Node> GetSwitchA() const;

  /**
   * \brief Get switch node for Network B
   */
  Ptr<Node> GetSwitchB() const;

  /**
   * \brief Get End System nodes
   */
  NodeContainer GetEndSystems() const;

  /**
   * \brief Install AFDX End System application on node
   * \param node The End System node
   * \param nodeId Unique End System identifier
   * \param csvFile Path to CSV log file
   * \return AfdxEndSystem application
   */
  Ptr<AfdxEndSystem> InstallEndSystem(Ptr<Node> node, uint32_t nodeId, 
                                      const std::string& csvFile);

  /**
   * \brief Configure CSMA parameters
   */
  void SetCsmaDataRate(DataRate rate);
  void SetCsmaDelay(Time delay);

  /**
   * \brief Enable PCAP tracing
   */
  void EnablePcap(const std::string& prefix);

private:
  void CreateSwitches();
  void CreateEndSystemLinks(NodeContainer esNodes);
  void InstallInternetStack();

  // Topology nodes
  NodeContainer m_switchNodes;      // Switch A and Switch B
  NodeContainer m_endSystemNodes;   // All End Systems

  // Network devices
  NetDeviceContainer m_switchADevices;
  NetDeviceContainer m_switchBDevices;
  std::vector<NetDeviceContainer> m_esDevicesA;  // ES Network A devices
  std::vector<NetDeviceContainer> m_esDevicesB;  // ES Network B devices

  // Helpers
  CsmaHelper m_csmaHelper;
  BridgeHelper m_bridgeHelper;
  InternetStackHelper m_internetStack;

  // Configuration
  DataRate m_dataRate;
  Time m_delay;
  bool m_pcapEnabled;
  std::string m_pcapPrefix;
};

} // namespace ns3

#endif /* AFDX_HELPER_H */
