#!/usr/bin/env python3
"""
AI-Driven AFDX Fuzzer Agent

This agent uses an LLM (GPT-5) to intelligently guide fuzzing decisions
based on historical experiment results. It reads meta.csv, analyzes patterns,
and proposes optimal mutation configurations to maximize network stress testing.

Usage:
    export OPENAI_API_KEY=your_key_here
    python3 tools/ai_fuzzer_agent.py

Author: AI Fuzzing Research Team
"""

import os
import sys
import json
import subprocess
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# OpenAI import with graceful fallback
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  Warning: openai package not installed. Install with: pip install openai")


def _as_int(val, default: int = 0) -> int:
    """Safe int conversion: handles NaN/''/None and numeric strings/floats."""
    import math
    try:
        if val is None:
            return default
        if isinstance(val, float) and (math.isnan(val)):  # pandas NaN is float('nan')
            return default
        if isinstance(val, str) and val.strip() == "":
            return default
        return int(float(val))
    except Exception:
        return default


def _prob_bin(p: float, step: float = 0.05) -> float:
    """Bin probability for novelty scoring."""
    try:
        return round(float(p) / step) * step
    except Exception:
        return 0.0


# ============================================================================
# CONFIGURATION
# ============================================================================

ROOT_DIR = Path.home() / "ns-3-reset" / "ns-3"
META_CSV = ROOT_DIR / "experiments" / "meta.csv"
SIMULATOR_BIN = ROOT_DIR / "build" / "examples" / "AFDX_V3" / "ns3-dev-afdx-demo-debug"
MUTATIONS_JSON = ROOT_DIR / "examples" / "AFDX_V3" / "mutations.json"
AI_RUNS_DIR = ROOT_DIR / "experiments" / "ai_runs"
AI_DECISIONS_LOG = ROOT_DIR / "ai_decisions.jsonl"

# ============================================================================
# FUZZING PARAMETER RANGES - EXTREME MODE
# ============================================================================

# Valid VL ranges per AFDX specification
VALID_VL_RANGE = [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]

# Invalid VLs for edge case testing (should be rejected by switch)
INVALID_VL_RANGE = [9999, 5000, 4095, 0, 100, 65535]

# Probability ranges
PROBABILITY_NORMAL = (0.10, 0.30)     # Conservative testing
PROBABILITY_EXTREME = (0.35, 0.50)    # Stress testing (may cause high drops)
PROBABILITY_MAX = 0.50                # Maximum allowed probability

# Mutation types
MUTATION_TYPES = ["bitflip"]

# Multi-VL exploration parameters
EPSILON_GREEDY = 0.2  # 20% random exploration, 80% exploit best VL
INVALID_VL_PROBABILITY = 0.30  # 30% chance to try invalid VL (edge case testing)

# Payload mutation ranges
PAYLOAD_DELTA_NORMAL = [-64, -32, -16, 0, +16, +32, +64]
PAYLOAD_DELTA_EXTREME = [-128, -64, 0, +64, +128, +200]
PAYLOAD_DELTA_OPTIONS = PAYLOAD_DELTA_NORMAL + PAYLOAD_DELTA_EXTREME  # Combined

# Timing jitter ranges
TIMING_JITTER_NORMAL = [0, 2, 4, 8, 12, 16]
TIMING_JITTER_EXTREME = [20, 30, 50, 100, 150]
TIMING_JITTER_OPTIONS = TIMING_JITTER_NORMAL + TIMING_JITTER_EXTREME  # Combined

# MAC address mutation types (NEW!)
MAC_MUTATION_TYPES = [
    "none",           # Normal (no MAC change)
    "spoof_src",      # Spoof source MAC (random)
    "spoof_dst",      # Spoof destination MAC (random multicast)
    "broadcast",      # Set dst to FF:FF:FF:FF:FF:FF
    "invalid_src",    # Set src to multicast (protocol violation!)
    "zero_mac",       # Set src/dst to 00:00:00:00:00:00
]

# Safety thresholds
MAX_CONSECUTIVE_CRASHES = 5  # Log crashes but continue (don't stop)

# LLM Configuration
LLM_MODEL = "gpt-5"  # GPT-5 - Latest model (August 2025)
LLM_TEMPERATURE = 1.0  # GPT-5 only supports temperature=1.0

# Reward Function Weights
REWARD_W_SWITCH_DROP = 1.0     # encourage invalid-VL drops at the switch (disruption)
REWARD_W_FORWARD     = -0.5    # penalize frames actually forwarded
REWARD_W_NOVELTY     = 0.2     # weak preference for exploring new (vl,prob) bins


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def check_prerequisites() -> bool:
    """
    Check if all required files and configurations exist.
    
    Returns:
        bool: True if all checks pass, False otherwise
    """
    issues = []
    
    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        issues.append("❌ OPENAI_API_KEY environment variable not set")
        print("   Set it with: export OPENAI_API_KEY=sk-...")
    
    # Check if OpenAI package is available
    if not OPENAI_AVAILABLE:
        issues.append("❌ openai package not installed")
        print("   Install with: pip install openai")
    
    # Check meta.csv exists
    if not META_CSV.exists():
        issues.append(f"❌ meta.csv not found at {META_CSV}")
    
    # Check simulator binary exists
    if not SIMULATOR_BIN.exists():
        issues.append(f"❌ Simulator binary not found at {SIMULATOR_BIN}")
    
    if issues:
        print("\n⚠️  Prerequisites check failed:")
        for issue in issues:
            print(f"   {issue}")
        return False
    
    print("✅ All prerequisites satisfied")
    return True


def load_meta() -> pd.DataFrame:
    """
    Load and clean the experiments metadata CSV.
    
    Returns:
        pd.DataFrame: Cleaned metadata with parsed timestamps
    """
    print(f"\n📊 Loading metadata from {META_CSV}")
    
    df = pd.read_csv(META_CSV)
    
    # Ensure expected columns exist (older meta.csv may miss some)
    for col, is_int in [
        ("frames_received", True),
        ("frames_forwarded", True),
        ("frames_dropped", True),
        ("frames_dropped_invalid_vl", True),
        ("vl", True),
        ("probability", False),
    ]:
        if col not in df.columns:
            df[col] = 0
        # Coerce to numeric and fill NaNs with 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        if is_int:
            df[col] = df[col].astype(int)
    
    # Ensure reward column exists (backward compatible)
    if "reward" not in df.columns:
        df["reward"] = 0.0
    else:
        df["reward"] = pd.to_numeric(df["reward"], errors="coerce").fillna(0.0)
    
    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True, errors='coerce')
    
    # Drop duplicates (keep last)
    original_len = len(df)
    df = df.drop_duplicates(subset=['run_id'], keep='last')
    removed = original_len - len(df)
    
    if removed > 0:
        print(f"   Removed {removed} duplicate entries")
    
    # Sort by timestamp
    df = df.sort_values('timestamp')
    
    print(f"   Loaded {len(df)} experiment records")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df


def analyze_vl_stats(df: pd.DataFrame) -> Dict:
    """
    Analyze statistics per Virtual Link.
    
    Args:
        df: Experiments metadata DataFrame
        
    Returns:
        Dict: Statistics per VL including avg drops, success rate, etc.
    """
    vl_stats = {}
    
    for vl in VALID_VL_RANGE:
        vl_data = df[df['vl'] == vl]
        
        if len(vl_data) == 0:
            vl_stats[vl] = {
                "experiments_count": 0,
                "avg_frames_dropped": 0,
                "avg_frames_invalid": 0,
                "max_drops": 0,
                "avg_probability": 0
            }
            continue
        
        vl_stats[vl] = {
            "experiments_count": len(vl_data),
            "avg_frames_dropped": float(vl_data['frames_dropped'].mean()),
            "avg_frames_invalid": float(vl_data['frames_dropped_invalid_vl'].mean()),
            "max_drops": int(vl_data['frames_dropped'].max()),
            "avg_probability": float(vl_data['probability'].mean()),
            "last_probability": float(vl_data.iloc[-1]['probability']) if len(vl_data) > 0 else 0,
            "last_drops": int(vl_data.iloc[-1]['frames_dropped']) if len(vl_data) > 0 else 0
        }
    
    return vl_stats


def get_recent_results(df: pd.DataFrame, n: int = 10) -> List[Dict]:
    """
    Get the N most recent experiment results.
    
    Args:
        df: Experiments metadata DataFrame
        n: Number of recent results to return
        
    Returns:
        List of dicts with recent experiment info
    """
    recent = df.tail(n)
    
    results = []
    for _, row in recent.iterrows():
        results.append({
            "run_id": row.get("run_id", ""),
            "vl": _as_int(row.get("vl")),
            "probability": float(row.get("probability", 0.0)),
            "frames_received": _as_int(row.get("frames_received")),
            "frames_dropped": _as_int(row.get("frames_dropped")),
            "frames_dropped_invalid_vl": _as_int(row.get("frames_dropped_invalid_vl")),
            "timestamp": row.get("timestamp").isoformat() if hasattr(row.get("timestamp"), "isoformat") else str(row.get("timestamp", "")),
        })
    
    return results


def _novelty_score(df: pd.DataFrame, vl: int, prob: float) -> float:
    """
    Compute novelty score based on how often we've tested this (vl, prob) combo.
    
    Args:
        df: Historical experiments DataFrame
        vl: Virtual Link ID
        prob: Probability value
        
    Returns:
        float: Novelty score [0..1], higher = less explored
    """
    if df is None or df.empty:
        return 1.0
    
    prob_b = _prob_bin(prob)
    # Count how many times we ran this (vl, prob_bin)
    mask = (df.get("vl", 0) == int(vl)) & (df.get("probability", 0.0).round(2) == round(prob_b, 2))
    freq = int(mask.sum())
    # Map frequency to [0..1], fewer repeats => higher novelty
    # freq==0 -> 1.0, freq>=5 -> ~0.0 (softly)
    return max(0.0, 1.0 - min(freq, 5) / 5.0)


def _compute_novelty_v2(df: pd.DataFrame, vl: int, prob: float, 
                        payload_delta: int = 0, timing_jitter: int = 0, k: int = 10) -> float:
    """
    Novelty score v2: unseen combo of (vl, probability, payload_delta, timing_jitter) in last K runs.
    
    Args:
        df: Historical runs
        vl: VL ID
        prob: Probability
        payload_delta: Payload delta bytes
        timing_jitter: Timing jitter ms
        k: Look-back window (default 10)
        
    Returns:
        float: 0.3 if unseen in last K, else 0.0
    """
    if df is None or df.empty:
        return 0.3
    
    # Last K runs
    recent = df.tail(k)
    
    # Check for exact match
    prob_rounded = round(prob, 2)
    for _, row in recent.iterrows():
        if (int(row.get("vl", 0)) == vl and
            round(float(row.get("probability", 0.0)), 2) == prob_rounded and
            int(row.get("payload_delta_bytes", 0)) == payload_delta and
            int(row.get("timing_jitter_ms", 0)) == timing_jitter):
            return 0.0  # Seen recently
    
    return 0.3  # Novel


def _compute_repeat_penalty(df: pd.DataFrame, vl: int, prob: float,
                            payload_delta: int = 0, timing_jitter: int = 0, k: int = 5) -> float:
    """
    Repeat penalty: exact repeat within last K runs.
    
    Args:
        df: Historical runs
        vl: VL ID
        prob: Probability
        payload_delta: Payload delta bytes
        timing_jitter: Timing jitter ms
        k: Look-back window (default 5)
        
    Returns:
        float: 0.5 if exact repeat in last K, else 0.0
    """
    if df is None or df.empty:
        return 0.0
    
    # Last K runs
    recent = df.tail(k)
    
    # Check for exact match
    prob_rounded = round(prob, 2)
    for _, row in recent.iterrows():
        if (int(row.get("vl", 0)) == vl and
            round(float(row.get("probability", 0.0)), 2) == prob_rounded and
            int(row.get("payload_delta_bytes", 0)) == payload_delta and
            int(row.get("timing_jitter_ms", 0)) == timing_jitter):
            return 0.5  # Exact repeat
    
    return 0.0  # No repeat


def compute_reward(metrics: dict, df_history: pd.DataFrame, vl: int, prob: float,
                   payload_delta: int = 0, timing_jitter: int = 0, 
                   mac_mutation: str = "none", is_extreme_test: bool = False) -> dict:
    """
    Compute reward v3 for a fuzzing run - EXTREME MODE with edge case awareness.
    
    Reward components:
    - policing_ratio: Frames dropped by policing (legitimate stress)
    - forward_ratio: Frames successfully forwarded
    - invalid_ratio: Frames dropped due to invalid VL
    - novelty_score: Exploration bonus
    - repeat_penalty: Discourage immediate repeats
    - edge_case_bonus: Reward for finding protocol violations (NEW!)
    - safety_reward: System handled extreme input gracefully (NEW!)
    
    Args:
        metrics: Current run metrics
        df_history: Historical experiments DataFrame
        vl: Virtual Link ID
        prob: Probability value
        payload_delta: Payload delta bytes
        timing_jitter: Timing jitter ms
        mac_mutation: MAC mutation type (NEW!)
        is_extreme_test: Flag if this is an extreme/edge case test (NEW!)
        
    Returns:
        dict: Reward components and total reward
    """
    # Extract metrics
    received = int(metrics.get("frames_received", 0) or 0)
    forwarded = int(metrics.get("frames_forwarded", 0) or 0)
    invalid = int(metrics.get("frames_dropped_invalid_vl", 0) or 0)
    mac_spoof_count = int(metrics.get("mac_spoof_count", 0) or 0)
    simulation_timeout = metrics.get("simulation_timeout", False)
    
    # Compute policing drops (what remains after accounting for invalid and forwarded)
    policing = max(received - forwarded - invalid, 0)
    
    denom = max(received, 1)
    forward_ratio = forwarded / denom
    invalid_ratio = invalid / denom
    policing_ratio = policing / denom
    
    # Compute novelty and repeat penalty
    novelty_score = _compute_novelty_v2(df_history, vl, prob, payload_delta, timing_jitter, k=10)
    repeat_penalty = _compute_repeat_penalty(df_history, vl, prob, payload_delta, timing_jitter, k=5)
    
    # Initialize bonuses
    edge_case_bonus = 0.0
    safety_reward = 0.0
    vulnerability_detected = False
    
    # CRASH PENALTY: Simulation timed out or crashed
    if simulation_timeout:
        reward = -10.0
        print("   💀 CRASH DETECTED: Simulation timeout!")
        return {
            "reward": float(reward),
            "forward_ratio": float(forward_ratio),
            "policing_ratio": float(policing_ratio),
            "invalid_ratio": float(invalid_ratio),
            "novelty": float(novelty_score),
            "repeat_penalty": float(repeat_penalty),
            "edge_case_bonus": 0.0,
            "safety_reward": 0.0,
            "crash_detected": True,
            "vulnerability_detected": False,
            "is_extreme_test": is_extreme_test,
            "switch_drop_ratio": float(invalid_ratio),  # Legacy
        }
    
    # EDGE CASE TESTING: Invalid VL or MAC spoofing
    if is_extreme_test:
        if invalid_ratio > 0.5:
            # Switch correctly rejected most invalid frames!
            edge_case_bonus = 0.8
            print(f"   ✅ Edge case handled correctly: {invalid_ratio*100:.1f}% frames rejected")
        elif invalid_ratio > 0.0 and invalid_ratio <= 0.5:
            # Partial rejection - interesting behavior
            edge_case_bonus = 0.5
            print(f"   ⚠️  Partial rejection: {invalid_ratio*100:.1f}% frames rejected")
        elif forwarded > 0:
            # VULNERABILITY: Invalid frames got through!
            edge_case_bonus = 1.0
            vulnerability_detected = True
            print(f"   🚨 POTENTIAL VULNERABILITY: {forwarded} invalid frames forwarded!")
        
        # Safety reward: System didn't crash despite extreme input
        if not simulation_timeout:
            safety_reward = 0.3
            print("   🛡️  System stability: No crash despite extreme input")
    
    # Base reward calculation
    if invalid_ratio > 0 and not is_extreme_test:
        # Invalid VL in normal testing - penalize heavily
        reward = -1.0 - 5.0 * invalid_ratio
    else:
        # Reward v3 formula
        reward = (
            + 0.6 * policing_ratio     # Encourage protocol policing (legit stress)
            - 0.2 * forward_ratio      # Slight penalty to high forwarding
            + 0.4 * novelty_score      # Exploration bonus
            - 0.2 * repeat_penalty     # Discourage immediate repeats
            + edge_case_bonus          # Edge case detection bonus (NEW!)
            + safety_reward            # System stability bonus (NEW!)
        )
        # Clamp to [-1.0, 2.0] (increased max for edge case bonuses)
        reward = max(-1.0, min(2.0, reward))
    
    return {
        "reward": float(reward),
        "forward_ratio": float(forward_ratio),
        "policing_ratio": float(policing_ratio),
        "invalid_ratio": float(invalid_ratio),
        "novelty": float(novelty_score),
        "repeat_penalty": float(repeat_penalty),
        "edge_case_bonus": float(edge_case_bonus),
        "safety_reward": float(safety_reward),
        "crash_detected": False,

        
        "vulnerability_detected": vulnerability_detected,
        "is_extreme_test": is_extreme_test,
        # Legacy fields for backward compatibility
        "switch_drop_ratio": float(invalid_ratio),
    }


def query_llm(vl_stats: Dict, recent_results: List[Dict], client: OpenAI) -> Optional[Dict]:
    """
    Query the LLM for next fuzzing decision.
    
    Args:
        vl_stats: Statistics per VL
        recent_results: Recent experiment results
        client: OpenAI client instance
        
    Returns:
        Dict with LLM decision or None if failed
    """
    system_prompt = """You are an AGGRESSIVE AFDX Fuzzer Agent in EXTREME MODE.

Your mission is to STRESS-TEST the AFDX network by finding EDGE CASES, PROTOCOL VIOLATIONS, 
and SYSTEM LIMITS. You are NOT just testing normal operation - you are actively trying to 
break the system and discover vulnerabilities.

🎯 PRIMARY OBJECTIVES:
1. **Find Protocol Violations:** Test invalid VLs, MAC spoofing, extreme payloads
2. **Maximize Network Stress:** Push probability up to 0.50 to stress switch buffers
3. **Discover Edge Cases:** Explore parameter combinations that cause interesting behavior
4. **Test System Resilience:** Try to crash the simulation (but track what causes crashes)
5. **Identify Vulnerabilities:** Look for cases where invalid frames get forwarded

📊 TESTING STRATEGIES (choose based on recent results):

**Normal Testing (30% of time):**
- Use VALID VLs: [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
- Probability: 0.10-0.30
- MAC mutation: "none"
- Goal: Establish baseline and find legitimate stress patterns

**Edge Case Testing (50% of time):**
- Use INVALID VLs: [9999, 5000, 4095, 0, 100, 65535]
- Probability: 0.25-0.45
- MAC mutation: "spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac"
- Goal: Test switch's rejection of invalid frames and find vulnerabilities

**Attack Simulation (20% of time):**
- Use any VL (valid or invalid)
- Probability: 0.40-0.50 (extreme stress!)
- Extreme payload deltas: ±128 to ±200 bytes
- Extreme timing jitter: 50-150ms
- MAC: invalid_src, zero_mac (protocol violations)
- Goal: Try to overwhelm or crash the system and find edge cases

🔥 DECISION RULES:
- If last 5 runs were all VALID VLs → try INVALID VL next (MANDATORY)
- If switch correctly dropped invalid frames (invalid_ratio > 0.5) → increase attack intensity
- If invalid frames got forwarded (forwarded > 0 with invalid VL) → FOCUS on that VL (potential vulnerability!)
- If simulation crashed in last run → back off slightly (but still be aggressive)
- If reward is stagnant → try more extreme parameters
- **PRIORITY**: If any VL has < 5 runs → test it immediately with edge case params
- Prioritize extreme parameter combinations (prob > 0.4, payload ±128+, jitter > 50ms)

⚠️ SAFETY CONSTRAINTS:
- Max probability: 0.50 (prevent complete saturation)
- If 5+ consecutive crashes detected → temporarily use normal parameters
- Track crash-prone configurations and vary approach

📊 PARAMETER DETAILS:
- **payload_delta_bytes**: Change in payload size (-200 to +200 bytes)
  * 0 = no change (safe)
  * ±32, ±64 = moderate mutations
  * ±128, ±200 = extreme mutations (may violate size limits)
- **timing_jitter_ms**: Timing variation in milliseconds (0-150ms)
  * 0 = no jitter (safe)
  * 10-20 = moderate jitter
  * 50-150 = extreme jitter (may cause timing violations)

Always respond with valid JSON matching this schema:
{
  "target_vl": <int, 0-65535, both valid and INVALID VLs allowed>,
  "probability": <float, range 0.10-0.50>,
  "mutation_type": "bitflip",
  "payload_delta_bytes": <int, range -200 to +200, choose based on test strategy>,
  "timing_jitter_ms": <int, range 0 to 150, choose based on test strategy>,
  "mac_mutation": <str, one of ["none", "spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac"]>,
  "is_extreme_test": <bool, true if using invalid VL or extreme parameters>,
  "reasoning": "<explain strategy: normal/edge-case/attack, which VL, why, and WHY you chose these specific payload/timing values>"
}"""

    # Identify under-tested VLs (< 5 runs)
    under_tested_vls = []
    all_vls = VALID_VL_RANGE + INVALID_VL_RANGE
    for vl in all_vls:
        if vl in vl_stats and vl_stats[vl]['experiments_count'] < 5:
            under_tested_vls.append(vl)
        elif vl not in vl_stats:
            under_tested_vls.append(vl)  # Never tested
    
    user_prompt = {
        "current_summary": {
            "vl_stats": vl_stats,
            "recent_results": recent_results,
            "under_tested_vls": under_tested_vls  # NEW!
        },
        "goal": "Propose an AGGRESSIVE mutation configuration that stress-tests the AFDX network. Try to find edge cases, protocol violations, and system limits. PRIORITIZE under-tested VLs!",
        "constraints": {
            "valid_vl_range": VALID_VL_RANGE,
            "invalid_vl_range": INVALID_VL_RANGE,
            "probability_range": [0.10, PROBABILITY_MAX],
            "mutation_types": MUTATION_TYPES,
            "mac_mutation_types": MAC_MUTATION_TYPES
        },
        "fuzzing_modes": {
            "normal": "30% - Valid VLs, moderate probability (0.10-0.30)",
            "edge_case": "50% - Invalid VLs, MAC spoofing, probability (0.25-0.45)",
            "attack": "20% - Extreme stress, probability up to 0.50"
        },
        "priority_message": f"🚨 UNDER-TESTED VLs: {under_tested_vls} - These VLs have < 5 runs. Test them with edge case parameters!" if under_tested_vls else ""
    }
    
    print("\n🤖 Querying LLM for next fuzzing decision...")
    print(f"   Model: {LLM_MODEL}")
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, indent=2)}
            ],
            temperature=LLM_TEMPERATURE,
            response_format={"type": "json_object"}
        )
        
        decision_text = response.choices[0].message.content
        decision = json.loads(decision_text)
        
        # Validate decision
        if not validate_decision(decision):
            print("   ⚠️  LLM returned invalid decision, using fallback")
            return None
        
        return decision
        
    except Exception as e:
        print(f"   ❌ Error querying LLM: {e}")
        return None


def validate_decision(decision: Dict) -> bool:
    """
    Validate that LLM decision meets constraints (EXTREME MODE - relaxed validation).
    
    Args:
        decision: LLM decision dict
        
    Returns:
        bool: True if valid
    """
    required_keys = ["target_vl", "probability", "mutation_type", "payload_delta_bytes", "timing_jitter_ms", "reasoning"]
    
    if not all(key in decision for key in required_keys):
        print(f"   ⚠️  Missing required keys: {[k for k in required_keys if k not in decision]}")
        return False
    
    # Validate VL (allow ANY VL 0-65535 for extreme testing!)
    vl = decision["target_vl"]
    if not isinstance(vl, int) or vl < 0 or vl > 65535:
        print(f"   ⚠️  Invalid VL: {vl} (must be 0-65535)")
        return False
    
    # Validate probability (0.10 - 0.50 for extreme mode)
    prob = decision["probability"]
    if not (0.10 <= prob <= PROBABILITY_MAX):
        print(f"   ⚠️  Invalid probability: {prob} (must be 0.10-{PROBABILITY_MAX})")
        return False
    
    # Validate mutation type
    if decision["mutation_type"] not in MUTATION_TYPES:
        print(f"   ⚠️  Invalid mutation type: {decision['mutation_type']}")
        return False
    
    # Validate payload_delta_bytes (-200 to +200)
    payload_delta = decision["payload_delta_bytes"]
    if not isinstance(payload_delta, int) or payload_delta < -200 or payload_delta > 200:
        print(f"   ⚠️  Invalid payload_delta_bytes: {payload_delta} (must be -200 to +200)")
        return False
    
    # Validate timing_jitter_ms (0 to 150)
    timing_jitter = decision["timing_jitter_ms"]
    if not isinstance(timing_jitter, int) or timing_jitter < 0 or timing_jitter > 150:
        print(f"   ⚠️  Invalid timing_jitter_ms: {timing_jitter} (must be 0 to 150)")
        return False
    
    # Validate MAC mutation (optional field, default to "none")
    if "mac_mutation" in decision:
        if decision["mac_mutation"] not in MAC_MUTATION_TYPES:
            print(f"   ⚠️  Invalid MAC mutation: {decision['mac_mutation']}")
            return False
    
    # Auto-detect if this is an extreme test
    if "is_extreme_test" not in decision:
        # Auto-set based on VL, MAC mutation, or extreme parameters
        is_invalid_vl = vl not in VALID_VL_RANGE
        has_mac_mutation = decision.get("mac_mutation", "none") != "none"
        has_extreme_payload = abs(payload_delta) >= 128
        has_extreme_jitter = timing_jitter >= 50
        decision["is_extreme_test"] = is_invalid_vl or has_mac_mutation or has_extreme_payload or has_extreme_jitter
    
    return True


def generate_mutations(decision: Dict) -> None:
    """
    Generate mutations.json file based on LLM decision (EXTREME MODE).
    
    Args:
        decision: LLM decision dict (includes payload, timing, MAC mutation, extreme flag)
    """
    mac_mutation = decision.get("mac_mutation", "none")
    is_extreme = decision.get("is_extreme_test", False)
    
    mutations = {
        "round": 0,
        "timestamp": int(datetime.now().timestamp()),
        "mutations": [
            {
                "vlId": decision["target_vl"],
                "op": decision["mutation_type"],
                "prob": decision["probability"],
                "payload_delta_bytes": decision.get("payload_delta_bytes", 0),
                "timing_jitter_ms": decision.get("timing_jitter_ms", 0),
                "mac_mutation": mac_mutation,
                "is_extreme_test": is_extreme,
                "notes": f"AI-guided EXTREME: {decision['reasoning']}"
            }
        ]
    }
    
    print(f"\n📝 Writing mutations to {MUTATIONS_JSON}")
    print(f"   🎯 Mode: {'🔥 EXTREME' if is_extreme else '✅ NORMAL'}")
    print(f"   VL={decision['target_vl']} {'(INVALID!)' if decision['target_vl'] not in VALID_VL_RANGE else ''}, "
          f"prob={decision['probability']:.2f}")
    print(f"   LLM-chosen payload delta={decision.get('payload_delta_bytes', 0)} bytes, "
          f"timing jitter={decision.get('timing_jitter_ms', 0)} ms")
    if mac_mutation != "none":
        print(f"   🚨 MAC Mutation: {mac_mutation}")
    
    with open(MUTATIONS_JSON, 'w') as f:
        json.dump(mutations, f, indent=2)
    
    print(f"   ✅ Mutations file created")


def run_simulation() -> Tuple[bool, str]:
    """
    Run the AFDX simulator.
    
    Returns:
        Tuple of (success: bool, log_output: str)
    """
    print(f"\n▶️  Running simulator: {SIMULATOR_BIN.name}")
    print("   This will take ~2 seconds...")
    
    try:
        result = subprocess.run(
            [str(SIMULATOR_BIN)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("   ✅ Simulation completed successfully")
            return True, result.stdout + result.stderr
        else:
            print(f"   ❌ Simulation failed with exit code {result.returncode}")
            return False, result.stdout + result.stderr
            
    except subprocess.TimeoutExpired:
        print("   ❌ Simulation timed out")
        return False, "Simulation timeout"
    except Exception as e:
        print(f"   ❌ Error running simulation: {e}")
        return False, str(e)


def extract_metrics_from_log(log_text: str, simulation_timeout: bool = False) -> Dict:
    """
    Extract metrics from simulation log output (EXTREME MODE - includes crash tracking).
    
    Args:
        log_text: Full log output from simulator
        simulation_timeout: Flag if simulation timed out
        
    Returns:
        Dict with extracted metrics
    """
    metrics = {
        "frames_received": 0,
        "frames_forwarded": 0,
        "frames_dropped": 0,
        "frames_dropped_invalid_vl": 0,
        "payload_applied_bytes": None,
        "jitter_applied_ms": None,
        "payload_clamp_count": 0,
        "tx_prob_drops": 0,
        "mac_spoof_count": 0,
        "simulation_timeout": simulation_timeout
    }
    
    # Parse log for metric lines
    for line in log_text.split('\n'):
        if "afdxFramesReceived.0 =" in line:
            metrics["frames_received"] = int(line.split('=')[1].strip())
        elif "afdxFramesForwarded.0 =" in line:
            metrics["frames_forwarded"] = int(line.split('=')[1].strip())
        elif "afdxFramesDropped.0 =" in line:
            metrics["frames_dropped"] = int(line.split('=')[1].strip())
        elif "afdxFramesDroppedInvalidVL.0 =" in line:
            metrics["frames_dropped_invalid_vl"] = int(line.split('=')[1].strip())
        # Parse mutation application metrics (from C++ simulation)
        elif "AfdxMutation.payloadAppliedBytes =" in line:
            try:
                metrics["payload_applied_bytes"] = int(line.split('=')[1].strip())
            except:
                pass
        elif "AfdxMutation.jitterAppliedMs =" in line:
            try:
                metrics["jitter_applied_ms"] = int(line.split('=')[1].strip())
            except:
                pass
        elif "AfdxMutation.payloadClampCount =" in line:
            try:
                metrics["payload_clamp_count"] = int(line.split('=')[1].strip())
            except:
                pass
        elif "AfdxMutation.txProbDrops =" in line:
            try:
                metrics["tx_prob_drops"] = int(line.split('=')[1].strip())
            except:
                pass
        elif "AfdxMutation.macSpoofCount =" in line:
            try:
                metrics["mac_spoof_count"] = int(line.split('=')[1].strip())
            except:
                pass
    
    return metrics


def save_ai_run(decision: Dict, log_output: str, metrics: Dict) -> str:
    """
    Save AI-guided run results to dedicated directory.
    
    Args:
        decision: LLM decision
        log_output: Simulator log output
        metrics: Extracted metrics
        
    Returns:
        str: Run ID
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"ai_run_vl{decision['target_vl']}_p{decision['probability']:.2f}_{timestamp}"
    run_dir = AI_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Save log
    log_file = run_dir / "simulation.log"
    with open(log_file, 'w') as f:
        f.write(log_output)
    
    # Save decision
    decision_file = run_dir / "decision.json"
    with open(decision_file, 'w') as f:
        json.dump(decision, f, indent=2)
    
    # Save metrics
    metrics_file = run_dir / "metrics.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # Copy output if exists
    output_src = ROOT_DIR / "examples" / "AFDX_V3" / "output"
    if output_src.exists():
        import shutil
        output_dst = run_dir / "output"
        if output_dst.exists():
            shutil.rmtree(output_dst)
        shutil.copytree(output_src, output_dst)
    
    print(f"\n💾 Saved AI run to: {run_dir}")
    return run_id


def update_meta(run_id: str, decision: Dict, metrics: Dict) -> None:
    """
    Append new AI-guided run to meta.csv (EXTREME MODE - includes edge case tracking).
    
    Args:
        run_id: Unique run identifier
        decision: LLM decision
        metrics: Extracted metrics
    """
    csv_file = AI_RUNS_DIR / run_id / "output" / "csv" / "AFDX-LOG-OUTPUT.csv"
    pcap_dir = AI_RUNS_DIR / run_id / "output" / "pcap"
    log_file = AI_RUNS_DIR / run_id / "simulation.log"
    
    new_row = {
        "run_id": run_id,
        "vl": decision["target_vl"],
        "probability": decision["probability"],
        "payload_delta_bytes": decision.get("payload_delta_bytes", 0),
        "timing_jitter_ms": decision.get("timing_jitter_ms", 0),
        "mac_mutation": decision.get("mac_mutation", "none"),
        "is_extreme_test": decision.get("is_extreme_test", False),
        "payload_applied_bytes": metrics.get("payload_applied_bytes"),
        "jitter_applied_ms": metrics.get("jitter_applied_ms"),
        "payload_clamp_count": metrics.get("payload_clamp_count", 0),
        "tx_prob_drops": metrics.get("tx_prob_drops", 0),
        "mac_spoof_count": metrics.get("mac_spoof_count", 0),
        "crash_detected": metrics.get("crash_detected", False),
        "vulnerability_detected": metrics.get("vulnerability_detected", False),
        "seed": 0,  # AI runs don't use seeds
        "timestamp": datetime.now().isoformat(),
        "stdout_log": str(log_file),
        "pcap_dir": str(pcap_dir),
        "csv_file": str(csv_file) if csv_file.exists() else "",
        "frames_received": metrics["frames_received"],
        "frames_forwarded": metrics["frames_forwarded"],
        "frames_dropped": metrics["frames_dropped"],
        "frames_dropped_invalid_vl": metrics["frames_dropped_invalid_vl"],
        "forward_ratio": metrics.get("forward_ratio", 0.0),
        "policing_ratio": metrics.get("policing_ratio", 0.0),
        "invalid_ratio": metrics.get("invalid_ratio", 0.0),
        "edge_case_bonus": metrics.get("edge_case_bonus", 0.0),
        "safety_reward": metrics.get("safety_reward", 0.0),
        "reward": metrics.get("reward", 0.0)
    }
    
    # Append to meta.csv
    df = pd.read_csv(META_CSV)
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(META_CSV, index=False)
    
    print(f"   ✅ Updated {META_CSV}")


def log_ai_decision(decision: Dict, metrics: Dict) -> None:
    """
    Append AI decision and results to decisions log file.
    
    Args:
        decision: LLM decision
        metrics: Extracted metrics (including reward components)
    """
    # Extract reward summary if available
    reward_summary = {}
    if 'reward' in metrics:
        reward_summary = {
            "reward": metrics.get("reward", 0.0),
            "forward_ratio": metrics.get("forward_ratio", 0.0),
            "policing_ratio": metrics.get("policing_ratio", 0.0),
            "invalid_ratio": metrics.get("invalid_ratio", 0.0),
            "novelty": metrics.get("novelty", 0.0),
            "repeat_penalty": metrics.get("repeat_penalty", 0.0),
        }
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "decision": decision,
        "results": metrics,
        "reward_summary": reward_summary
    }
    
    AI_DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    with open(AI_DECISIONS_LOG, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    print(f"   ✅ Logged decision to {AI_DECISIONS_LOG}")


def print_decision(decision: Dict) -> None:
    """
    Pretty-print LLM decision.
    
    Args:
        decision: LLM decision dict
    """
    print("\n" + "="*70)
    print("🤖 AI FUZZING DECISION")
    print("="*70)
    print(f"Target VL:          {decision['target_vl']}")
    print(f"Probability:        {decision['probability']:.3f}")
    print(f"Mutation Type:      {decision['mutation_type']}")
    print(f"Payload Delta:      {decision.get('payload_delta_bytes', 0):+d} bytes")
    print(f"Timing Jitter:      {decision.get('timing_jitter_ms', 0)} ms")
    
    mac_mutation = decision.get('mac_mutation', 'none')
    if mac_mutation != 'none':
        print(f"MAC Mutation:       🚨 {mac_mutation}")
    else:
        print(f"MAC Mutation:       {mac_mutation}")
    
    is_extreme = decision.get('is_extreme_test', False)
    print(f"Test Mode:          {'🔥 EXTREME' if is_extreme else '✅ NORMAL'}")
    
    print(f"\n💭 Reasoning:")
    print(f"   {decision['reasoning']}")
    print("="*70 + "\n")


def print_results(metrics: Dict) -> None:
    """
    Pretty-print simulation results.
    
    Args:
        metrics: Extracted metrics
    """
    print("\n" + "="*70)
    print("📊 SIMULATION RESULTS")
    print("="*70)
    print(f"Frames Received:        {metrics['frames_received']:,}")
    print(f"Frames Forwarded:       {metrics['frames_forwarded']:,}")
    print(f"Frames Dropped:         {metrics['frames_dropped']:,}")
    print(f"Frames Dropped (Inv):   {metrics['frames_dropped_invalid_vl']:,}")
    
    if metrics['frames_received'] > 0:
        drop_rate = (metrics['frames_dropped'] / metrics['frames_received']) * 100
        print(f"\n📉 Drop Rate: {drop_rate:.1f}%")
    
    # Print reward summary if available
    if 'reward' in metrics:
        print(f"\n🎯 REWARD V2 (Policing-Aware)")
        print(f"  ForwardRatio:    {metrics.get('forward_ratio', 0):.3f}")
        print(f"  PolicingRatio:   {metrics.get('policing_ratio', 0):.3f}  ← legit stress")
        print(f"  InvalidRatio:    {metrics.get('invalid_ratio', 0):.3f}  ← penalized")
        print(f"  Novelty:         {metrics.get('novelty', 0):.3f}")
        print(f"  RepeatPenalty:   {metrics.get('repeat_penalty', 0):.3f}")
        print(f"  ==> Reward:      {metrics['reward']:.3f}")
    
    print("="*70 + "\n")


def print_summary(df: pd.DataFrame) -> None:
    """
    Print summary of recent experiments.
    
    Args:
        df: Experiments metadata DataFrame
    """
    recent = df.tail(5)
    
    print("\n" + "="*70)
    print("📋 LAST 5 EXPERIMENTS SUMMARY")
    print("="*70)
    print(f"{'Run ID':<30} {'VL':<6} {'Prob':<7} {'Dropped':<10}")
    print("-"*70)
    
    for _, row in recent.iterrows():
        print(f"{row['run_id']:<30} {_as_int(row['vl']):<6} {float(row['probability']):<7.2f} {_as_int(row['frames_dropped']):<10}")
    
    print("="*70 + "\n")


# ============================================================================
# MAIN AGENT LOOP
# ============================================================================

def main():
    """
    Main AI Fuzzer Agent loop.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='AI-Driven AFDX Fuzzer Agent')
    parser.add_argument('--iters', type=int, default=30,
                        help='Number of AI fuzzing iterations (default: 30)')
    parser.add_argument('--tag', type=str, default=None,
                        help='Optional run tag for identification')
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🚀 AI-DRIVEN AFDX FUZZER AGENT")
    print("="*70)
    print(f"Target iterations: {args.iters}")
    if args.tag:
        print(f"Run tag: {args.tag}")
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Cannot continue without prerequisites. Exiting.")
        sys.exit(1)
    
    # Initialize OpenAI client
    if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  OpenAI not available. Please:")
        print("   1. Install: pip install openai")
        print("   2. Set API key: export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    print(f"✅ OpenAI client initialized (model: {LLM_MODEL})")
    
    # Create output directories
    AI_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Main loop - run N iterations for Multi-VL exploration
    max_iterations = args.iters
    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*70}")
        print(f"🔄 ITERATION {iteration}/{max_iterations}")
        print(f"{'='*70}")
        
        # Load and analyze data
        df = load_meta()
        print_summary(df)
        
        vl_stats = analyze_vl_stats(df)
        recent_results = get_recent_results(df)
        
        # Query LLM (now includes ALL parameters including payload & timing)
        decision = query_llm(vl_stats, recent_results, client)
        
        if decision is None:
            print("\n❌ Failed to get valid decision from LLM. Exiting.")
            break
        
        print_decision(decision)
        
        # Generate mutations
        generate_mutations(decision)
        
        # Run simulation
        success, log_output = run_simulation()
        
        # Track simulation timeout/crash
        simulation_timeout = not success
        
        if not success:
            print("\n💀 Simulation failed/timeout detected!")
            print(f"\nLog output:\n{log_output[:500]}...")
            # DON'T skip - track crash in metrics and continue
        
        # Extract metrics (including timeout flag)
        metrics = extract_metrics_from_log(log_output, simulation_timeout=simulation_timeout)
        
        # Compute reward v3 with EXTREME MODE parameters
        reward_parts = compute_reward(
            metrics, df, 
            decision["target_vl"], 
            decision["probability"],
            payload_delta=decision.get("payload_delta_bytes", 0),
            timing_jitter=decision.get("timing_jitter_ms", 0),
            mac_mutation=decision.get("mac_mutation", "none"),
            is_extreme_test=decision.get("is_extreme_test", False)
        )
        metrics.update(reward_parts)
        
        print_results(metrics)
        
        # Save results
        run_id = save_ai_run(decision, log_output, metrics)
        update_meta(run_id, decision, metrics)
        log_ai_decision(decision, metrics)
        
        print(f"\n✅ Iteration {iteration}/{max_iterations} completed successfully")
    
    print("\n" + "="*70)
    print("🏁 AI FUZZER AGENT FINISHED")
    print("="*70)
    print(f"\n✅ Completed all {max_iterations} AI-guided iterations")
    print(f"Results saved in: {AI_RUNS_DIR}")
    print(f"Decisions log: {AI_DECISIONS_LOG}")
    print(f"Updated meta.csv: {META_CSV}")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

