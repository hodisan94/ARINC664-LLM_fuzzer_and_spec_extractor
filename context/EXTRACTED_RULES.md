# Extracted Protocol Rules — Full Inventory

## Overview

| Metric | Value |
|--------|-------|
| Total extracted rules (full) | 431 |
| After simulator-relevance filter | **236** |
| Categories | 72 |
| Functional domains | 12 |
| Test cases generated | 1,491 |
| Extraction method | Open Discovery (GPT-4o + Claude Sonnet, LLM judge) |
| Filter method | LLM analysis of simulator implementation |

### Comparison with Previous Extraction (Strict Mode)

| | Strict Mode (old) | Open Discovery (new) |
|---|---|---|
| Rules | ~10 | 236 (filtered) / 431 (total) |
| Categories | 7 hardcoded | 72 LLM-chosen |
| Test cases | 96 | 1,491 |
| Method | LLM fills predefined schema | LLM freely discovers rules |
| Cross-validation | None | GPT + Claude + judge arbiter |
| Duplicates as proof | N/A | ~40-50 rules confirmed by both models |

---

## Domain 1: Frame Structure & Validation (27 rules)

Rules governing Ethernet frame format, sizes, CRC/FCS, and frame-level checks.
The simulator validates every incoming frame through these checks (Receiving ES: 10 tests, Switch: 5 tests).

### Core testable rules

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `frame_size_validation` | [64, 1518] bytes | Send frames outside this range |
| `frame_check_sequence_validation` | CRC must match IEEE 802.3 | Corrupt FCS field |
| `destination_address_validity` | Must correspond to valid VL | Use invalid MAC destination |
| `virtual_link_port_authorization` | VL must be authorized on port | Send VL to unauthorized port |
| `frame_size_maximum_constraint` | L <= Lmax (per VL) | Send frame larger than VL's Lmax |
| `discard_frames_smaller_than_minimum_size` | L >= Smin (per VL) | Send frame smaller than Smin |
| `discard_frames_with_erroneous_mac_destination_address` | 32-bit constant field must be correct | Corrupt constant field in MAC |
| `discard_frames_with_disallowed_vl_id` | VL ID must be in port's allowed list | Send disallowed VL ID |
| `ethernet_frame_alignment_check` | Size must be integral number of octets | Send non-aligned frame |
| `frame_discard_on_validation_failure` | Invalid frames → discard + MIB update | Any validation failure |
| `no_budget_consumption_for_invalid_frames` | Discarded frames don't consume budget | Send invalid frame, check budget unchanged |

### Structural / informational rules

| Rule | Value |
|------|-------|
| `frame_overhead_components` | frame + 12 (IFG) + 7 (preamble) + 1 (SFD) = 84 bytes minimum on wire |
| `ethernet_frame_composition` | MAC header followed by packet |
| `complete_structure_transmission` | Entire static structure must be sent, not just used portion |
| `automatic_padding_for_undersized_messages` | Messages < 18 bytes padded to 18 bytes |

---

## Domain 2: Traffic Policing & Control (24 rules)

BAG enforcement, bandwidth allocation, token bucket policing.
The switch implements token-bucket BAG policing (5 tests) and enhanced policing (5 tests).

### Core testable rules

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `bag_interval_enforcement` | [1, 2, 4, 8, 16, 32, 64, 128] ms | Use non-power-of-2 BAG |
| `bag_value_range` | [1, 128] ms | Use BAG outside range |
| `bag_frame_rate_limit` | Max 1 frame per BAG interval | Send multiple frames within one BAG |
| `byte_based_frame_acceptance` | Accept if AC > S, debit by S | Exceed byte budget |
| `frame_based_frame_acceptance` | Accept if Frame AC > Smax, debit by Smax | Exceed frame budget |
| `maximum_frame_size` | 1518 bytes | Send frame > 1518 |
| `ethernet_frame_size_handling_range` | [64, 1518] bytes | Send frame outside range |
| `maximum_jitter_value_range` | [0, 10] ms | Inject jitter > 10ms |
| `traffic_policing_resolution` | <= 100 μs | Timing precision test |
| `maximum_bandwidth_allocation` | Lmax / T_GAP | Exceed bandwidth allocation |
| `policing_rate_tolerance` | ±10⁻⁴ | Test policing precision boundary |

### Token bucket internals

| Rule | Value |
|------|-------|
| `initial_account_setting` | ACi = Smax × (1 + J_switch / BAG) |
| `account_crediting_rate` | Proportional to Smax, upper limit BAG |
| `frame_size_consistency_for_shared_accounts` | All VLs sharing account must have same Smin, Smax |
| `default_vl_policing_activation` | Policing active by default |

### Traffic shaping / regulation

| Rule | Value |
|------|-------|
| `virtual_link_bandwidth_allocation_formula` | Lmax / TGAP (bps) |
| `exact_bandwidth_regulated_traffic_control` | Limit bandwidth over any arbitrarily small interval |
| `bounded_frame_delivery_distribution` | Bounded arrival, not Poisson |
| `ordinal_integrity_within_virtual_link` | Frame order preserved per VL |

---

## Domain 3: Switching (72 rules)

Switch forwarding, filtering, buffering, priority queuing, frame aging, operational modes.
The switch test suite covers 46 tests across all these areas.

**Note:** This domain has ~40-50 duplicate rules (same rule extracted by both GPT and Claude with different names). This is expected and validates the cross-model extraction.

### Core switching behavior

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `maintain_vl_frame_order` | Frame order must be preserved | Send frames out of order |
| `do_not_modify_fcs` | Switch must not change CRC | Verify CRC unchanged after switch |
| `use_destination_address_for_port_forwarding` | Forward by MAC destination | Test with wrong MAC |
| `discard_frames_on_congestion` | Discard on buffer overflow | Flood switch to cause congestion |
| `discard_frames_on_link_failure` | Discard if output link down | Test with link failure |
| `frame_buffering_requirement` | Buffer complete frames | Send partial frame |
| `minimum_inter_frame_gap` | Minimum IFG enforced | Send back-to-back without gap |
| `frame_sequencing_for_simultaneous_reception` | Simultaneous frames sequenced | Send concurrent frames |

### Priority queuing

| Rule | Value / Constraint |
|------|-------------------|
| `traffic_prioritization_by_mac_address` | [High Priority, Low Priority] |
| `high_priority_transmission_precedence` | High priority sent before low |
| `no_preemption_of_low_priority_frames` | Low priority frame not preempted mid-transmission |
| `vl_priority_classification` | [high, low] |

### Buffer management

| Rule | Value / Constraint |
|------|-------------------|
| `minimum_output_port_buffer_capacity` | >= 512 frames |
| `buffer_priority_balance` | Balanced between high and low priority |
| `low_priority_vl_output_buffer_size` | Configurable per port |
| `high_priority_vl_output_buffer_size` | Configurable per port |

### Switch performance

| Rule | Value |
|------|-------|
| `maximum_vl_support` | 4096 VLs |
| `minimum_interframe_gap` | 12 bytes |
| `maximum_frame_rate_100mbps` | 148,800 frames/sec |
| `technological_latency_limit` | [0, 100] μs |
| `wire_speed_filtering_capability` | Filter at wire speed |
| `wire_speed_relaying_capability` | Relay at wire speed |
| `vl_processing_capacity` | At least 4096 VLs |

### Switch operational modes

| Rule | Description |
|------|-------------|
| `switch_enters_ops_mode_after_initialization` | Normal operational mode |
| `ops_mode_functions` | Frame filtering + policing + switching + monitoring |
| `switch_enters_dl_mode_from_init_mode` | Download mode from init |
| `switch_enters_passive_mode` | Only network management communication |
| `passive_mode_switch_functions_disabled` | All switch functions stopped |
| `quiet_mode_frame_forwarding_prohibition` | No forwarding, no message generation |
| `fault_indicator_state_during_initialization` | Fault state during INIT |

### Switch configuration (per-VL)

| Rule | Description |
|------|-------------|
| `vl_mac_destination_address_identifier` | MAC dest identifies VL |
| `vl_bandwidth_allocation_gap` | BAG per VL |
| `vl_maximum_allowed_jitter` | Max jitter per VL |
| `vl_maximum_ethernet_frame_size` | Smax per VL |
| `vl_minimum_ethernet_frame_size` | Smin per VL |
| `vl_account_sharing_configuration` | Account shared or not |
| `port_maximum_delay_constraint` | Max delay per port |
| `port_operational_state` | [ON, OFF] |

---

## Domain 4: Virtual Links (11 rules)

VL configuration parameters. Fundamental to every simulation.

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `single_source_per_virtual_link` | One ES source per VL | Multiple sources on same VL |
| `maintain_data_ordering` | Data order preserved in TX and RX | Reorder data |
| `dedicated_maximum_bandwidth_per_vl` | Each VL has dedicated max bandwidth | Exceed bandwidth |
| `vl_bandwidth_isolation` | Other VLs unaffected by one VL's usage | Saturate one VL, check others |
| `vl_partition_exclusivity` | VL not shared by multiple source partitions | Share VL between partitions |
| `vl_bandwidth_and_frame_interval_bounds` | Both bandwidth and interval bounded | Unbounded traffic |
| `bandwidth_allocation_for_maximum_message_size` | Bandwidth for max message not usable by others | Use another VL's bandwidth |
| `minimum_frame_size_range_constraint` | [84, 1538] bytes on wire | Frame outside range |
| `default_reception_vl_identifier` | VL(0, position) | Wrong format |
| `default_reception_vl_uniqueness` | One unique reception VL per switch | Duplicate |
| `default_transmission_vl_uniqueness` | VL(1, position) unique per switch | Duplicate |

---

## Domain 5: Redundancy Management (24 rules)

Dual-network architecture, accept-first policy, sequence handling.
Tested by Redundancy Management suite (6 tests) and Sequence Handling suite (7 tests).

### Sequence number handling

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `sequence_number_range` | 0 to 255 | SN outside range |
| `valid_sequence_number_range_for_frame_acceptance` | RSN in [PSN+1, PSN+2] | SN outside window |
| `sequence_number_wrap_around_handling` | PSN=254 → PSN+1=255, PSN+2=1 | Test wraparound boundary |
| `invalid_frame_discard_requirement` | Frames outside SN criteria → discard | Send invalid SN |
| `zero_sequence_number_transmission_condition` | SN=0 only after reset | Send SN=0 without reset |
| `increasing_rsn_order` | Frames forwarded in increasing RSN | Send decreasing RSN |

### Redundancy policy

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `first_valid_wins_policy` | First frame with valid SN accepted | Race condition test |
| `duplicate_frame_discard` | Second frame with same SN discarded | Send duplicate |
| `dual_network_transmission` | Each frame sent on both networks | Send on one only |
| `first_win_redundancy_delivery` | Deliver first received redundant frame | Delay one network |
| `handling_frame_loss` | Accept from redundant network if lost | Drop on one network |
| `skewmax_parameter` | SkewMax per VL from system integrator | Exceed SkewMax |
| `skewmax_exceeded_acceptance` | If SkewMax exceeded, accept next frame regardless | Trigger SkewMax timeout |
| `maximum_time_difference_between_redundant_frames` | Max 0.5 (unit depends on config) | Exceed time difference |

### Redundancy configuration

| Rule | Description |
|------|-------------|
| `per_vl_redundancy_configuration_capability` | Configurable per VL: one or both networks |
| `redundant_vl_single_data_delivery_mode` | RM active → deliver one copy |
| `redundant_vl_dual_data_delivery_mode` | RM not active → deliver both copies |
| `non_redundant_vl_reception_capability` | Non-redundant VL on either interface |
| `redundancy_management_after_integrity_checking` | RM runs after integrity check |
| `copy_frame_loss_due_to_sequencing` | Faster network can cause copy loss |
| `handling_abnormal_frames` | Abnormal frames not forwarded to partition |
| `reset_tolerance` | Reset should not affect RM |

---

## Domain 6: End System Behavior (9 rules)

| Rule | Value / Constraint |
|------|-------------------|
| `full_duplex_ethernet_requirement` | Full-duplex |
| `ethernet_frame_compliance` | IEEE 802.3 compliant |
| `transmission_during_link_failure` | Continue transmitting |
| `wire_speed_capability` | Handle back-to-back frames at wire speed |
| `frame_processing_rate` | Process at full frame rate of medium |
| `maximum_technological_latency_in_transmission` | 0 to 150 μs |
| `maximum_allowed_jitter` | 0 to 500 μs |
| `performance_calculation_formula` | Performance = 100 × (1 / (last_frame_latency - tech_latency + 1)) |
| `performance_measurement_burst_duration` | [1] second |

---

## Domain 7: Timing & Performance (13 rules)

Latency formulas and bounds. These are "knowledge rules" — they define how latency is calculated.
The fuzzer uses them to understand what timing violations to create.

| Rule | Formula / Value |
|------|----------------|
| `total_latency_formula` | L = Ts + Tm + Tr |
| `first_frame_latency_formula` | La = Ts + Tm1 + Tsw + (8×M)/Nbw + Tm2 + Tr |
| `delayed_frame_latency_formula` | Lb = La + Tj |
| `jitter_time_calculation` | Tj = (8×M)/Nbw + Tmin_gap |
| `maximum_latency_for_single_frame` | BAG + Max_jitter + Tech_latency |
| `constant_end_system_latency` | ES latency is constant |
| `transmission_technological_latency_bound` | < 150 μs |
| `maximum_jitter_constraint_formula` | max_jitter ≤ 40 + Σ(Lmax×8)/Nbw |
| `maximum_jitter_absolute_bound` | ≤ 500 μs |
| `timely_delivery_requirement` | Complete data delivered in timely fashion |

---

## Domain 8: QoS & Sub-VL Queuing (11 rules)

| Rule | Value / Constraint |
|------|-------------------|
| `guaranteed_service_characteristics` | Bandwidth and bounded latency guaranteed |
| `fault_isolation_in_switch` | true |
| `maximum_network_transit_delay_guarantee` | Max transit delay must be guaranteed |
| `guaranteed_bandwidth_requirement` | Constant bandwidth at link level |
| `fifo_discipline_requirement` | FIFO |
| `maximum_application_data_size` | 8192 bytes |
| `in_order_fragment_transmission` | In-order |
| `buffer_overflow_frame_discard` | Discard frame + send error indication |
| `maximum_sub_vl_fifo_queues_per_vl` | 4 |
| `sub_vl_round_robin_scheduling` | One frame per BAG in round-robin |
| `sub_vl_fifo_queue_exclusivity` | Sub-VL queue read by only one VL queue |

---

## Domain 9: AFDX Addressing (27 rules)

MAC address format, VL addressing, IP addressing specific to AFDX.

### MAC addressing

| Rule | Value |
|------|-------|
| `mac_destination_address_format` | xxxx xx11 xxxx xxxx ... (group + locally administered) |
| `mac_source_address_format` | 0000 0010 ... (individual + locally administered) |
| `mac_destination_address_lsb_must_be_1` | Group address bit = 1 |
| `mac_source_address_lsb_must_be_0` | Individual address bit = 0 |
| `mac_address_constant_field_format` | 20000 (constant field value) |
| `interface_id_allowed_values` | ["001", "010"] (Network A, Network B) |
| `mac_address_unicast_or_multicast_support` | [unicast, multicast] |

### IP addressing (AFDX-specific)

| Rule | Value |
|------|-------|
| `ip_address_class_a_private_format` | 10.0.0.0/8 |
| `ip_address_class_a_private_format_requirement` | First 8 bits = '00001010' |
| `ip_source_address_identifies_transmitting_partition` | Source IP = transmitting partition |
| `ip_multicast_address_format_requirement` | Class D + constant 12 bits + 16-bit VL ID |

### Address validation

| Rule | Value |
|------|-------|
| `source_address_validation` | Must be single host, not zero/loopback/broadcast/multicast |
| `source_address_ownership_requirement` | Must be own IP, not broadcast/multicast |
| `destination_address_filtering` | Silently discard if not destined for host |
| `domain_id_coding` | [1, 14] |
| `side_id_coding` | [1, 6] |
| `location_id_coding` | [1, 30] |

---

## Domain 10: Sequence Number & Integrity (6 rules)

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `valid_sequence_number_range_for_frame_acceptance` | RSN in [PSN+1, PSN+2] | SN outside window |
| `sequence_number_wrap_around_handling` | Wraparound at 255 → 1 | Test boundary |
| `invalid_frame_discard_requirement` | Invalid SN → discard | Send bad SN |
| `zero_sequence_number_transmission_condition` | SN=0 only after reset | SN=0 without reset |
| `virtual_link_ordinal_integrity_requirement` | Frame order within VL | Reorder frames |
| `ordinal_integrity` | AFDX maintains frame order | Reorder delivery |

---

## Domain 11: Reception & Error Handling (5 rules)

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `buffer_overflow_handling` | Error message + discard frame | Flood receiver |
| `reception_buffer_overflow_handling` | Error to partition + discard | Exceed buffer capacity |
| `sap_port_receiver_buffer_overflow_handling` | Error to partition + discard | Overflow SAP buffer |
| `buffer_overflow_handling_in_transmission` | Error indication + discard | Overflow TX buffer |
| `data_presentation_after_reassembly` | No data until fully reassembled | Send partial fragments |

---

## Domain 12: IP/UDP Validation in Frame (7 rules)

The receiving ES validates IP/UDP headers as part of the frame validation chain.

| Rule | Value / Constraint | Fuzz Strategy |
|------|-------------------|---------------|
| `ipv4_version_requirement` | [4] | Send IPv6 or invalid version |
| `ipv4_total_length_field_range_in_afdx` | [21, 1499] bytes | Send outside range |
| `ipv4_packet_structure_compliance` | Must comply with IPv4 format | Malform header |
| `unique_data_flow_identification` | Identified by UDP port + IP dest + MAC dest + physical connection | Duplicate identifiers |
| `valid_frame_filtering_criteria` | Filter by TCP/UDP + IP + MAC + physical | Send with wrong addresses |
| `default_ttl_value` | 1 | Send TTL != 1 |
| `no_gateway_operation_required` | false (no gateway needed in AFDX) | — |

---

## What Was Excluded (195 rules, 11 domains)

These rules were extracted by the LLMs but filtered out because our ns-3 simulator does not implement them.

| Excluded Domain | Rules | Reason |
|----------------|-------|--------|
| TCP Transport Layer | 39 | No TCP stack in simulator |
| ICMP Messages | 22 | No ICMP implementation |
| Application-Level Ports & SAP | 32 | Above network layer |
| Data Encoding & Application Data | 34 | Payload content, not network behavior |
| IP Fragmentation & Reassembly | 8 | AFDX prohibits fragmentation |
| IP Routing & Options | 13 | AFDX uses static VL forwarding |
| Configuration & Management Plane | 11 | SNMP, ARINC 615A — management functions |
| Physical Layer | 6 | Cannot test by frame injection |
| General / Architectural | 14 | High-level assertions |
| Application Services | 7 | Sampling service, TFTP |
| UDP/Broadcast (above frame) | 9 | Above frame validation level |

---

## Key Takeaway for the Paper

The open discovery extraction produced **236 simulator-relevant rules** across **12 functional domains**, compared to ~10 hardcoded rules in the original strict-mode extraction. Among these:

- **~80-100 are unique, directly testable rules** with specific numeric or behavioral constraints
- **~40-50 are cross-model duplicates**, confirming extraction reliability (both GPT and Claude independently found the same rule)
- **~50-60 are behavioral rules** that guide the LLM fuzzer's strategy without having a single numeric threshold
- **~30-40 are knowledge/formula rules** that help the LLM understand protocol timing and structure

The filtering reduced the full extraction (431 rules) by 45.2%, removing TCP, ICMP, application-layer, and other non-simulatable categories — demonstrating that the LLM extraction is comprehensive (captures the full spec) while the filtering ensures practical relevance to the specific simulator under test.
