#!/usr/bin/env python3
"""
Rule Filter for AFDX Simulator Relevance
=========================================

Filters the full extracted rule set (spec_rules.json) down to rules that are
actually testable by our ns-3 AFDX simulator and fuzzer.

The filtering is based on a systematic analysis of the simulator's implemented
features (see examples/AFDX_V3/README.md):

  Simulator implements:
    - Frame structure validation (64-1518 bytes, CRC/FCS, MAC, IP/UDP headers)
    - Virtual Link management (VL ID, BAG 1-128ms, Smin/Smax, priority)
    - Switch: filtering, BAG policing (token bucket), static forwarding,
      priority queuing (4 levels), frame aging, buffer mgmt, discard tracking
    - End System: sending (frame construction, SN, dual network, BAG scheduling)
                  receiving (frame/IP/UDP validation, sequence handling, redundancy)
    - Redundancy: dual network A/B, accept-first, duplicate detection
    - Sequence numbers: 0-255, wraparound, gap detection

  Simulator does NOT implement:
    - TCP transport layer
    - ICMP messages
    - IP fragmentation / reassembly
    - Application-level communication ports / SAP services
    - Data encoding beyond frame structure
    - Configuration management (SNMP, ARINC 615A)
    - Physical layer details (auto-negotiation, etc.)
    - File transfer (TFTP), multihoming, sampling service

Usage:
    python filter_rules.py [--input INPUT] [--output OUTPUT] [--report REPORT]

Output:
    - spec_rules_filtered.json  : filtered rules in same format as input
    - filter_report.json        : statistics and per-category decisions
"""

import argparse
import json
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Category Classification
#
# Each category extracted by the LLMs is mapped to one of:
#   INCLUDE  - rules testable by our AFDX simulator / fuzzer
#   EXCLUDE  - rules outside the simulator's scope
#
# The mapping is organized by DOMAIN (functional area of the simulator).
# ---------------------------------------------------------------------------

RELEVANT_DOMAINS = {
    "Frame Structure & Validation": {
        "description": (
            "Rules about Ethernet frame format, sizes, CRC/FCS, and frame-level "
            "validation. Directly tested by the Sending ES (58 tests) and "
            "Receiving ES (frame integrity suite, 10 tests)."
        ),
        "categories": [
            "Frame Validation",
            "frame_validation",
            "frame_structure",
            "frame_filtering",
            "Frame Filtering",
            "frame_processing",
            "frame_transmission",
            "ethernet_payload",
            "Filtering and Policing",
        ],
    },
    "Traffic Policing & Control": {
        "description": (
            "BAG enforcement, bandwidth allocation, traffic shaping. "
            "Tested by switch BAG policing (token bucket) and enhanced "
            "policing test suites (5+5 tests)."
        ),
        "categories": [
            "Traffic Policing",
            "traffic_policing",
            "Traffic Control",
            "traffic_regulation",
            "traffic_shaping",
            "Policing",
        ],
    },
    "Switching": {
        "description": (
            "Switch forwarding, filtering, buffering, priority queuing, "
            "frame aging, operational modes. Core of the Switch test suite "
            "(46 tests covering validation, authorization, policing, "
            "forwarding, queuing, aging, buffer overflow, discard tracking)."
        ),
        "categories": [
            "Switching",
            "switching",
            "switching_behavior",
            "switching_function",
            "Switch Behavior",
            "Switch Configuration",
            "switch_configuration",
            "switch_buffering",
            "switch_performance",
            "switch_operation",
            "Switch Processing",
            "Switch Port Processing",
            "Switch Specification",
            "Switch Port Configuration",
            "Switch Operating Modes",
            "switch_operating_modes",
            "Switch Operational Modes",
            "switch_operational_modes",
            "Switch Functionality",
        ],
    },
    "Virtual Links": {
        "description": (
            "VL configuration parameters: VL ID, BAG values, Smin/Smax, "
            "priority, MAC addressing derived from VL ID. Fundamental to "
            "every simulation and test."
        ),
        "categories": [
            "Virtual Link",
            "virtual_link",
            "Virtual Link Configuration",
            "virtual_link_configuration",
            "bandwidth_allocation",
        ],
    },
    "Redundancy": {
        "description": (
            "Dual-network architecture, accept-first policy, duplicate "
            "detection, sequence-based redundancy management. Tested by "
            "Redundancy Management suite (6 tests)."
        ),
        "categories": [
            "Redundancy Management",
            "Redundancy",
            "Network Redundancy",
        ],
    },
    "End System Behavior": {
        "description": (
            "End System transmission/reception rules, full-duplex requirement, "
            "performance metrics (latency, jitter bounds, processing rate). "
            "Tested across Sending ES and Receiving ES suites."
        ),
        "categories": [
            "End System Behavior",
            "End System Performance",
        ],
    },
    "Timing & Performance": {
        "description": (
            "Latency bounds, jitter constraints, transmission timing. "
            "The simulator tracks per-VL latency and the fuzzer can "
            "introduce timing violations to test these bounds."
        ),
        "categories": [
            "Latency",
            "latency_calculation",
            "Latency Management",
            "transmission_performance",
            "Jitter",
            "timing_requirements",
        ],
    },
    "QoS & Sub-VL Queuing": {
        "description": (
            "Priority levels, quality of service, sub-VL scheduling and "
            "queue management. The switch implements 4 priority queues "
            "(CRITICAL/HIGH/MEDIUM/LOW) and FIFO discipline."
        ),
        "categories": [
            "Quality of Service",
            "Sub-VL Queue Exclusivity",
            "Sub-VL Queue Management",
            "Sub-VL Scheduling",
            "queuing_service",
        ],
    },
    "AFDX Addressing": {
        "description": (
            "MAC addressing (AFDX multicast format 03:00:00:00:VL_HI:VL_LO), "
            "VL-based addressing, IP addressing format for AFDX (Class A "
            "private 10.0.0.0/8). Validated by the receiving ES."
        ),
        "categories": [
            "Addressing",
            "addressing",
            "MAC Addressing",
            "mac_addressing",
            "mac_constraints",
            "Address Validation",
            "address_validation",
            "IP_Addressing",
        ],
    },
    "Sequence Number & Integrity": {
        "description": (
            "Sequence number range (0-255), wraparound, gap detection, "
            "ordinal integrity within a VL. Tested by sequence handling "
            "suite (7 tests) and integrity checks."
        ),
        "categories": [
            "integrity_checking",
            "data_integrity",
            "Integrity",
        ],
    },
    "Reception & Error Handling": {
        "description": (
            "Frame reception behavior, buffer overflow handling, error "
            "detection and reporting. The receiving ES generates structured "
            "error codes (100-800 range) for every validation failure."
        ),
        "categories": [
            "Reception",
            "Error Handling",
            "error_handling",
        ],
    },
    "IP/UDP Validation (in-frame)": {
        "description": (
            "IP header validation (version, total length, TTL) and UDP "
            "header checks performed by the receiving ES as part of "
            "frame validation. The ES validates IP version=4, "
            "TTL=1 (AFDX default), and UDP port mapping."
        ),
        "categories": [
            "Network Layer",
            "IP_Configuration",
            "IP_Layer_Requirements",
        ],
    },
}

EXCLUDED_DOMAINS = {
    "TCP Transport Layer": {
        "reason": "Simulator has no TCP stack. AFDX uses UDP for data transport.",
        "categories": [
            "TCP Acknowledgment",
            "TCP_Acknowledgment",
            "TCP_Configuration",
            "TCP_Features",
            "TCP_Retransmission",
            "TCP Urgent Data",
            "TCP Window Management",
            "TCP Zero Window Probing",
            "tcp_addressing",
            "tcp_behavior",
            "tcp_connection",
            "tcp_connection_management",
            "tcp_options",
            "tcp_urgent_data",
            "tcp_validation",
            "tcp_windowing",
            "Connection Management",
        ],
    },
    "ICMP Messages": {
        "reason": "Simulator does not implement ICMP. No ICMP generation or processing.",
        "categories": [
            "ICMP",
            "ICMP Behavior",
            "ICMP Handling",
            "ICMP Restrictions",
            "ICMP_Message_Handling",
            "icmp_layer",
            "icmp_restrictions",
        ],
    },
    "Application-Level Ports & SAP": {
        "reason": (
            "Communication ports, SAP services, and port allocation are "
            "application-layer concepts above the AFDX network layer. "
            "The simulator operates at the frame/network level."
        ),
        "categories": [
            "AFDX Communication Ports",
            "Communication Ports",
            "Communication_Ports",
            "End System",
            "Port Allocation",
            "Port Binding",
            "Port Management",
            "Port Configuration",
            "SAP Port",
            "communication",
            "demultiplexing",
            "transport_layer_addressing",
        ],
    },
    "Data Encoding & Application Data": {
        "reason": (
            "Data alignment, encoding, and format rules apply to application "
            "payload content, not to network-level frame behavior."
        ),
        "categories": [
            "Data Alignment",
            "Data Encoding",
            "Data Format",
            "Data Types",
            "Data Transmission",
            "data_validation",
            "Message Structure",
            "message_structure",
            "message_format",
            "message_formatting",
        ],
    },
    "IP Fragmentation & Reassembly": {
        "reason": (
            "AFDX prohibits IP fragmentation in normal operation. "
            "The simulator does not implement fragmentation/reassembly."
        ),
        "categories": [
            "Fragmentation",
            "Fragmentation and Reassembly",
            "Reassembly and Fragmentation",
            "datagram_transmission",
            "datagram_validation",
        ],
    },
    "IP Routing & Options": {
        "reason": (
            "AFDX uses static VL-based forwarding, not IP routing. "
            "TTL management for routing and IP options are not applicable."
        ),
        "categories": [
            "IP Routing",
            "Routing",
            "TTL Management",
            "ttl_handling",
            "Options Processing",
            "Packet Handling",
            "ip_layer",
            "ip_protocol",
        ],
    },
    "Configuration & Management Plane": {
        "reason": (
            "Network configuration management, SNMP monitoring, ARINC 615A "
            "are management-plane functions not exercised by frame-level fuzzing."
        ),
        "categories": [
            "Configuration Management",
            "configuration",
            "configuration_management",
            "Network Configuration",
            "Network_Monitoring",
            "Switch Monitoring",
            "Switch Initialization",
        ],
    },
    "Physical Layer": {
        "reason": (
            "Physical port speed, auto-negotiation, and duplex settings "
            "cannot be tested by injecting frames into the simulator."
        ),
        "categories": [
            "Physical Layer",
            "physical_layer",
            "physical_port_configuration",
        ],
    },
    "General / Architectural": {
        "reason": (
            "High-level architectural assertions (scalability, compliance, "
            "interoperability) are not directly testable constraints."
        ),
        "categories": [
            "Network Compatibility",
            "Network Interoperability",
            "network_architecture",
            "network_behavior",
            "network_hierarchy",
            "Protocol Compliance",
            "protocol_stack",
            "Performance",
            "Reliability",
            "Fault Tolerance",
            "Interface",
            "Multihoming",
            "identification",
        ],
    },
    "Application Services": {
        "reason": (
            "Sampling service, file transfer (TFTP), and similar "
            "application-level services are not part of the AFDX "
            "network simulation."
        ),
        "categories": [
            "sampling_service",
            "file_transfer",
        ],
    },
    "UDP/Broadcast (above frame level)": {
        "reason": (
            "UDP socket behavior and IP broadcast address semantics "
            "are above the frame validation level implemented in the simulator."
        ),
        "categories": [
            "UDP Protocol Behavior",
            "UDP_Protocol",
            "Broadcast",
            "Address Mask Handling",
        ],
    },
}


def _build_include_set():
    """Return set of all category names marked as relevant."""
    cats = set()
    for domain in RELEVANT_DOMAINS.values():
        cats.update(domain["categories"])
    return cats


def _build_exclude_set():
    """Return set of all category names marked as excluded."""
    cats = set()
    for domain in EXCLUDED_DOMAINS.values():
        cats.update(domain["categories"])
    return cats


def filter_rules(rules: dict, verbose: bool = False) -> tuple:
    """
    Filter spec_rules to only categories relevant to the simulator.

    Returns:
        (filtered_rules, report_dict)
    """
    include = _build_include_set()
    exclude = _build_exclude_set()

    filtered = {}
    included_count = 0
    excluded_count = 0
    unmapped_categories = {}

    for category, category_rules in rules.items():
        n = len(category_rules) if isinstance(category_rules, dict) else 1

        if category in include:
            filtered[category] = category_rules
            included_count += n
        elif category in exclude:
            excluded_count += n
        else:
            unmapped_categories[category] = n
            excluded_count += n
            if verbose:
                print(f"  [UNMAPPED] {category} ({n} rules) -> excluded by default")

    domain_breakdown = {}
    for domain_name, domain_info in RELEVANT_DOMAINS.items():
        count = 0
        cats_found = []
        for c in domain_info["categories"]:
            if c in rules:
                n = len(rules[c]) if isinstance(rules[c], dict) else 1
                count += n
                cats_found.append(c)
        domain_breakdown[domain_name] = {
            "rule_count": count,
            "categories": cats_found,
            "description": domain_info["description"],
        }

    exclusion_breakdown = {}
    for domain_name, domain_info in EXCLUDED_DOMAINS.items():
        count = 0
        cats_found = []
        for c in domain_info["categories"]:
            if c in rules:
                n = len(rules[c]) if isinstance(rules[c], dict) else 1
                count += n
                cats_found.append(c)
        if count > 0:
            exclusion_breakdown[domain_name] = {
                "rule_count": count,
                "reason": domain_info["reason"],
                "categories": cats_found,
            }

    report = {
        "filter_timestamp": datetime.now().isoformat(),
        "method": (
            "LLM-based analysis of simulator implementation "
            "(examples/AFDX_V3/README.md) mapped against extracted rule "
            "categories. Categories are grouped into functional domains "
            "matching simulator components: Frame Structure, Switch, "
            "End System, Virtual Links, Redundancy, and Timing."
        ),
        "total_input_rules": sum(
            len(v) if isinstance(v, dict) else 1 for v in rules.values()
        ),
        "total_filtered_rules": included_count,
        "total_excluded_rules": excluded_count,
        "retention_rate": f"{included_count / max(1, included_count + excluded_count) * 100:.1f}%",
        "included_domains": domain_breakdown,
        "excluded_domains": exclusion_breakdown,
        "unmapped_categories": unmapped_categories,
    }

    return filtered, report


def main():
    parser = argparse.ArgumentParser(
        description="Filter extracted rules to simulator-relevant subset"
    )
    parser.add_argument(
        "--input",
        default=str(Path(__file__).parent.parent / "configs" / "spec_rules.json"),
        help="Path to full spec_rules.json",
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).parent.parent / "configs" / "spec_rules_filtered.json"
        ),
        help="Path to write filtered rules",
    )
    parser.add_argument(
        "--report",
        default=str(
            Path(__file__).parent.parent / "configs" / "filter_report.json"
        ),
        help="Path to write filter report",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed output"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("AFDX Rule Filter - Simulator Relevance")
    print("=" * 60)

    with open(args.input) as f:
        rules = json.load(f)

    total_input = sum(len(v) if isinstance(v, dict) else 1 for v in rules.values())
    print(f"\nInput: {args.input}")
    print(f"Total input rules: {total_input}")
    print(f"Total categories:  {len(rules)}")

    filtered, report = filter_rules(rules, verbose=args.verbose)

    total_filtered = sum(
        len(v) if isinstance(v, dict) else 1 for v in filtered.values()
    )

    print(f"\n{'─' * 60}")
    print("INCLUDED DOMAINS (simulator-testable):")
    print(f"{'─' * 60}")
    for domain_name, info in report["included_domains"].items():
        if info["rule_count"] > 0:
            print(f"  {info['rule_count']:3d} rules  │  {domain_name}")

    print(f"\n{'─' * 60}")
    print("EXCLUDED DOMAINS (not testable by this simulator):")
    print(f"{'─' * 60}")
    for domain_name, info in report["excluded_domains"].items():
        print(f"  {info['rule_count']:3d} rules  │  {domain_name}")
        if args.verbose:
            print(f"             └─ {info['reason']}")

    if report["unmapped_categories"]:
        print(f"\n{'─' * 60}")
        print("UNMAPPED (excluded by default):")
        print(f"{'─' * 60}")
        for cat, n in report["unmapped_categories"].items():
            print(f"  {n:3d} rules  │  {cat}")

    print(f"\n{'=' * 60}")
    print(f"RESULT: {total_filtered} / {total_input} rules retained "
          f"({total_filtered / total_input * 100:.1f}%)")
    print(f"{'=' * 60}")

    with open(args.output, "w") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)
    print(f"\nFiltered rules saved to: {args.output}")

    with open(args.report, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Filter report saved to:  {args.report}")


if __name__ == "__main__":
    main()
