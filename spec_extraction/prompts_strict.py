"""
Strict schema prompts for multi-model validation.

These prompts enforce an EXACT JSON structure that all models must follow,
enabling accurate comparison between different LLM extractions.
"""

import json

# The exact schema all models must follow
STRICT_SCHEMA = {
    "bag": {
        "allowed_values_ms": "list of integers: allowed BAG values in milliseconds (e.g., [1, 2, 4, 8, 16, 32, 64, 128])",
        "constraints": "string: description of BAG constraints"
    },
    "frame_structure": {
        "ethernet": {
            "lmin": "integer: minimum frame length in bytes",
            "lmax": "integer: maximum frame length in bytes",
            "smin": "integer or null: minimum frame size",
            "dest_mac_offset": "integer: destination MAC offset in bytes",
            "dest_mac_size": "integer: destination MAC size in bytes",
            "src_mac_offset": "integer: source MAC offset in bytes",
            "src_mac_size": "integer: source MAC size in bytes",
            "ethertype_offset": "integer: ethertype field offset",
            "ethertype_value": "string: expected ethertype value (e.g., '0x800')",
            "crc_fcs_required": "boolean: whether CRC/FCS is required",
            "multicast_bit_rule": "string: rule for multicast bit in MAC address"
        },
        "ip_header": {
            "version": "integer: IP version number (4 or 6)",
            "checksum_required": "boolean: whether checksum verification is required",
            "fragmentation_allowed": "boolean: whether IP fragmentation is allowed",
            "ttl_rules": "string: rules for Time To Live field",
            "header_validation": "list of strings: validation rules for IP header"
        },
        "udp_header": {
            "checksum_required": "boolean: whether UDP checksum is required",
            "port_rules": "string or null: rules for port mapping",
            "length_validation": "string or null: length validation rules"
        },
        "afdx_fields": {
            "vl_id_offset": "integer or null: VL ID field offset",
            "vl_id_size": "integer: VL ID field size in bytes",
            "sequence_num_offset": "integer: sequence number field offset",
            "sequence_num_size": "integer: sequence number field size",
            "payload_offset": "integer: payload start offset"
        },
        "payload": {
            "min_size": "integer: minimum payload size in bytes",
            "max_size": "integer: maximum payload size in bytes",
            "vl_specific_ranges": "string or null: VL-specific size constraints"
        }
    },
    "virtual_link": {
        "id_range": "list of integers: [min_id, max_id] for VL IDs",
        "redundancy_required": "boolean: whether redundancy is required",
        "configuration_parameters": "list of strings: required VL configuration parameters"
    },
    "sequence_numbers": {
        "range": "list of integers: [min_value, max_value] for sequence numbers",
        "wraparound": "boolean: whether wraparound is enabled",
        "window_size": "integer: sequence number window size",
        "out_of_window_action": "string: action for out-of-window frames",
        "missing_frame_detection": "string: how missing frames are detected",
        "handling_rules": "list of strings: sequence number handling rules"
    },
    "filtering_policing": {
        "drop_conditions": "list of strings: conditions that cause frame drops",
        "policing_algorithm": "string: description of policing algorithm",
        "token_bucket": {
            "size_formula": "string or null: token bucket size formula",
            "refill_rate_formula": "string or null: token bucket refill rate"
        },
        "bag_enforcement": "string: how BAG is enforced"
    },
    "switching": {
        "static_forwarding": {
            "enabled": "boolean: whether static forwarding is enabled",
            "port_mapping_rules": "string: port mapping rules description"
        },
        "forwarding_rules": "list of strings: forwarding rules",
        "split_horizon": "string or null: split horizon configuration"
    },
    "priority_qos": {
        "priority_levels": "list of strings: available priority levels (e.g., ['High Priority', 'Low Priority'])",
        "queue_separation": "string: how queues are separated by priority",
        "scheduling_algorithm": "string: scheduling algorithm description"
    },
    "buffer_management": {
        "overflow_policy": "string: policy for buffer overflow (e.g., 'head-drop')",
        "buffer_size_rules": "string: buffer size rules",
        "queue_limits": "list of strings: queue limit specifications"
    },
    "frame_aging": {
        "ttl_enabled": "boolean: whether TTL/aging is enabled",
        "max_age": "string: maximum frame age specification",
        "aging_rules": "string: frame aging rules"
    },
    "monitoring": {
        "mib_required": "boolean: whether MIB is required",
        "snmp_required": "boolean: whether SNMP is required",
        "fault_detection": "string: fault detection description",
        "update_interval_ms": "integer: monitoring update interval in ms",
        "discard_counters": {
            "categories": "list of strings: discard counter categories",
            "tracking_required": "boolean: whether tracking is required"
        },
        "statistics": "list of strings: required statistics"
    },
    "redundancy": {
        "network_a_b_architecture": "boolean: whether Network A/B architecture is used",
        "dual_transmission_required": "boolean: whether dual transmission is required",
        "policy": "string: redundancy policy name (e.g., 'accept-first')",
        "accept_first_policy": "string: accept-first policy description",
        "discard_duplicate_policy": "string: duplicate discard policy"
    },
    "performance": {
        "max_switch_delay_us": "integer: maximum switch delay in microseconds",
        "max_end_to_end_latency_ms": "integer: maximum end-to-end latency in ms",
        "max_jitter_fraction": "float: maximum jitter as fraction (0.0-1.0)",
        "link_speed_mbps": "integer: link speed in Mbps"
    }
}


SYSTEM_PROMPT_STRICT_EXTRACTION = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to extract protocol rules from the specification text into a STRICTLY DEFINED JSON format.

CRITICAL: You MUST use EXACTLY the following JSON structure. Do not add, remove, or rename any fields.
Use null for values not found in the specification. Use the exact field names shown.

REQUIRED JSON STRUCTURE:
{
  "bag": {
    "allowed_values_ms": [list of integers],
    "constraints": "string or null"
  },
  "frame_structure": {
    "ethernet": {
      "lmin": integer or null,
      "lmax": integer or null,
      "smin": integer or null,
      "dest_mac_offset": integer or null,
      "dest_mac_size": integer or null,
      "src_mac_offset": integer or null,
      "src_mac_size": integer or null,
      "ethertype_offset": integer or null,
      "ethertype_value": "string or null",
      "crc_fcs_required": boolean or null,
      "multicast_bit_rule": "string or null"
    },
    "ip_header": {
      "version": integer or null,
      "checksum_required": boolean or null,
      "fragmentation_allowed": boolean or null,
      "ttl_rules": "string or null",
      "header_validation": [list of strings] or []
    },
    "udp_header": {
      "checksum_required": boolean or null,
      "port_rules": "string or null",
      "length_validation": "string or null"
    },
    "afdx_fields": {
      "vl_id_offset": integer or null,
      "vl_id_size": integer or null,
      "sequence_num_offset": integer or null,
      "sequence_num_size": integer or null,
      "payload_offset": integer or null
    },
    "payload": {
      "min_size": integer or null,
      "max_size": integer or null,
      "vl_specific_ranges": "string or null"
    }
  },
  "virtual_link": {
    "id_range": [min, max] or null,
    "redundancy_required": boolean or null,
    "configuration_parameters": [list of strings] or []
  },
  "sequence_numbers": {
    "range": [min, max] or null,
    "wraparound": boolean or null,
    "window_size": integer or null,
    "out_of_window_action": "string or null",
    "missing_frame_detection": "string or null",
    "handling_rules": [list of strings] or []
  },
  "filtering_policing": {
    "drop_conditions": [list of strings] or [],
    "policing_algorithm": "string or null",
    "token_bucket": {
      "size_formula": "string or null",
      "refill_rate_formula": "string or null"
    },
    "bag_enforcement": "string or null"
  },
  "switching": {
    "static_forwarding": {
      "enabled": boolean or null,
      "port_mapping_rules": "string or null"
    },
    "forwarding_rules": [list of strings] or [],
    "split_horizon": "string or null"
  },
  "priority_qos": {
    "priority_levels": [list of strings] or [],
    "queue_separation": "string or null",
    "scheduling_algorithm": "string or null"
  },
  "buffer_management": {
    "overflow_policy": "string or null",
    "buffer_size_rules": "string or null",
    "queue_limits": [list of strings] or []
  },
  "frame_aging": {
    "ttl_enabled": boolean or null,
    "max_age": "string or null",
    "aging_rules": "string or null"
  },
  "monitoring": {
    "mib_required": boolean or null,
    "snmp_required": boolean or null,
    "fault_detection": "string or null",
    "update_interval_ms": integer or null,
    "discard_counters": {
      "categories": [list of strings] or [],
      "tracking_required": boolean or null
    },
    "statistics": [list of strings] or []
  },
  "redundancy": {
    "network_a_b_architecture": boolean or null,
    "dual_transmission_required": boolean or null,
    "policy": "string or null",
    "accept_first_policy": "string or null",
    "discard_duplicate_policy": "string or null"
  },
  "performance": {
    "max_switch_delay_us": integer or null,
    "max_end_to_end_latency_ms": integer or null,
    "max_jitter_fraction": float or null,
    "link_speed_mbps": integer or null
  }
}

RULES:
1. Use ONLY the field names shown above - no additions, no modifications
2. Use null for any value not explicitly stated in the specification
3. Be precise with numerical values - use integers for bytes/ms/us, floats for fractions
4. For lists, extract all relevant items found in the text
5. Include direct quotes from the specification when describing rules
6. DO NOT invent or assume values - only extract what is explicitly stated
"""


def get_strict_extraction_prompt(chapter_name: str, text_chunk: str, chunk_index: int, total_chunks: int) -> str:
    """Generate user prompt for strict schema extraction."""
    return f"""Extract AFDX protocol rules from this section following the EXACT JSON structure specified.

Chapter: {chapter_name}
Chunk: {chunk_index + 1} of {total_chunks}

SPECIFICATION TEXT:
---
{text_chunk}
---

Extract all protocol rules from the text above. 
Use the EXACT field names from the required structure.
Use null for fields not mentioned in this chunk.
Return ONLY valid JSON matching the required structure.
"""


SYSTEM_PROMPT_STRICT_AGGREGATION = """You are aggregating multiple JSON extractions into a single consolidated document.

CRITICAL RULES:
1. The output MUST follow the EXACT same JSON structure as the inputs
2. Merge values from different chunks - combine lists, prefer non-null values over null
3. For conflicting values, prefer the more specific/complete one
4. Do NOT add new fields or change field names
5. Output must be valid JSON matching the strict schema

When merging:
- Lists: Combine all unique items
- Strings: Use the more complete/specific description  
- Numbers: Use the explicitly stated value
- Booleans: Use the explicitly stated value
- null vs value: Use the value
"""


def get_strict_aggregation_prompt(extracted_rules: list) -> str:
    """Generate prompt for aggregating extractions with strict schema."""
    rules_text = "\n\n---\n\n".join([
        f"Extraction {i+1}:\n{json.dumps(rule, indent=2)}"
        for i, rule in enumerate(extracted_rules)
    ])
    
    return f"""Aggregate these extractions into ONE JSON document following the EXACT same structure.

{rules_text}

---

Merge all extractions into a single document.
Combine lists, prefer non-null values, resolve conflicts by choosing the more specific value.
Return ONLY valid JSON matching the strict schema - no extra fields, no missing fields.
"""

