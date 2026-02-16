"""
Prompts for LLM-based protocol rule extraction from ARINC 664 Part 7.

This implements a two-stage approach:
1. Discovery Phase: Open-ended discovery of ALL protocol elements
2. Structured Extraction Phase: Extract discovered elements in structured JSON
"""

import json

# ============================================================================
# PHASE 1: DISCOVERY (Open-ended exploration)
# ============================================================================

SYSTEM_PROMPT_DISCOVERY = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to perform comprehensive discovery of ALL protocol elements, rules, constraints, and requirements in the given specification text.

DO NOT structure the output yet - just discover and list everything you find.

Focus on discovering:

1. Data Structures & Formats:
   - Frame formats (Ethernet, IP, UDP headers)
   - Field definitions (sizes, offsets, encodings)
   - Virtual Link structures
   - Configuration parameters

2. Numerical Constraints:
   - Size limits (min/max values)
   - Allowed values and ranges
   - Timing constraints (latencies, jitters, BAGs)
   - Rate limits and thresholds

3. Behavioral Rules:
   - Validation rules (what must be checked)
   - Drop conditions (when to discard frames)
   - Forwarding rules (where to send frames)
   - Policing algorithms (rate limiting mechanisms)
   - Sequence number handling
   - Redundancy management policies

4. Protocol Requirements:
   - Mandatory features
   - Optional features
   - Conformance requirements
   - Interoperability requirements

5. Performance & QoS:
   - Priority levels
   - Queue management
   - Buffer management
   - Aging/TTL rules
   - Latency bounds
   - Jitter limits

6. Monitoring & Management:
   - Statistics counters
   - Error detection
   - Fault handling
   - MIB requirements
   - SNMP requirements

7. Security & Validation:
   - Integrity checks (CRC, checksums)
   - Authorization rules
   - Access control

Output Format:
Provide a comprehensive bulleted list of discoveries. For each item, include:
- What the element/rule is
- Specific numerical values (if mentioned)
- Direct quotes from the specification (if important)
- Section references (if visible)

Be thorough - discover EVERYTHING, even if it seems minor!
"""


# ============================================================================
# PHASE 2: STRUCTURED EXTRACTION (Based on discovery)
# ============================================================================

SYSTEM_PROMPT_RULE_EXTRACTION = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to extract protocol rules from specification text in a structured JSON format.

Extract rules in this comprehensive JSON structure:
{
  "bag": {
    "allowed_values_ms": [list of allowed BAG values in milliseconds],
    "constraints": "description of BAG constraints"
  },
  "frame_structure": {
    "ethernet": {
      "lmin": minimum frame length in bytes,
      "lmax": maximum frame length in bytes,
      "dest_mac_offset": offset in bytes,
      "dest_mac_size": size in bytes,
      "src_mac_offset": offset in bytes,
      "src_mac_size": size in bytes,
      "ethertype_offset": offset in bytes,
      "ethertype_value": expected value or null,
      "crc_fcs_required": boolean,
      "multicast_bit_rule": "description of multicast MAC bit 0 rule"
    },
    "ip_header": {
      "version": IP version number,
      "checksum_required": boolean,
      "fragmentation_allowed": boolean,
      "ttl_rules": "description or null",
      "header_validation": ["list of validation checks"]
    },
    "udp_header": {
      "checksum_required": boolean,
      "port_rules": "description or null",
      "length_validation": "description"
    },
    "afdx_fields": {
      "vl_id_offset": offset in bytes,
      "vl_id_size": size in bytes,
      "sequence_num_offset": offset in bytes,
      "sequence_num_size": size in bytes,
      "payload_offset": offset in bytes
    },
    "payload": {
      "min_size": minimum payload size in bytes,
      "max_size": maximum payload size in bytes,
      "vl_specific_ranges": "description or null"
    }
  },
  "virtual_link": {
    "id_range": [min_vl_id, max_vl_id],
    "redundancy_required": boolean,
    "configuration_parameters": ["list of required VL config params"]
  },
  "sequence_numbers": {
    "range": [min_value, max_value],
    "wraparound": boolean,
    "window_size": window size in frames,
    "out_of_window_action": "description",
    "duplicate_detection": "description",
    "missing_frame_detection": "description"
  },
  "filtering_policing": {
    "drop_conditions": ["list of conditions that cause frame drops"],
    "policing_algorithm": "description or null",
    "token_bucket": {
      "size_formula": "formula or description",
      "refill_rate_formula": "formula or description"
    },
    "bag_enforcement": "description"
  },
  "switching": {
    "static_forwarding": {
      "enabled": boolean,
      "port_mapping_rules": "description"
    },
    "forwarding_rules": ["list of forwarding rules"],
    "sequence_handling": ["how sequence numbers are handled"],
    "redundancy_handling": {
      "policy": "accept-first or other",
      "duplicate_discard": "description"
    },
    "split_horizon": "description or null"
  },
  "priority_qos": {
    "priority_levels": ["list of priority levels"],
    "queue_separation": "description",
    "scheduling_algorithm": "description or null"
  },
  "buffer_management": {
    "overflow_policy": "head-drop or other",
    "buffer_size_rules": "description or null",
    "queue_limits": "description or null"
  },
  "frame_aging": {
    "ttl_enabled": boolean,
    "max_age": "value or null",
    "aging_rules": "description",
    "discard_conditions": ["list of aging-related discard conditions"]
  },
  "monitoring": {
    "mib_required": boolean,
    "snmp_required": boolean,
    "fault_detection": "description",
    "update_interval_ms": value or null,
    "discard_counters": {
      "categories": ["list of discard reason categories"],
      "tracking_required": boolean
    },
    "statistics": ["list of required statistics"]
  },
  "redundancy": {
    "network_a_b_architecture": boolean,
    "dual_transmission_required": boolean,
    "accept_first_policy": "description",
    "discard_duplicate_policy": "description"
  },
  "performance": {
    "max_switch_delay_us": maximum switch delay in microseconds,
    "max_end_to_end_latency_ms": maximum latency,
    "max_jitter_fraction": maximum jitter as fraction,
    "link_speed_mbps": link speed in Mbps
  }
}

Important:
- Only extract rules that are explicitly stated in the text
- Use null for values not found in the text
- Be precise with numerical values and units
- Include direct quotes for important constraints
"""


SYSTEM_PROMPT_AGGREGATION = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to aggregate multiple JSON rule extractions into a single, consolidated protocol rules document.

When aggregating:
1. Merge overlapping rules (keep the most specific/complete version)
2. Resolve conflicts (prefer rules from more authoritative sections)
3. Remove duplicates
4. Ensure consistency across all rules
5. Fill in any missing cross-references

Output a single, well-structured JSON document that combines all extracted rules.
Use the same JSON structure as the individual extractions.

If there are conflicts, add a "notes" field explaining the conflict and your resolution.
"""


def get_discovery_user_prompt(chapter_name: str, text_chunk: str, chunk_index: int, total_chunks: int) -> str:
    """
    Generate user prompt for discovery phase (Phase 1).
    
    Args:
        chapter_name: Name of the chapter being processed
        text_chunk: The text to discover rules from
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks in this chapter
    
    Returns:
        Formatted user prompt for discovery
    """
    return f"""Perform comprehensive discovery on this section of ARINC 664 Part 7.

Chapter: {chapter_name}
Chunk: {chunk_index + 1} of {total_chunks}

Text:
{text_chunk}

---

Discover and list ALL protocol elements, rules, constraints, and requirements in the text above.
Be exhaustive - don't miss anything! Include numerical values, constraints, and direct quotes.
"""


def get_extraction_user_prompt(chapter_name: str, text_chunk: str, chunk_index: int, total_chunks: int) -> str:
    """
    Generate user prompt for rule extraction from a text chunk.
    
    Args:
        chapter_name: Name of the chapter being processed
        text_chunk: The text to extract rules from
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks in this chapter
    
    Returns:
        Formatted user prompt
    """
    return f"""Extract protocol rules from this section of ARINC 664 Part 7.

Chapter: {chapter_name}
Chunk: {chunk_index + 1} of {total_chunks}

Text:
{text_chunk}

---

Extract all protocol rules from the above text and return them in the specified JSON format.
Focus on concrete, testable rules (numerical limits, allowed values, constraints, etc.).
"""


def get_aggregation_user_prompt(extracted_rules: list) -> str:
    """
    Generate user prompt for aggregating multiple rule extractions.
    
    Args:
        extracted_rules: List of JSON rule extractions from different chunks
    
    Returns:
        Formatted user prompt
    """
    rules_text = "\n\n---\n\n".join([
        f"Extraction {i+1}:\n{json.dumps(rule, indent=2)}"
        for i, rule in enumerate(extracted_rules)
    ])
    
    return f"""Aggregate the following protocol rule extractions into a single, consolidated JSON document.

{rules_text}

---

Merge these extractions into one complete protocol rules document.
Resolve any conflicts, remove duplicates, and ensure consistency.
Return the final consolidated JSON.
"""
