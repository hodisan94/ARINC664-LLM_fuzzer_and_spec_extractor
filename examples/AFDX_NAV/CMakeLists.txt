# ============================================================================
# AFDX Navigation Application (AFDX-NAV)
# GPS Receiver and Flight Control System over AFDX network
# ============================================================================

# NAV AFDX Demo
build_example(
  NAME afdx-nav-demo
  SOURCE_FILES
    simulations/afdx-demo.cc
    model/afdx-frame.cc
    model/afdx-virtual-link.cc
    model/afdx-end-system.cc
    model/afdx-switch.cc
    model/afdx-traffic-generator.cc
  LIBRARIES_TO_LINK
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libcsma}
    ${libbridge}
)

# NAV Sending ES Test
build_example(
  NAME afdx-nav-sending-es-test
  SOURCE_FILES
    test/afdx-sending-es-test.cc
    model/afdx-frame.cc
    model/afdx-virtual-link.cc
    model/afdx-end-system.cc
    model/afdx-switch.cc
    model/afdx-traffic-generator.cc
  LIBRARIES_TO_LINK
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libcsma}
    ${libbridge}
)

# NAV Switch Test
build_example(
  NAME afdx-nav-switch-test
  SOURCE_FILES
    test/afdx-switch-test.cc
    model/afdx-frame.cc
    model/afdx-virtual-link.cc
    model/afdx-end-system.cc
    model/afdx-switch.cc
    model/afdx-traffic-generator.cc
  LIBRARIES_TO_LINK
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libcsma}
    ${libbridge}
)

# NAV Receiving ES Test
build_example(
  NAME afdx-nav-receiving-es-test
  SOURCE_FILES
    test/afdx-receiving-es-test.cc
    model/afdx-frame.cc
    model/afdx-virtual-link.cc
    model/afdx-end-system.cc
    model/afdx-switch.cc
    model/afdx-traffic-generator.cc
  LIBRARIES_TO_LINK
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libcsma}
    ${libbridge}
)

# AFDX Navigation Application Simulation
# GPS Receiver + Flight Control over AFDX
build_example(
  NAME afdx-nav-app-simulation
  SOURCE_FILES
    simulations/afdx-nav-app-simulation.cc
    model/satellite.cc
    model/gps.cc
    model/control-flight.cc
    model/afdx-frame.cc
    model/afdx-virtual-link.cc
    model/afdx-end-system.cc
    model/afdx-switch.cc
    model/afdx-traffic-generator.cc
  LIBRARIES_TO_LINK
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libcsma}
    ${libbridge}
)
