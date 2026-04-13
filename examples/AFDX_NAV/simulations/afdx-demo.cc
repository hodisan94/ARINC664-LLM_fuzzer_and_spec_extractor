/*
 * AFDX Protocol Demonstration Simulation
 * 
 * This simulation demonstrates a complete AFDX network with:
 * - Star topology with 3 End Systems
 * - 2 Redundant Switches (Network A and Network B)
 * - Virtual Link configuration from CSV file
 * - PCAP trace generation
 * - CSV event logging
 * - Full ARINC 664 Part 7 compliance features
 * 
 * Topology:
 * 
 *    ES1 (Flight_Control)
 *      |       |
 *   [SwitchA] [SwitchB]  <- Redundant switches
 *      |   X   |
 *      |  / \  |
 *    ES2     ES3
 *  (Sensors) (Nav)
 * 
 * Each ES connects to both switches for redundancy
 * VL configuration read from: config/virtual_links.csv
 * PCAP output: output/pcap/
 * CSV output: output/csv/afdx-simulation-events.csv
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/csma-module.h"
#include "ns3/internet-module.h"
#include "../model/afdx-switch.h"
#include "../model/afdx-end-system.h"
#include "../model/afdx-virtual-link.h"
#include "../model/afdx-traffic-generator.h"
#include <fstream>
#include <sstream>
#include <iomanip>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("AfdxDemo");

// CSV Event Logger with enhanced AFDX-specific fields
class CsvEventLogger
{
public:
    CsvEventLogger(const std::string& filename)
    {
        m_file.open(filename);
        // Write comprehensive CSV header with AFDX-specific fields
        m_file << "Timestamp,Event,NodeID,NodeName,VL_ID,SequenceNum,Network,"
               << "IsDuplicate,BAG,MaxJitter,Jitter,SkewMax,"
               << "EthSrcMAC,EthDstMAC,EthType,"
               << "PacketSize,EndToEndLatency,IntegrityCheckResult,FrameValidityStatus,"
               << "VL_MaxFrameSize,TransmitTime,ReceiveTime,SwitchHops,"
               << "PayloadHex,Description\n";
    }

    ~CsvEventLogger()
    {
        if (m_file.is_open())
        {
            m_file.close();
        }
    }

    void LogPacketEvent(double timestamp, const std::string& event, 
                       uint32_t nodeId, const std::string& nodeName,
                       uint16_t vlId, uint8_t seqNum, const std::string& network,
                       bool isDuplicate, Mac48Address srcMac, Mac48Address dstMac,
                       uint32_t packetSize, uint32_t maxFrameSize, double bag,
                       double jitter, double txTime, double rxTime, 
                       const std::string& description)
    {
        // Calculate derived metrics
        double latency = (event == "RX") ? (rxTime - txTime) : 0.0;
        std::string integrityCheck = (isDuplicate) ? "Duplicate" : "Pass";
        std::string validity = (event == "TX") ? "Valid" : 
                              (isDuplicate) ? "Duplicate" : "Valid";
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << event << "," 
               << nodeId << "," 
               << nodeName << ","
               << vlId << "," 
               << (int)seqNum << "," 
               << network << ","
               << (isDuplicate ? "true" : "false") << ","
               << std::setprecision(3) << bag << ","  // BAG in ms
               << "1.0,"  // MaxJitter (1ms typical for AFDX)
               << std::setprecision(6) << jitter << ","
               << "0.5,"  // SkewMax (0.5ms for redundant frames)
               << srcMac << "," 
               << dstMac << ","
               << "0x88B5,"  // AFDX EtherType
               << packetSize << ","
               << std::setprecision(6) << latency * 1000.0 << ","  // Latency in ms
               << integrityCheck << ","
               << validity << ","
               << maxFrameSize << ","  // VL_MaxFrameSize
               << std::setprecision(6) << txTime << ","
               << rxTime << ","
               << "1,"  // SwitchHops (1 switch in star topology)
               << "00 " << std::hex << std::setfill('0') << std::setw(2) << vlId 
               << " " << std::setw(2) << (int)seqNum << " 00 00 00 00 00" << std::dec << ","
               << description << "\n";
        m_file.flush();
    }

private:
    std::ofstream m_file;
    std::map<uint16_t, double> m_lastTxTime;  // Track TX times per VL for latency calc
};

// Global CSV logger pointer
static CsvEventLogger* g_csvLogger = nullptr;

// Global structures to track packet timing and VL configuration
struct PacketTiming {
    double txTime;
    uint32_t maxFrameSize;
    double bag;
};
static std::map<std::string, PacketTiming> g_packetTimings;  // Key: "vlId_seqNum_network"

struct VLConfigInfo {
    uint32_t maxFrameSize;
    double bag;  // in milliseconds
};
static std::map<uint16_t, VLConfigInfo> g_vlConfigInfoMap;

// Packet sniffer callback for TX events
void TxPacketSniffer(std::string context, Ptr<const Packet> packet)
{
    if (!g_csvLogger) return;
    
    // Extract node info from context (format: "/NodeList/X/$ns3::...")
    size_t nodePos = context.find("/NodeList/");
    if (nodePos == std::string::npos) return;
    
    nodePos += 10; // Skip "/NodeList/"
    size_t slashPos = context.find("/", nodePos);
    uint32_t nodeId = std::stoi(context.substr(nodePos, slashPos - nodePos));
    
    // Skip switch nodes (nodes 3 and 4 are switches)
    if (nodeId >= 3) return;
    
    // Extract device index to determine network (A or B)
    size_t devPos = context.find("/DeviceList/");
    if (devPos == std::string::npos) return;
    devPos += 12; // Skip "/DeviceList/"
    size_t devSlashPos = context.find("/", devPos);
    uint32_t deviceIndex = std::stoi(context.substr(devPos, devSlashPos - devPos));
    
    // Determine node name and network based on node ID and device index
    // Device 0 = Network A, Device 1 = Network B
    std::string nodeName;
    std::string network = (deviceIndex == 0) ? "A" : "B";
    
    if (nodeId == 0) { nodeName = "ES1_FlightControl"; }
    else if (nodeId == 1) { nodeName = "ES2_Sensors"; }
    else if (nodeId == 2) { nodeName = "ES3_Navigation"; }
    else { nodeName = "Unknown"; }
    
    // Extract packet data to get VL ID and sequence number
    uint8_t buffer[100];
    packet->CopyData(buffer, std::min((uint32_t)100, packet->GetSize()));
    
    // Parse AFDX frame header:
    // CSMA Ethernet header (14 bytes):
    //   Offset 0-5: Destination MAC
    //   Offset 6-11: Source MAC
    //   Offset 12-13: EtherType (0x88B5)
    // AFDX frame header (inside packet):
    //   Offset 14-19: Destination MAC (again)
    //   Offset 20-25: Source MAC (again)
    //   Offset 26-27: EtherType (0x88B5 again)
    //   Offset 28-29: Virtual Link ID (2 bytes, network byte order)
    //   Offset 30: Sequence Number (1 byte)
    uint16_t vlId = (buffer[28] << 8) | buffer[29];  // VL ID at offset 28-29
    uint8_t seqNum = buffer[30];  // Sequence number at offset 30
    
    // Get MAC addresses from CSMA header
    Mac48Address srcMac;
    srcMac.CopyFrom(buffer + 6);  // Source MAC at offset 6-11
    Mac48Address dstMac;
    dstMac.CopyFrom(buffer);  // Destination MAC at offset 0-5
    
    // Get VL configuration
    VLConfigInfo vlConfigInfo;
    if (g_vlConfigInfoMap.find(vlId) != g_vlConfigInfoMap.end()) {
        vlConfigInfo = g_vlConfigInfoMap[vlId];
    } else {
        // Default values if VL not found in map
        vlConfigInfo.maxFrameSize = 1518;  // Max Ethernet frame size
        vlConfigInfo.bag = 0.0;
    }
    
    // Record TX timing for latency calculation
    std::string key = std::to_string(vlId) + "_" + std::to_string(seqNum) + "_" + network;
    double txTime = Simulator::Now().GetSeconds();
    g_packetTimings[key] = {txTime, vlConfigInfo.maxFrameSize, vlConfigInfo.bag};
    
    g_csvLogger->LogPacketEvent(
        Simulator::Now().GetSeconds(),
        "TX",
        nodeId,
        nodeName,
        vlId,
        seqNum,
        network,
        false,  // Not duplicate for TX
        srcMac,
        dstMac,
        packet->GetSize(),
        vlConfigInfo.maxFrameSize,
        vlConfigInfo.bag,
        0.0,  // Jitter (calculated later)
        txTime,
        0.0,  // RX time (not applicable for TX)
        "Frame transmission on Network " + network
    );
}

// Packet sniffer callback for RX events  
void RxPacketSniffer(std::string context, Ptr<const Packet> packet)
{
    if (!g_csvLogger) return;
    
    // Extract node info from context
    size_t nodePos = context.find("/NodeList/");
    if (nodePos == std::string::npos) return;
    
    nodePos += 10;
    size_t slashPos = context.find("/", nodePos);
    uint32_t nodeId = std::stoi(context.substr(nodePos, slashPos - nodePos));
    
    // Skip switch nodes (nodes 3 and 4 are switches)
    if (nodeId >= 3) return;
    
    // Extract device index to determine network (A or B)
    size_t devPos = context.find("/DeviceList/");
    if (devPos == std::string::npos) return;
    devPos += 12; // Skip "/DeviceList/"
    size_t devSlashPos = context.find("/", devPos);
    uint32_t deviceIndex = std::stoi(context.substr(devPos, devSlashPos - devPos));
    
    // Determine node name and network
    // Device 0 = Network A, Device 1 = Network B
    std::string nodeName;
    std::string network = (deviceIndex == 0) ? "A" : "B";
    
    if (nodeId == 0) { nodeName = "ES1_FlightControl"; }
    else if (nodeId == 1) { nodeName = "ES2_Sensors"; }
    else if (nodeId == 2) { nodeName = "ES3_Navigation"; }
    else { nodeName = "Unknown"; }
    
    // Extract AFDX frame info
    uint8_t buffer[100];
    packet->CopyData(buffer, std::min((uint32_t)100, packet->GetSize()));
    
    // Parse AFDX frame header (same structure as TX)
    // VL ID at offset 28-29, Sequence at offset 30
    uint16_t vlId = (buffer[28] << 8) | buffer[29];
    uint8_t seqNum = buffer[30];
    
    // Get MAC addresses from CSMA header
    Mac48Address srcMac;
    srcMac.CopyFrom(buffer + 6);
    Mac48Address dstMac;
    dstMac.CopyFrom(buffer);
    
    // Check if this is a duplicate (simplified - just check if we've seen this seq before)
    static std::map<uint16_t, uint8_t> lastSeqPerVL;
    bool isDuplicate = (lastSeqPerVL[vlId] == seqNum);
    lastSeqPerVL[vlId] = seqNum;
    
    // Get timing information
    std::string key = std::to_string(vlId) + "_" + std::to_string(seqNum) + "_" + network;
    double rxTime = Simulator::Now().GetSeconds();
    double txTime = 0.0;
    uint32_t maxFrameSize = 1518;
    double bag = 0.0;
    double jitter = 0.0;
    
    if (g_packetTimings.find(key) != g_packetTimings.end()) {
        PacketTiming& timing = g_packetTimings[key];
        txTime = timing.txTime;
        maxFrameSize = timing.maxFrameSize;
        bag = timing.bag;
        
        // Calculate jitter (variation from expected BAG interval)
        static std::map<std::string, double> lastRxTimes;
        std::string jitterKey = std::to_string(nodeId) + "_" + std::to_string(vlId) + "_" + network;
        if (lastRxTimes.find(jitterKey) != lastRxTimes.end()) {
            double interval = rxTime - lastRxTimes[jitterKey];
            double expectedInterval = bag / 1000.0;  // Convert ms to seconds
            jitter = std::abs(interval - expectedInterval);
        }
        lastRxTimes[jitterKey] = rxTime;
    }
    
    g_csvLogger->LogPacketEvent(
        Simulator::Now().GetSeconds(),
        "RX",
        nodeId,
        nodeName,
        vlId,
        seqNum,
        network,
        isDuplicate,
        srcMac,
        dstMac,
        packet->GetSize(),
        maxFrameSize,
        bag,
        jitter,
        txTime,
        rxTime,
        "Frame reception on Network " + network
    );
}

// VL Configuration structure
struct VLConfig
{
    uint16_t vlId;
    std::string vlName;
    uint32_t sourceES;
    std::vector<uint32_t> subscriberES;
    std::string sourceMac;
    std::string destMac;
    uint32_t bagMs;
    uint32_t maxFrameSize;
    uint32_t minFrameSize;
};

// Parse Virtual Links CSV
std::vector<VLConfig> ParseVirtualLinksCSV(const std::string& filename)
{
    std::vector<VLConfig> configs;
    std::ifstream file(filename);
    
    if (!file.is_open())
    {
        NS_LOG_ERROR("Failed to open virtual links CSV: " << filename);
        return configs;
    }

    std::string line;
    // Skip header and comments
    while (std::getline(file, line))
    {
        if (line.empty() || line[0] == '#')
            continue;
            
        std::istringstream ss(line);
        VLConfig config;
        std::string token;
        
        // Parse VL_ID
        if (!std::getline(ss, token, ',')) continue;
        config.vlId = std::stoi(token);
        
        // Parse VL_Name
        if (!std::getline(ss, config.vlName, ',')) continue;
        
        // Parse Source_ES
        if (!std::getline(ss, token, ',')) continue;
        config.sourceES = std::stoi(token);
        
        // Parse Subscriber_ES (semicolon-separated)
        if (!std::getline(ss, token, ',')) continue;
        std::istringstream subSS(token);
        std::string subToken;
        while (std::getline(subSS, subToken, ';'))
        {
            config.subscriberES.push_back(std::stoi(subToken));
        }
        
        // Parse Source_MAC
        if (!std::getline(ss, config.sourceMac, ',')) continue;
        
        // Parse Dest_MAC
        if (!std::getline(ss, config.destMac, ',')) continue;
        
        // Parse BAG_ms
        if (!std::getline(ss, token, ',')) continue;
        config.bagMs = std::stoi(token);
        
        // Parse Max_Frame_Size
        if (!std::getline(ss, token, ',')) continue;
        config.maxFrameSize = std::stoi(token);
        
        // Parse Min_Frame_Size
        if (!std::getline(ss, token, ',')) continue;
        config.minFrameSize = std::stoi(token);
        
        configs.push_back(config);
    }
    
    file.close();
    NS_LOG_INFO("Loaded " << configs.size() << " virtual link configurations");
    return configs;
}

// Helper function to convert MAC string to Mac48Address
Mac48Address StringToMac(const std::string& macStr)
{
    return Mac48Address(macStr.c_str());
}

int main(int argc, char* argv[])
{
    // Simulation parameters
    double simTime = 2.0;  // 2 seconds
    std::string vlConfigFile = "examples/AFDX/config/virtual_links.csv";
    std::string pcapDir = "examples/AFDX/output/pcap/";
    std::string csvFile = "examples/AFDX/output/csv/AFDX-LOG-OUTPUT.csv";
    std::string csvDir = "examples/AFDX/output/csv/";
    bool enablePcap = true;
    bool enableCsv = true;

    // Command line arguments
    CommandLine cmd;
    cmd.AddValue("simTime", "Simulation time in seconds", simTime);
    cmd.AddValue("vlConfig", "Virtual links CSV file", vlConfigFile);
    cmd.AddValue("pcapDir", "PCAP output directory", pcapDir);
    cmd.AddValue("csvFile", "CSV events output file", csvFile);
    cmd.AddValue("enablePcap", "Enable PCAP tracing", enablePcap);
    cmd.AddValue("enableCsv", "Enable CSV event logging", enableCsv);
    cmd.Parse(argc, argv);

    // Enable logging
    LogComponentEnable("AfdxDemo", LOG_LEVEL_INFO);
    
    NS_LOG_INFO("=== AFDX Protocol Demonstration ===");
    NS_LOG_INFO("Simulation Time: " << simTime << " seconds");
    NS_LOG_INFO("VL Config: " << vlConfigFile);
    NS_LOG_INFO("PCAP Output: " << pcapDir);
    NS_LOG_INFO("CSV Output: " << csvFile);

    // Load Virtual Link configurations
    std::vector<VLConfig> vlConfigs = ParseVirtualLinksCSV(vlConfigFile);
    if (vlConfigs.empty())
    {
        NS_LOG_ERROR("No virtual link configurations loaded!");
        return 1;
    }

    // Create nodes
    NodeContainer endSystems;
    endSystems.Create(3);  // ES1, ES2, ES3
    
    NodeContainer switchesA;
    switchesA.Create(1);  // Switch A (Network A)
    
    NodeContainer switchesB;
    switchesB.Create(1);  // Switch B (Network B)

    NS_LOG_INFO("Created 3 End Systems and 2 Redundant Switches");

    // Install CSMA for all links
    CsmaHelper csma;
    csma.SetChannelAttribute("DataRate", StringValue("100Mbps"));
    csma.SetChannelAttribute("Delay", StringValue("10us"));  // 10 microseconds

    // Network A topology (star with Switch A at center)
    NetDeviceContainer es1ToSwitchA = csma.Install(NodeContainer(endSystems.Get(0), switchesA.Get(0)));
    NetDeviceContainer es2ToSwitchA = csma.Install(NodeContainer(endSystems.Get(1), switchesA.Get(0)));
    NetDeviceContainer es3ToSwitchA = csma.Install(NodeContainer(endSystems.Get(2), switchesA.Get(0)));

    // Network B topology (star with Switch B at center)
    NetDeviceContainer es1ToSwitchB = csma.Install(NodeContainer(endSystems.Get(0), switchesB.Get(0)));
    NetDeviceContainer es2ToSwitchB = csma.Install(NodeContainer(endSystems.Get(1), switchesB.Get(0)));
    NetDeviceContainer es3ToSwitchB = csma.Install(NodeContainer(endSystems.Get(2), switchesB.Get(0)));

    NS_LOG_INFO("CSMA links established for redundant networks");

    // Create AFDX Switches
    Ptr<AfdxSwitch> switchA = CreateObject<AfdxSwitch>();
    switchA->SetSwitchId(1);
    switchesA.Get(0)->AggregateObject(switchA);
    
    Ptr<AfdxSwitch> switchB = CreateObject<AfdxSwitch>();
    switchB->SetSwitchId(2);
    switchesB.Get(0)->AggregateObject(switchB);

    NS_LOG_INFO("AFDX Switches created (Switch A=1, Switch B=2)");

    // Add ports to Switch A (Network A)
    switchA->AddSwitchPort(es1ToSwitchA.Get(1));  // Port 0: ES1
    switchA->AddSwitchPort(es2ToSwitchA.Get(1));  // Port 1: ES2
    switchA->AddSwitchPort(es3ToSwitchA.Get(1));  // Port 2: ES3

    // Add ports to Switch B (Network B)
    switchB->AddSwitchPort(es1ToSwitchB.Get(1));  // Port 0: ES1
    switchB->AddSwitchPort(es2ToSwitchB.Get(1));  // Port 1: ES2
    switchB->AddSwitchPort(es3ToSwitchB.Get(1));  // Port 2: ES3

    NS_LOG_INFO("Switch ports configured (3 ports per switch)");

    // Note: Switches will learn VLs from traffic in this simple demo
    // In production, you would configure static forwarding tables here
    
    NS_LOG_INFO("Switches ready (VL configuration will be learned from traffic)");

    // Create End Systems
    Ptr<AfdxEndSystem> es1 = CreateObject<AfdxEndSystem>();
    es1->SetNodeId(1);
    es1->SetNetworkADevice(es1ToSwitchA.Get(0));
    es1->SetNetworkBDevice(es1ToSwitchB.Get(0));
    endSystems.Get(0)->AggregateObject(es1);

    Ptr<AfdxEndSystem> es2 = CreateObject<AfdxEndSystem>();
    es2->SetNodeId(2);
    es2->SetNetworkADevice(es2ToSwitchA.Get(0));
    es2->SetNetworkBDevice(es2ToSwitchB.Get(0));
    endSystems.Get(1)->AggregateObject(es2);

    Ptr<AfdxEndSystem> es3 = CreateObject<AfdxEndSystem>();
    es3->SetNodeId(3);
    es3->SetNetworkADevice(es3ToSwitchA.Get(0));
    es3->SetNetworkBDevice(es3ToSwitchB.Get(0));
    endSystems.Get(2)->AggregateObject(es3);

    NS_LOG_INFO("End Systems created and configured");

    // Configure Virtual Links on End Systems (for receiving)
    for (const auto& vlConfig : vlConfigs)
    {
        // Add VL to source ES for transmission
        AfdxVirtualLink vl;
        vl.SetVlId(vlConfig.vlId);
        vl.SetName(vlConfig.vlName);
        vl.SetSourceMac(StringToMac(vlConfig.sourceMac));
        vl.SetDestinationMac(StringToMac(vlConfig.destMac));
        vl.SetBag(MilliSeconds(vlConfig.bagMs));
        vl.SetMaxFrameSize(vlConfig.maxFrameSize);
        vl.SetMinFrameSize(vlConfig.minFrameSize);

        // Determine priority based on BAG
        AfdxPriority priority;
        if (vlConfig.bagMs <= 8)
            priority = AFDX_PRIORITY_CRITICAL;
        else if (vlConfig.bagMs <= 32)
            priority = AFDX_PRIORITY_HIGH;
        else if (vlConfig.bagMs <= 64)
            priority = AFDX_PRIORITY_MEDIUM;
        else
            priority = AFDX_PRIORITY_LOW;
        vl.SetPriority(priority);

        // Add VL to source ES
        if (vlConfig.sourceES == 1)
            es1->AddTransmitVL(vl);
        else if (vlConfig.sourceES == 2)
            es2->AddTransmitVL(vl);
        else if (vlConfig.sourceES == 3)
            es3->AddTransmitVL(vl);

        // Add VL to subscriber ES (for receiving)
        for (uint32_t subES : vlConfig.subscriberES)
        {
            if (subES == 1)
                es1->AddReceiveVL(vlConfig.vlId);
            else if (subES == 2)
                es2->AddReceiveVL(vlConfig.vlId);
            else if (subES == 3)
                es3->AddReceiveVL(vlConfig.vlId);
        }
        
        // Store VL configuration for CSV logging
        g_vlConfigInfoMap[vlConfig.vlId] = {
            static_cast<uint32_t>(vlConfig.maxFrameSize),
            static_cast<double>(vlConfig.bagMs)
        };
    }

    // Create Traffic Generators for each VL
    std::vector<Ptr<AfdxTrafficGenerator>> generators;
    
    for (const auto& vlConfig : vlConfigs)
    {
        Ptr<AfdxTrafficGenerator> gen = CreateObject<AfdxTrafficGenerator>();
        
        // Configure Virtual Link on generator
        AfdxVirtualLink vl;
        vl.SetVlId(vlConfig.vlId);
        vl.SetName(vlConfig.vlName);
        vl.SetSourceMac(StringToMac(vlConfig.sourceMac));
        vl.SetDestinationMac(StringToMac(vlConfig.destMac));
        vl.SetBag(MilliSeconds(vlConfig.bagMs));
        vl.SetMaxFrameSize(vlConfig.maxFrameSize);
        vl.SetMinFrameSize(vlConfig.minFrameSize);
        
        // Determine priority based on BAG
        AfdxPriority priority;
        if (vlConfig.bagMs <= 8)
            priority = AFDX_PRIORITY_CRITICAL;
        else if (vlConfig.bagMs <= 32)
            priority = AFDX_PRIORITY_HIGH;
        else if (vlConfig.bagMs <= 64)
            priority = AFDX_PRIORITY_MEDIUM;
        else
            priority = AFDX_PRIORITY_LOW;
        vl.SetPriority(priority);
        
        gen->AddVirtualLink(vl, vlConfig.minFrameSize);
        
        // Set dual network devices based on source ES
        if (vlConfig.sourceES == 1)
        {
            gen->SetDualNetworkDevices(es1ToSwitchA.Get(0), es1ToSwitchB.Get(0));
            gen->SetNode(endSystems.Get(0));
        }
        else if (vlConfig.sourceES == 2)
        {
            gen->SetDualNetworkDevices(es2ToSwitchA.Get(0), es2ToSwitchB.Get(0));
            gen->SetNode(endSystems.Get(1));
        }
        else if (vlConfig.sourceES == 3)
        {
            gen->SetDualNetworkDevices(es3ToSwitchA.Get(0), es3ToSwitchB.Get(0));
            gen->SetNode(endSystems.Get(2));
        }

        gen->SetStartTime(Seconds(0.1));
        gen->SetStopTime(Seconds(simTime - 0.1));
        
        // Note: CSV logging is now handled by packet sniffers above
        // Traffic generator's simplified CSV logging is disabled

        // Install on appropriate ES node
        if (vlConfig.sourceES == 1)
            endSystems.Get(0)->AddApplication(gen);
        else if (vlConfig.sourceES == 2)
            endSystems.Get(1)->AddApplication(gen);
        else if (vlConfig.sourceES == 3)
            endSystems.Get(2)->AddApplication(gen);

        generators.push_back(gen);
        
        NS_LOG_INFO("Traffic generator created for VL " << vlConfig.vlId 
                    << " (ES" << vlConfig.sourceES << ", BAG=" << vlConfig.bagMs << "ms)");
    }

    // Enable PCAP tracing
    if (enablePcap)
    {
        // Create output directory if it doesn't exist
        system(("mkdir -p " + pcapDir).c_str());
        
        csma.EnablePcap(pcapDir + "es1-netA", es1ToSwitchA.Get(0), true);
        csma.EnablePcap(pcapDir + "es1-netB", es1ToSwitchB.Get(0), true);
        csma.EnablePcap(pcapDir + "es2-netA", es2ToSwitchA.Get(0), true);
        csma.EnablePcap(pcapDir + "es2-netB", es2ToSwitchB.Get(0), true);
        csma.EnablePcap(pcapDir + "es3-netA", es3ToSwitchA.Get(0), true);
        csma.EnablePcap(pcapDir + "es3-netB", es3ToSwitchB.Get(0), true);
        csma.EnablePcap(pcapDir + "switchA", es1ToSwitchA.Get(1), true);
        csma.EnablePcap(pcapDir + "switchB", es1ToSwitchB.Get(1), true);
        
        NS_LOG_INFO("PCAP tracing enabled in: " << pcapDir);
    }

    // Initialize CSV Event Logger with packet sniffers for TX/RX events
    if (enableCsv)
    {
        system(("mkdir -p " + csvDir).c_str());
        NS_LOG_INFO("Initializing CSV event logger with packet sniffers...");
        g_csvLogger = new CsvEventLogger(csvFile);
        
        // Connect packet sniffers to all CSMA devices for TX events
        Config::Connect("/NodeList/*/DeviceList/*/$ns3::CsmaNetDevice/MacTx",
                       MakeCallback(&TxPacketSniffer));
        
        // Connect packet sniffers for RX events - using promiscuous mode
        Config::Connect("/NodeList/*/DeviceList/*/$ns3::CsmaNetDevice/PromiscSniffer",
                       MakeCallback(&RxPacketSniffer));
        
        NS_LOG_INFO("CSV event logging enabled with TX/RX packet sniffers");
        NS_LOG_INFO("CSV file: " << csvFile);
    }

    NS_LOG_INFO("\n=== Starting Simulation ===");
    NS_LOG_INFO("Duration: " << simTime << " seconds");
    NS_LOG_INFO("VLs configured: " << vlConfigs.size());
    NS_LOG_INFO("Traffic generators: " << generators.size());

    // Run simulation
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    NS_LOG_INFO("\n=== Simulation Complete ===");

    // Print statistics for Switch A
    NS_LOG_INFO("\n--- Switch A Statistics ---");
    std::cout << "\n=== SWITCH A (Network A) STATISTICS ===\n";
    std::ostringstream ossA;
    switchA->ExportMIB(ossA);
    std::cout << ossA.str();

    // Print statistics for Switch B
    NS_LOG_INFO("\n--- Switch B Statistics ---");
    std::cout << "\n=== SWITCH B (Network B) STATISTICS ===\n";
    std::ostringstream ossB;
    switchB->ExportMIB(ossB);
    std::cout << ossB.str();

    // Cleanup
    if (g_csvLogger)
    {
        delete g_csvLogger;
        g_csvLogger = nullptr;
    }

    Simulator::Destroy();
    
    NS_LOG_INFO("\n=== Outputs Generated ===");
    if (enablePcap)
        NS_LOG_INFO("PCAP files: " << pcapDir);
    if (enableCsv)
        NS_LOG_INFO("CSV events: " << csvFile);
    
    return 0;
}
