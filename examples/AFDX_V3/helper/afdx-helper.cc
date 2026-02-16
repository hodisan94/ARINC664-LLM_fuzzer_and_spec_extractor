/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2025 AFDX Simulation
 *
 * AFDX Helper Implementation
 */

#include "afdx-helper.h"
#include "ns3/log.h"
#include "ns3/ipv4-address-helper.h"
#include "ns3/bridge-net-device.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("AfdxHelper");

AfdxHelper::AfdxHelper()
    : m_dataRate(DataRate("100Mbps")),
      m_delay(MicroSeconds(10)),
      m_pcapEnabled(false),
      m_pcapPrefix("afdx")
{
  NS_LOG_FUNCTION(this);
  
  // Configure CSMA defaults for AFDX (100Mbps full-duplex)
  m_csmaHelper.SetChannelAttribute("DataRate", DataRateValue(m_dataRate));
  m_csmaHelper.SetChannelAttribute("Delay", TimeValue(m_delay));
}

AfdxHelper::~AfdxHelper()
{
  NS_LOG_FUNCTION(this);
}

void
AfdxHelper::SetCsmaDataRate(DataRate rate)
{
  m_dataRate = rate;
  m_csmaHelper.SetChannelAttribute("DataRate", DataRateValue(rate));
}

void
AfdxHelper::SetCsmaDelay(Time delay)
{
  m_delay = delay;
  m_csmaHelper.SetChannelAttribute("Delay", TimeValue(delay));
}

void
AfdxHelper::EnablePcap(const std::string& prefix)
{
  m_pcapEnabled = true;
  m_pcapPrefix = prefix;
}

NodeContainer
AfdxHelper::CreateStarTopology(uint32_t numEndSystems)
{
  NS_LOG_FUNCTION(this << numEndSystems);
  
  NS_LOG_INFO("Creating AFDX Star Topology with " << numEndSystems << " End Systems");
  
  // Create switch nodes (Network A and Network B)
  CreateSwitches();
  
  // Create End System nodes
  m_endSystemNodes.Create(numEndSystems);
  
  // Create links between End Systems and switches
  CreateEndSystemLinks(m_endSystemNodes);
  
  // Install Internet stack
  InstallInternetStack();
  
  NS_LOG_INFO("AFDX topology created successfully");
  
  return m_endSystemNodes;
}

void
AfdxHelper::CreateSwitches()
{
  NS_LOG_FUNCTION(this);
  
  // Create two switch nodes (Network A and Network B)
  m_switchNodes.Create(2);
  
  NS_LOG_INFO("Created Switch A (Network A) and Switch B (Network B)");
}

void
AfdxHelper::CreateEndSystemLinks(NodeContainer esNodes)
{
  NS_LOG_FUNCTION(this);
  
  uint32_t numES = esNodes.GetN();
  
  // For each End System, create two dedicated links:
  // - One to Switch A (Network A)
  // - One to Switch B (Network B)
  
  for (uint32_t i = 0; i < numES; i++)
  {
    Ptr<Node> esNode = esNodes.Get(i);
    Ptr<Node> switchA = m_switchNodes.Get(0);
    Ptr<Node> switchB = m_switchNodes.Get(1);
    
    // Create link ES <-> Switch A (Network A)
    NodeContainer linkA(esNode, switchA);
    NetDeviceContainer devicesA = m_csmaHelper.Install(linkA);
    m_esDevicesA.push_back(devicesA);
    m_switchADevices.Add(devicesA.Get(1));  // Switch side
    
    // Create link ES <-> Switch B (Network B)
    NodeContainer linkB(esNode, switchB);
    NetDeviceContainer devicesB = m_csmaHelper.Install(linkB);
    m_esDevicesB.push_back(devicesB);
    m_switchBDevices.Add(devicesB.Get(1));  // Switch side
    
    NS_LOG_INFO("Created links for ES" << i << " to both switches");
  }
  
  // Install bridges on switches
  NetDeviceContainer bridgeDevicesA = m_bridgeHelper.Install(m_switchNodes.Get(0), m_switchADevices);
  NetDeviceContainer bridgeDevicesB = m_bridgeHelper.Install(m_switchNodes.Get(1), m_switchBDevices);
  
  NS_LOG_INFO("Installed bridges on Switch A (" << m_switchADevices.GetN() 
              << " ports) and Switch B (" << m_switchBDevices.GetN() << " ports)");
  
  // Enable PCAP if requested
  if (m_pcapEnabled)
  {
    for (uint32_t i = 0; i < numES; i++)
    {
      m_csmaHelper.EnablePcap(m_pcapPrefix + "-es" + std::to_string(i) + "-netA", 
                              m_esDevicesA[i].Get(0), true);
      m_csmaHelper.EnablePcap(m_pcapPrefix + "-es" + std::to_string(i) + "-netB", 
                              m_esDevicesB[i].Get(0), true);
    }
    NS_LOG_INFO("PCAP tracing enabled with prefix: " << m_pcapPrefix);
  }
}

void
AfdxHelper::InstallInternetStack()
{
  NS_LOG_FUNCTION(this);
  
  // Install Internet stack on End Systems and switches
  NodeContainer allNodes;
  allNodes.Add(m_endSystemNodes);
  allNodes.Add(m_switchNodes);
  
  m_internetStack.Install(allNodes);
  
  // Assign IP addresses
  Ipv4AddressHelper addressA;
  addressA.SetBase("10.1.0.0", "255.255.255.0");
  
  Ipv4AddressHelper addressB;
  addressB.SetBase("10.2.0.0", "255.255.255.0");
  
  // Assign addresses to ES devices (Network A)
  for (uint32_t i = 0; i < m_esDevicesA.size(); i++)
  {
    NetDeviceContainer tempDevices;
    tempDevices.Add(m_esDevicesA[i].Get(0));  // Only ES side
    addressA.Assign(tempDevices);
  }
  
  // Assign addresses to ES devices (Network B)
  for (uint32_t i = 0; i < m_esDevicesB.size(); i++)
  {
    NetDeviceContainer tempDevices;
    tempDevices.Add(m_esDevicesB[i].Get(0));  // Only ES side
    addressB.Assign(tempDevices);
  }
  
  NS_LOG_INFO("IP addresses assigned (Network A: 10.1.0.x, Network B: 10.2.0.x)");
}

Ptr<Node>
AfdxHelper::GetSwitchA() const
{
  return m_switchNodes.Get(0);
}

Ptr<Node>
AfdxHelper::GetSwitchB() const
{
  return m_switchNodes.Get(1);
}

NodeContainer
AfdxHelper::GetEndSystems() const
{
  return m_endSystemNodes;
}

Ptr<AfdxEndSystem>
AfdxHelper::InstallEndSystem(Ptr<Node> node, uint32_t nodeId, const std::string& csvFile)
{
  NS_LOG_FUNCTION(this << node << nodeId << csvFile);
  
  // Find this node's index in the End Systems list
  int32_t nodeIndex = -1;
  for (uint32_t i = 0; i < m_endSystemNodes.GetN(); i++)
  {
    if (m_endSystemNodes.Get(i) == node)
    {
      nodeIndex = i;
      break;
    }
  }
  
  if (nodeIndex < 0)
  {
    NS_LOG_ERROR("Node not found in End Systems");
    return nullptr;
  }
  
  // Create AFDX End System application
  Ptr<AfdxEndSystem> endSystem = CreateObject<AfdxEndSystem>();
  endSystem->SetNodeId(nodeId);
  endSystem->SetCsvFile(csvFile);
  
  // Set network devices (redundant networks)
  Ptr<NetDevice> deviceA = m_esDevicesA[nodeIndex].Get(0);
  Ptr<NetDevice> deviceB = m_esDevicesB[nodeIndex].Get(0);
  
  endSystem->SetNetworkADevice(deviceA);
  endSystem->SetNetworkBDevice(deviceB);
  
  // Install application on node
  node->AddApplication(endSystem);
  
  NS_LOG_INFO("Installed AFDX End System on node " << nodeId);
  
  return endSystem;
}

} // namespace ns3
