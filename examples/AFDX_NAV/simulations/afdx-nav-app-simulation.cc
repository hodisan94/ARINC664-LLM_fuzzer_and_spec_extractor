/*
 * AFDX Navigation Application Simulation
 * 
 * This simulation demonstrates AFDX communication for aircraft navigation systems:
 * - GPS Receiver: Generates satellite data and transmits via AFDX
 * - Flight Control System: Receives and validates GPS data
 * 
 * Network Topology:
 * 
 *    GPS_Receiver (ES1)
 *         |       |
 *      [Switch A] [Switch B]    <- Redundant AFDX switches
 *         |       |
 *    Flight_Control (ES2)
 * 
 * Virtual Link Configuration:
 * - VL 100: GPS Navigation Data (GPS -> Flight Control)
 * 
 * Features demonstrated:
 * - Satellite data generation (position, velocity, TOW, fix type)
 * - GPS message encoding for AFDX payload (72 bytes)
 * - CRC-32 integrity checking
 * - GPS data validation (fix type, position bounds, velocity limits)
 * - AFDX dual-network redundancy with First Valid Frame Wins
 * - CSV event logging for analysis
 * 
 * Author: AFDX Development Team
 * Date: 2024
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/csma-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"

// AFDX module includes - using ns3 header path since we link with libafdx
#include "../model/afdx-end-system.h"
#include "../model/afdx-switch.h"
#include "../model/satellite.h"
#include "../model/gps.h"
#include "../model/control-flight.h"

#include <fstream>
#include <sstream>
#include <iomanip>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("AfdxNavAppSimulation");

// ============================================================================
// Global Configuration
// ============================================================================

// Virtual Link ID for GPS navigation data
static const uint16_t GPS_VL_ID = 100;

// GPS update rate (Hz) - typical aviation GPS is 1-10 Hz
static const double GPS_UPDATE_RATE_HZ = 5.0;

// Simulation duration
static const double SIMULATION_DURATION_SEC = 10.0;

// ============================================================================
// CSV Event Logger
// ============================================================================

class NavAppCsvLogger
{
public:
    NavAppCsvLogger(const std::string& filename)
    {
        m_file.open(filename);
        if (m_file.is_open())
        {
            // Write CSV header - Frame info + single Payload column
            m_file << "Timestamp_s,Event,Source,Destination,VL_ID,SeqNum,Network,"
                   << "FrameSize_bytes,PayloadSize_bytes,Payload\n";
            m_file.flush();
        }
    }
    
    ~NavAppCsvLogger()
    {
        if (m_file.is_open())
        {
            m_file.close();
        }
    }
    
    // Helper to format satellite payload as a single string
    std::string FormatSatellitePayload(const SatelliteData& satData, 
                                        const std::string& status,
                                        const std::string& msgId = "-",
                                        const std::string& gpsRxId = "-",
                                        const std::string& gpsTimestamp = "-",
                                        const std::string& crc32 = "-",
                                        const std::string& validationResult = "-")
    {
        std::ostringstream ss;
        ss << std::fixed;
        ss << "Status=" << status << ";";
        ss << "MsgID=" << msgId << ";";
        ss << "GPS_RxID=" << gpsRxId << ";";
        ss << "GPS_Timestamp_ms=" << gpsTimestamp << ";";
        ss << std::setprecision(2);
        ss << "Sat_PosX_m=" << satData.positionX << ";";
        ss << "Sat_PosY_m=" << satData.positionY << ";";
        ss << "Sat_PosZ_m=" << satData.positionZ << ";";
        ss << "Sat_VelX_ms=" << satData.velocityX << ";";
        ss << "Sat_VelY_ms=" << satData.velocityY << ";";
        ss << "Sat_VelZ_ms=" << satData.velocityZ << ";";
        ss << std::setprecision(1);
        ss << "Sat_TOW_s=" << satData.timeOfWeek << ";";
        ss << "Sat_NumSats=" << (int)satData.numSatellites << ";";
        ss << "Sat_FixType=" << (satData.fixType == 2 ? "3D_FIX" : (satData.fixType == 1 ? "2D_FIX" : "NO_FIX")) << ";";
        ss << "CRC32=" << crc32 << ";";
        ss << "ValidationResult=" << validationResult;
        return ss.str();
    }
    
    // Log satellite data generation (Step 1: Satellite -> GPS via function call)
    void LogSatelliteData(double timestamp, const SatelliteData& satData)
    {
        if (!m_file.is_open()) return;
        
        std::string payload = FormatSatellitePayload(satData, "GENERATED");
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << "SAT_DATA_GEN,"      // Event
               << "Satellite,"         // Source
               << "GPS_Receiver,"      // Destination
               << "-,"                 // VL_ID
               << "-,"                 // SeqNum
               << "INTERNAL,"          // Network
               << "-,"                 // FrameSize
               << "58,"                // PayloadSize
               << "\"" << payload << "\"\n";
        m_file.flush();
    }
    
    // Log GPS creates AFDX frame with satellite payload (Step 2: GPS encodes)
    void LogGpsEncode(double timestamp, const GpsMessage& msg)
    {
        if (!m_file.is_open()) return;
        
        std::ostringstream crcSs;
        crcSs << "0x" << std::hex << msg.checksum;
        
        std::string payload = FormatSatellitePayload(
            msg.satelliteData, "ENCODED",
            std::to_string(msg.messageId),
            std::to_string(msg.gpsReceiverId),
            std::to_string(msg.timestampMs),
            crcSs.str());
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << "GPS_ENCODE,"        // Event
               << "GPS_Receiver,"      // Source
               << "-,"                 // Destination
               << "-,"                 // VL_ID
               << "-,"                 // SeqNum
               << "INTERNAL,"          // Network
               << "76,"                // FrameSize
               << "72,"                // PayloadSize
               << "\"" << payload << "\"\n";
        m_file.flush();
    }
    
    // Log GPS transmits AFDX frame (Step 3: GPS -> AFDX Network)
    void LogGpsTx(double timestamp, uint16_t vlId, uint8_t seqNum, 
                  const std::string& network, const GpsMessage& msg)
    {
        if (!m_file.is_open()) return;
        
        std::ostringstream crcSs;
        crcSs << "0x" << std::hex << msg.checksum;
        
        std::string payload = FormatSatellitePayload(
            msg.satelliteData, "SENT",
            std::to_string(msg.messageId),
            std::to_string(msg.gpsReceiverId),
            std::to_string(msg.timestampMs),
            crcSs.str());
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << "AFDX_TX,"           // Event
               << "GPS_Receiver,"      // Source
               << "Flight_Control,"    // Destination
               << vlId << ","
               << (int)seqNum << ","
               << network << ","
               << "76,"                // FrameSize
               << "72,"                // PayloadSize
               << "\"" << payload << "\"\n";
        m_file.flush();
    }
    
    // Log Flight Control receives AFDX frame (Step 4: AFDX Network -> Flight Control)
    void LogFlightControlRx(double timestamp, uint16_t vlId, uint8_t seqNum,
                           const std::string& network, const GpsMessage& msg,
                           const GpsValidationResult& result)
    {
        if (!m_file.is_open()) return;
        
        std::ostringstream crcSs;
        crcSs << "0x" << std::hex << msg.checksum;
        
        std::string payload = FormatSatellitePayload(
            msg.satelliteData, 
            result.isValid ? "VALID" : "INVALID",
            std::to_string(msg.messageId),
            std::to_string(msg.gpsReceiverId),
            std::to_string(msg.timestampMs),
            crcSs.str(),
            result.isValid ? "ALL_CHECKS_PASSED" : result.errorMessage);
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << "AFDX_RX,"           // Event
               << "GPS_Receiver,"      // Source
               << "Flight_Control,"    // Destination
               << vlId << ","
               << (int)seqNum << ","
               << network << ","
               << "76,"                // FrameSize
               << "72,"                // PayloadSize
               << "\"" << payload << "\"\n";
        m_file.flush();
    }
    
    // Log duplicate frame discarded
    void LogDuplicateDiscarded(double timestamp, uint16_t vlId, uint8_t seqNum,
                               const std::string& network)
    {
        if (!m_file.is_open()) return;
        
        m_file << std::fixed << std::setprecision(6) << timestamp << ","
               << "AFDX_DUPLICATE,"    // Event
               << "GPS_Receiver,"      // Source
               << "Flight_Control,"    // Destination
               << vlId << ","
               << (int)seqNum << ","
               << network << ","
               << "76,"                // FrameSize
               << "-,"                 // PayloadSize
               << "\"Status=DISCARDED;ValidationResult=First_Valid_Frame_Wins\"\n";
        m_file.flush();
    }

private:
    std::ofstream m_file;
};

// Global logger pointer
static NavAppCsvLogger* g_csvLogger = nullptr;

// Global pointers for frame forwarding
static Ptr<FlightControlSystem> g_flightControl = nullptr;

// Store the last GPS message for logging
static GpsMessage g_lastGpsMessage;

// ============================================================================
// Satellite Data Callback - Called when satellite generates data (Step 1)
// ============================================================================

void SatelliteDataCallback(const SatelliteData& satData)
{
    if (g_csvLogger)
    {
        g_csvLogger->LogSatelliteData(Simulator::Now().GetSeconds(), satData);
    }
}

// ============================================================================
// GPS Encode Callback - Called when GPS encodes message (Step 2)
// ============================================================================

void GpsEncodeCallback(const GpsMessage& msg)
{
    if (g_csvLogger)
    {
        g_csvLogger->LogGpsEncode(Simulator::Now().GetSeconds(), msg);
    }
}

// ============================================================================
// GPS Transmit Callback - Called when GPS transmits via AFDX (Step 3)
// ============================================================================

void GpsTransmitCallback(const GpsMessage& msg, uint16_t vlId)
{
    // Store for logging
    g_lastGpsMessage = msg;
    
    if (g_csvLogger)
    {
        // Log transmission on Network A
        g_csvLogger->LogGpsTx(Simulator::Now().GetSeconds(), vlId, 1, "NET_A", msg);
        // Log transmission on Network B
        g_csvLogger->LogGpsTx(Simulator::Now().GetSeconds(), vlId, 1, "NET_B", msg);
    }
}

// ============================================================================
// Flight Control Validation Callback - Called after GPS data validation
// ============================================================================

void FlightControlValidationCallback(const GpsMessage& msg, const GpsValidationResult& result)
{
    if (g_csvLogger)
    {
        g_csvLogger->LogFlightControlRx(Simulator::Now().GetSeconds(), 
                                        GPS_VL_ID, msg.messageId & 0xFF,
                                        "FIRST_VALID", msg, result);
    }
}

// ============================================================================
// Frame Forwarding: Simulate switch behavior
// ============================================================================

// This function simulates the switch forwarding GPS frames to Flight Control
void ForwardFrameToFlightControl(Ptr<AfdxEndSystem> gpsSender, 
                                 Ptr<AfdxEndSystem> flightReceiver,
                                 Ptr<FlightControlSystem> flightApp)
{
    // In a real AFDX simulation, the switch would forward frames.
    // Here we simulate this by having the GPS application notify when it sends,
    // and directly processing at the receiver.
    // This is handled through the callback mechanism in our design.
}

// ============================================================================
// Custom Frame Receive Handler
// ============================================================================

// Custom handler that intercepts AFDX frames and forwards GPS data to Flight Control
class GpsFrameForwarder
{
public:
    GpsFrameForwarder(Ptr<FlightControlSystem> flightControl)
        : m_flightControl(flightControl)
    {}
    
    void HandleAfdxEvent(std::string eventType, uint32_t nodeId, std::string nodeName,
                        uint16_t vlId, uint8_t seqNum, std::string networkId,
                        uint32_t payloadSize, std::string status, std::string details)
    {
        // Only process successful frame receptions at the Flight Control node
        if (eventType == "FRAME_RECEIVED" && status == "SUCCESS" && 
            nodeName == "Flight_Control" && vlId == GPS_VL_ID)
        {
            // The frame was successfully received, the FlightControlSystem 
            // will process it through its HandleReceivedFrame method
            NS_LOG_INFO("GPS frame received at Flight Control - VL=" << vlId 
                       << " Seq=" << (int)seqNum);
        }
    }
    
private:
    Ptr<FlightControlSystem> m_flightControl;
};

// ============================================================================
// Main Simulation
// ============================================================================

int main(int argc, char* argv[])
{
    // ========================================================================
    // Command Line Arguments
    // ========================================================================
    
    double simDuration = SIMULATION_DURATION_SEC;
    double gpsRate = GPS_UPDATE_RATE_HZ;
    double fixProbability = 0.90;  // 90% valid GPS fix
    bool verbose = false;
    std::string outputDir = "examples/AFDX/output/pcap/nav-app/";
    
    CommandLine cmd(__FILE__);
    cmd.AddValue("duration", "Simulation duration in seconds", simDuration);
    cmd.AddValue("gpsRate", "GPS update rate in Hz", gpsRate);
    cmd.AddValue("fixProb", "Probability of valid 3D GPS fix (0.0-1.0)", fixProbability);
    cmd.AddValue("verbose", "Enable verbose logging", verbose);
    cmd.AddValue("outputDir", "Output directory for CSV files", outputDir);
    cmd.Parse(argc, argv);
    
    // ========================================================================
    // Logging Configuration
    // ========================================================================
    
    if (verbose)
    {
        LogComponentEnable("AfdxNavAppSimulation", LOG_LEVEL_INFO);
        LogComponentEnable("AfdxEndSystem", LOG_LEVEL_INFO);
        LogComponentEnable("Satellite", LOG_LEVEL_INFO);
        LogComponentEnable("Gps", LOG_LEVEL_INFO);
        LogComponentEnable("ControlFlight", LOG_LEVEL_INFO);
    }
    else
    {
        LogComponentEnable("AfdxNavAppSimulation", LOG_LEVEL_WARN);
    }
    
    NS_LOG_INFO("=======================================================");
    NS_LOG_INFO("AFDX Navigation Application Simulation");
    NS_LOG_INFO("=======================================================");
    NS_LOG_INFO("Duration: " << simDuration << " seconds");
    NS_LOG_INFO("GPS Update Rate: " << gpsRate << " Hz");
    NS_LOG_INFO("GPS Fix Probability: " << fixProbability * 100.0 << "%");
    NS_LOG_INFO("=======================================================");
    
    // ========================================================================
    // Initialize CSV Logger
    // ========================================================================
    
    std::string csvFilename = outputDir + "afdx-nav-app-events.csv";
    g_csvLogger = new NavAppCsvLogger(csvFilename);
    NS_LOG_INFO("CSV logging to: " << csvFilename);
    
    // ========================================================================
    // Create Network Nodes
    // ========================================================================
    
    // Create 2 End System nodes (no separate switch nodes needed for simplified topology)
    NodeContainer endSystems;
    endSystems.Create(2);  // Node 0: GPS, Node 1: Flight Control
    
    // ========================================================================
    // Configure CSMA Channels (100 Mbps AFDX)
    // ========================================================================
    
    CsmaHelper csma;
    csma.SetChannelAttribute("DataRate", DataRateValue(DataRate("100Mbps")));
    csma.SetChannelAttribute("Delay", TimeValue(MicroSeconds(1)));
    
    // For this demonstration, we use a simplified topology where both
    // End Systems are on shared CSMA buses (like a hub-based network).
    // This allows the GPS frames to reach the Flight Control system directly.
    // In a production simulation, you would use proper AFDX switches with
    // VL routing tables for true star topology.
    
    // Network A: GPS and Flight Control on same segment
    NodeContainer networkA;
    networkA.Add(endSystems.Get(0));  // GPS
    networkA.Add(endSystems.Get(1));  // Flight Control
    
    // Network B: GPS and Flight Control on same segment (redundant)
    NodeContainer networkB;
    networkB.Add(endSystems.Get(0));  // GPS
    networkB.Add(endSystems.Get(1));  // Flight Control
    
    // Install CSMA devices - each node gets one device per network
    NetDeviceContainer devicesNetA = csma.Install(networkA);
    NetDeviceContainer devicesNetB = csma.Install(networkB);
    
    // ========================================================================
    // Configure AFDX End Systems
    // ========================================================================
    
    // GPS Receiver End System
    Ptr<AfdxEndSystem> gpsEndSystem = CreateObject<AfdxEndSystem>();
    gpsEndSystem->SetNodeId(0);
    gpsEndSystem->SetName("GPS_Receiver");
    gpsEndSystem->SetNetworkInterfaces(devicesNetA.Get(0), devicesNetB.Get(0));
    gpsEndSystem->AddPublication(GPS_VL_ID);
    
    // Flight Control End System
    Ptr<AfdxEndSystem> fcEndSystem = CreateObject<AfdxEndSystem>();
    fcEndSystem->SetNodeId(1);
    fcEndSystem->SetName("Flight_Control");
    fcEndSystem->SetNetworkInterfaces(devicesNetA.Get(1), devicesNetB.Get(1));
    fcEndSystem->AddSubscription(GPS_VL_ID);
    
    // ========================================================================
    // Network Topology Note
    // ========================================================================
    
    // In this simplified simulation, we use shared CSMA segments to simulate
    // AFDX switch behavior. The GPS and Flight Control systems are on the same
    // Ethernet segment for each network (A and B), allowing frames to be
    // delivered directly via broadcast.
    
    // ========================================================================
    // Create Satellite Data Generator
    // ========================================================================
    
    Ptr<SatelliteDataGenerator> satGenerator = CreateObject<SatelliteDataGenerator>();
    
    // Configure position bounds (aircraft operating area)
    satGenerator->SetPositionBounds(
        -50000.0, 50000.0,    // X: ±50km
        -50000.0, 50000.0,    // Y: ±50km
        1000.0, 12000.0       // Z: 1-12km altitude (typical cruise)
    );
    
    // Configure velocity bounds (typical commercial aircraft)
    satGenerator->SetVelocityBounds(
        -250.0, 250.0,   // Vx: ±250 m/s (~900 km/h)
        -250.0, 250.0,   // Vy: ±250 m/s
        -20.0, 20.0      // Vz: ±20 m/s (climb/descent rate)
    );
    
    // Configure satellite visibility
    satGenerator->SetSatelliteVisibility(4, 12);
    satGenerator->SetFixProbability(fixProbability);
    satGenerator->SetInitialTOW(0.0);  // Start at week beginning
    
    NS_LOG_INFO("Satellite data generator configured");
    
    // ========================================================================
    // Create GPS Receiver Application
    // ========================================================================
    
    Ptr<GpsReceiver> gpsApp = CreateObject<GpsReceiver>();
    gpsApp->SetAfdxEndSystem(gpsEndSystem);
    gpsApp->SetSatelliteGenerator(satGenerator);
    gpsApp->SetReceiverId(1);
    gpsApp->SetVirtualLinkId(GPS_VL_ID);
    gpsApp->SetUpdateInterval(Seconds(1.0 / gpsRate));
    
    // Connect CSV logging callbacks
    // Only log GPS_Receiver -> Flight_Control events (AFDX_TX and AFDX_RX)
    gpsApp->SetTransmitCallback(MakeCallback(&GpsTransmitCallback));
    
    // Install GPS application on first node
    endSystems.Get(0)->AddApplication(gpsApp);
    gpsApp->SetStartTime(Seconds(0.1));
    gpsApp->SetStopTime(Seconds(simDuration - 0.1));
    
    NS_LOG_INFO("GPS Receiver application installed on node 0");
    
    // ========================================================================
    // Create Flight Control System Application
    // ========================================================================
    
    Ptr<FlightControlSystem> flightControlApp = CreateObject<FlightControlSystem>();
    flightControlApp->SetAfdxEndSystem(fcEndSystem);
    flightControlApp->SetSystemId(1);
    flightControlApp->SubscribeToGpsData(GPS_VL_ID);
    
    // Configure validation parameters
    PositionBounds posBounds;
    posBounds.minX = -100000.0; posBounds.maxX = 100000.0;
    posBounds.minY = -100000.0; posBounds.maxY = 100000.0;
    posBounds.minZ = -100.0;    posBounds.maxZ = 20000.0;  // -100m to 20km
    flightControlApp->SetPositionBounds(posBounds);
    
    VelocityLimits velLimits;
    velLimits.maxHorizontal = 350.0;  // ~Mach 1
    velLimits.maxVertical = 50.0;     // 50 m/s vertical
    flightControlApp->SetVelocityLimits(velLimits);
    
    flightControlApp->SetMinimumSatellites(4);
    flightControlApp->SetValidationCallback(MakeCallback(&FlightControlValidationCallback));
    
    // Store global pointer for frame forwarding
    g_flightControl = flightControlApp;
    
    // Install Flight Control application on second node
    endSystems.Get(1)->AddApplication(flightControlApp);
    flightControlApp->SetStartTime(Seconds(0.05));
    flightControlApp->SetStopTime(Seconds(simDuration));
    
    // Connect AFDX End System frame reception to Flight Control System
    fcEndSystem->SetFrameReceiveCallback(
        MakeCallback(&FlightControlSystem::HandleReceivedFrame, flightControlApp));
    
    NS_LOG_INFO("Flight Control System application installed on node 1");
    
    // ========================================================================
    // Setup Frame Forwarding Simulation
    // ========================================================================
    
    // In this simplified simulation, we need to manually forward frames
    // from GPS to Flight Control since we're using basic CSMA without
    // full switch implementation. We'll use a custom callback approach.
    
    // Create a periodic check that simulates frame delivery
    // This is a workaround for the demo - in production, proper AFDX switches
    // would handle the frame forwarding automatically.
    
    // ========================================================================
    // Enable Tracing
    // ========================================================================
    
    // Enable PCAP tracing on the GPS and Flight Control interfaces
    csma.EnablePcap(outputDir + "afdx-nav-gps-netA", devicesNetA.Get(0), true);
    csma.EnablePcap(outputDir + "afdx-nav-gps-netB", devicesNetB.Get(0), true);
    csma.EnablePcap(outputDir + "afdx-nav-fc-netA", devicesNetA.Get(1), true);
    csma.EnablePcap(outputDir + "afdx-nav-fc-netB", devicesNetB.Get(1), true);
    
    NS_LOG_INFO("PCAP tracing enabled");
    
    // ========================================================================
    // Run Simulation
    // ========================================================================
    
    NS_LOG_INFO("Starting simulation...");
    
    Simulator::Stop(Seconds(simDuration));
    Simulator::Run();
    
    // ========================================================================
    // Print Final Statistics
    // ========================================================================
    
    NS_LOG_INFO("\n=======================================================");
    NS_LOG_INFO("SIMULATION COMPLETE");
    NS_LOG_INFO("=======================================================");
    
    std::cout << "\n========================================\n";
    std::cout << "GPS Receiver Statistics\n";
    std::cout << "========================================\n";
    std::cout << "Messages Sent: " << gpsApp->GetMessagesSent() << "\n";
    std::cout << "Final Message ID: " << gpsApp->GetCurrentMessageId() << "\n";
    
    std::cout << "\n";
    flightControlApp->PrintStatistics(std::cout);
    
    std::cout << "\n========================================\n";
    std::cout << "AFDX End System Statistics\n";
    std::cout << "========================================\n";
    std::cout << "GPS ES - Frames Sent: " << gpsEndSystem->GetFramesSent() << "\n";
    std::cout << "FC ES - Frames Received: " << fcEndSystem->GetFramesReceived() << "\n";
    std::cout << "FC ES - Duplicates Discarded: " << fcEndSystem->GetDuplicatesDiscarded() << "\n";
    std::cout << "========================================\n";
    
    // ========================================================================
    // Cleanup
    // ========================================================================
    
    Simulator::Destroy();
    
    delete g_csvLogger;
    g_csvLogger = nullptr;
    g_flightControl = nullptr;
    
    NS_LOG_INFO("Simulation cleanup complete");
    
    return 0;
}
