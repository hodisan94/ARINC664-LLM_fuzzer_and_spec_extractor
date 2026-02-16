# ============================================================================
# AFDX (ARINC 664 Part 7) Implementation
# Main demonstration simulation and test suites
# ============================================================================

# Main AFDX Demo - Comprehensive demonstration simulation
# - Star topology with 3 End Systems and 2 redundant switches
# - Reads virtual link configuration from CSV
# - Generates PCAP traces and CSV event logs
# - Demonstrates full AFDX protocol with redundancy
build_example(
  NAME afdx-demo
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

# AFDX Sending End System Test (Frame structure and transmission tests)
build_example(
  NAME afdx-sending-es-test
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

# AFDX Switch Test (ARINC 664 Part 7 switch functionality tests)
build_example(
  NAME afdx-switch-test
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

# AFDX Receiving End System Test (Network-level validation tests)
build_example(
  NAME afdx-receiving-es-test
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
