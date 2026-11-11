"""
Translation of a predefined test case into simulator mutation parameters.

The simulator only receives the parameters listed in SIM_PARAM_FIELDS; the
frame list built by TestGenerator is not sent. Every fuzzer therefore needs the
same translation from (rule, test-case value) to these parameters. BOOFUZZ,
Random and the LLM fuzzer all use this module.
"""

import csv
import math
from pathlib import Path
from typing import Any, Dict, Optional

SIM_PARAM_FIELDS = (
    "bag_value",
    "frame_size",
    "timing_jitter_ms",
    "mac_mutation_type",
    "prob",
    "sequence_number_override",
    "dest_mac_mutation",
    "vl_id_override",
)

DEST_MAC_VARIANTS = ("corrupt_prefix", "wrong_vl", "zero")

_VL_CSV = Path(__file__).resolve().parents[2] / "examples/AFDX_V3/config/virtual_links.csv"
_vl_source_cache: Optional[Dict[int, int]] = None


def vl_sources() -> Dict[int, int]:
    """VL id -> source end system, from the simulator VL configuration."""
    global _vl_source_cache
    if _vl_source_cache is None:
        _vl_source_cache = {}
        try:
            with open(_VL_CSV) as f:
                for row in csv.reader(line for line in f if line.strip() and not line.startswith("#")):
                    _vl_source_cache[int(row[0])] = int(row[2])
        except (OSError, ValueError, IndexError):
            pass
    return _vl_source_cache


def impersonation_target(target_vl: int, index: int = 0) -> Optional[int]:
    """A configured VL whose source end system differs from the target VL's."""
    sources = vl_sources()
    own = sources.get(target_vl)
    others = sorted(vl for vl, es in sources.items() if es != own)
    return others[index % len(others)] if others else None


def has_sim_params(strategy: Dict[str, Any]) -> bool:
    return any(strategy.get(f) not in (None, "none") for f in SIM_PARAM_FIELDS)


def classify_rule(rule_id: str) -> str:
    """Map a rule id to the simulator mechanism it exercises (keyword matching)."""
    r = rule_id.lower()
    if 'bag' in r or 'bandwidth' in r or 'traffic_shaping' in r:
        return 'bag'
    if any(k in r for k in ('sequence', 'ordinal', 'integrity_check', 'duplicate',
                            'redundancy')):
        return 'sequence_number'
    if any(k in r for k in ('frame', 'ethernet', 'fragment', 'reassembly',
                            'payload', 'data_size', 'mtu', 'overhead')):
        return 'frame_size'
    if any(k in r for k in ('ip', 'ttl', 'routing', 'datagram', 'header')):
        return 'ip_header'
    if any(k in r for k in ('virtual_link', 'vl_', 'switching', 'switch',
                            'forwarding')):
        return 'vl_id'
    if 'priority' in r or 'qos' in r or 'quality' in r:
        return 'priority'
    if any(k in r for k in ('mac', 'address', 'destination', 'source_addr')):
        return 'mac_address'
    if any(k in r for k in ('latency', 'jitter', 'delay', 'timing')):
        return 'bag'
    if any(k in r for k in ('filter', 'policing', 'discard', 'reject')):
        return 'frame_size'
    return 'generic'


MAX_INT_VALUE = 1_000_000


def _as_int(value) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return max(-MAX_INT_VALUE, min(MAX_INT_VALUE, int(value)))


def test_case_to_params(rule_id: str, value: Any, target_vl: int, index: int = 0) -> Dict[str, Any]:
    """Simulator parameters for one test case. `index` selects among variants deterministically."""
    params: Dict[str, Any] = {f: None for f in SIM_PARAM_FIELDS}
    iv = _as_int(value)
    kind = classify_rule(rule_id)

    if kind == 'bag':
        params["bag_value"] = iv if iv is not None else 1
    elif kind == 'frame_size':
        params["frame_size"] = iv if iv is not None else 63
    elif kind == 'sequence_number':
        # Values outside the one-octet field become 255, which is repeated on every
        # frame and fails integrity checking; 0 is a legal reset value.
        params["sequence_number_override"] = iv if iv is not None and 0 <= iv <= 255 else 255
    elif kind == 'mac_address':
        params["mac_mutation_type"] = 'spoof_src'
        params["dest_mac_mutation"] = DEST_MAC_VARIANTS[index % len(DEST_MAC_VARIANTS)]
    elif kind == 'vl_id':
        params["vl_id_override"] = impersonation_target(target_vl, index)
    elif kind in ('ip_header', 'priority'):
        pass
    else:
        cycle = index % 4
        if cycle == 0:
            params["bag_value"] = iv if iv is not None else 1
            params["frame_size"] = 63
        elif cycle == 1:
            params["frame_size"] = iv if iv is not None else 1519
            params["sequence_number_override"] = 255
        elif cycle == 2:
            params["bag_value"] = iv if iv is not None else 0
            params["dest_mac_mutation"] = 'corrupt_prefix'
        else:
            params["frame_size"] = iv if iv is not None else 17
            params["dest_mac_mutation"] = 'wrong_vl'
            params["sequence_number_override"] = 255
    return params
