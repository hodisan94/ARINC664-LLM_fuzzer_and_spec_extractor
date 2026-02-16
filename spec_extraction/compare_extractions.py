#!/usr/bin/env python3
"""
Compare protocol rule extractions from multiple LLM providers.

This script performs semantic comparison between rule extractions to:
1. Identify rules that all models agree on (high confidence)
2. Identify rules with partial agreement (medium confidence)
3. Identify conflicts requiring arbitration (low confidence)

Usage:
    python3 compare_extractions.py --input-dir outputs/multimodel --output comparison_results.json

Output:
    comparison_results.json with:
    - Agreement metrics (Fleiss' Kappa, pairwise agreement)
    - High/Medium/Low confidence rule classifications
    - Specific conflicts requiring arbitration
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class ConfidenceLevel(Enum):
    """Confidence levels based on inter-model agreement."""
    HIGH = "high"        # All models agree
    MEDIUM = "medium"    # Majority agree (2/3)
    LOW = "low"          # Only 1 model, or conflict


@dataclass
class RuleComparison:
    """Comparison result for a single rule."""
    rule_path: str           # e.g., "bag.allowed_values_ms"
    confidence: ConfidenceLevel
    extracted_by: List[str]  # List of provider names
    values: Dict[str, Any]   # Provider -> value mapping
    consensus_value: Any     # Agreed value (or None if conflict)
    conflict_details: str    # Description of conflict (if any)


@dataclass 
class ComparisonSummary:
    """Overall comparison summary."""
    total_rules: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    pairwise_agreement: Dict[str, float]  # "openai_vs_anthropic": 0.85
    fleiss_kappa: float
    providers_compared: List[str]


def flatten_json(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """
    Flatten nested JSON into dot-notation keys.
    
    Example:
        {"a": {"b": 1, "c": [2,3]}} -> {"a.b": 1, "a.c": [2,3]}
    """
    result = {}
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(flatten_json(value, new_key))
            else:
                result[new_key] = value
    else:
        result[prefix] = obj
    
    return result


def normalize_value(value: Any) -> Any:
    """
    Normalize a value for comparison.
    
    - Sort lists
    - Lowercase strings
    - Round floats
    """
    if value is None:
        return None
    elif isinstance(value, list):
        # Sort if all elements are comparable
        try:
            return sorted([normalize_value(v) for v in value])
        except TypeError:
            return [normalize_value(v) for v in value]
    elif isinstance(value, str):
        # Lowercase and strip whitespace
        return value.lower().strip()
    elif isinstance(value, float):
        # Round to avoid floating point comparison issues
        return round(value, 6)
    elif isinstance(value, dict):
        return {k: normalize_value(v) for k, v in value.items()}
    else:
        return value


def values_are_equivalent(val1: Any, val2: Any) -> bool:
    """
    Check if two values are semantically equivalent.
    
    Handles:
    - Direct equality
    - List order differences
    - String case differences
    - Float precision differences
    """
    norm1 = normalize_value(val1)
    norm2 = normalize_value(val2)
    
    # Direct comparison
    if norm1 == norm2:
        return True
    
    # Both are None
    if norm1 is None and norm2 is None:
        return True
    
    # One is None
    if norm1 is None or norm2 is None:
        return False
    
    # String similarity (for textual rules)
    if isinstance(norm1, str) and isinstance(norm2, str):
        # Check if one contains the other (for partial matches)
        if norm1 in norm2 or norm2 in norm1:
            return True
        # Check word overlap
        words1 = set(re.findall(r'\w+', norm1))
        words2 = set(re.findall(r'\w+', norm2))
        if len(words1) > 0 and len(words2) > 0:
            overlap = len(words1 & words2) / len(words1 | words2)
            return overlap > 0.8
    
    # List comparison (order-independent)
    if isinstance(norm1, list) and isinstance(norm2, list):
        if len(norm1) != len(norm2):
            return False
        try:
            return sorted(norm1) == sorted(norm2)
        except TypeError:
            return norm1 == norm2
    
    return False


def calculate_pairwise_agreement(
    extractions: Dict[str, Dict[str, Any]]
) -> Dict[str, float]:
    """
    Calculate pairwise agreement between all provider pairs.
    
    Returns:
        Dictionary of "provider1_vs_provider2": agreement_ratio
    """
    providers = list(extractions.keys())
    agreements = {}
    
    for i, p1 in enumerate(providers):
        for p2 in providers[i+1:]:
            flat1 = flatten_json(extractions[p1])
            flat2 = flatten_json(extractions[p2])
            
            all_keys = set(flat1.keys()) | set(flat2.keys())
            
            if not all_keys:
                agreements[f"{p1}_vs_{p2}"] = 1.0
                continue
            
            matching = 0
            for key in all_keys:
                val1 = flat1.get(key)
                val2 = flat2.get(key)
                
                if values_are_equivalent(val1, val2):
                    matching += 1
            
            agreements[f"{p1}_vs_{p2}"] = matching / len(all_keys)
    
    return agreements


def calculate_fleiss_kappa(
    extractions: Dict[str, Dict[str, Any]]
) -> float:
    """
    Calculate Fleiss' Kappa for multi-rater agreement.
    
    Simplified version that treats each rule as a "subject" and 
    each provider as a "rater" who assigns a category (the value).
    
    Returns:
        Fleiss' Kappa coefficient (-1 to 1, where 1 = perfect agreement)
    """
    providers = list(extractions.keys())
    n_raters = len(providers)
    
    if n_raters < 2:
        return 1.0  # Perfect agreement with one rater
    
    # Flatten all extractions
    flattened = {p: flatten_json(e) for p, e in extractions.items()}
    
    # Get all unique keys
    all_keys = set()
    for flat in flattened.values():
        all_keys.update(flat.keys())
    
    if not all_keys:
        return 1.0
    
    # For each key, count how many raters agree
    agreements = []
    for key in all_keys:
        values = [flattened[p].get(key) for p in providers]
        
        # Count matches for each pair
        pair_matches = 0
        pair_total = 0
        for i in range(len(values)):
            for j in range(i+1, len(values)):
                pair_total += 1
                if values_are_equivalent(values[i], values[j]):
                    pair_matches += 1
        
        if pair_total > 0:
            agreements.append(pair_matches / pair_total)
    
    if not agreements:
        return 1.0
    
    # Average agreement across all keys
    observed_agreement = sum(agreements) / len(agreements)
    
    # Expected agreement by chance (simplified - assume uniform distribution)
    expected_agreement = 1 / n_raters
    
    # Kappa calculation
    if expected_agreement == 1:
        return 1.0
    
    kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)
    return max(-1, min(1, kappa))  # Clamp to [-1, 1]


def compare_rules(
    extractions: Dict[str, Dict[str, Any]]
) -> List[RuleComparison]:
    """
    Compare all rules across providers and classify by confidence.
    
    Args:
        extractions: Dictionary of provider_name -> extracted_rules
    
    Returns:
        List of RuleComparison objects
    """
    providers = list(extractions.keys())
    n_providers = len(providers)
    
    # Flatten all extractions
    flattened = {p: flatten_json(e) for p, e in extractions.items()}
    
    # Get all unique keys
    all_keys = set()
    for flat in flattened.values():
        all_keys.update(flat.keys())
    
    comparisons = []
    
    for key in sorted(all_keys):
        # Collect values from each provider
        values = {}
        for provider in providers:
            if key in flattened[provider]:
                values[provider] = flattened[provider][key]
        
        extracted_by = list(values.keys())
        n_extracted = len(extracted_by)
        
        # Find consensus (most common value)
        value_groups = {}
        for provider, val in values.items():
            norm_val = str(normalize_value(val))
            if norm_val not in value_groups:
                value_groups[norm_val] = {"providers": [], "original": val}
            value_groups[norm_val]["providers"].append(provider)
        
        # Determine confidence level
        if n_extracted == 0:
            continue
        elif n_extracted == 1:
            confidence = ConfidenceLevel.LOW
            consensus = values[extracted_by[0]]
            conflict = f"Only extracted by {extracted_by[0]}"
        elif n_providers >= 3 and n_extracted == n_providers:
            # All providers extracted this rule
            # Check if they all agree
            unique_normalized = set(str(normalize_value(v)) for v in values.values())
            
            if len(unique_normalized) == 1:
                confidence = ConfidenceLevel.HIGH
                consensus = list(values.values())[0]
                conflict = ""
            elif len(unique_normalized) == 2:
                # Find majority
                max_group = max(value_groups.values(), key=lambda x: len(x["providers"]))
                if len(max_group["providers"]) >= 2:
                    confidence = ConfidenceLevel.MEDIUM
                    consensus = max_group["original"]
                    minority = [p for p in providers if p not in max_group["providers"]]
                    conflict = f"Minority opinion from: {', '.join(minority)}"
                else:
                    confidence = ConfidenceLevel.LOW
                    consensus = None
                    conflict = "No majority consensus"
            else:
                confidence = ConfidenceLevel.LOW
                consensus = None
                conflict = "All providers disagree"
        else:
            # Partial extraction or 2 providers
            unique_normalized = set(str(normalize_value(v)) for v in values.values())
            
            if len(unique_normalized) == 1:
                # All who extracted agree
                if n_extracted >= 2:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
                consensus = list(values.values())[0]
                missing = [p for p in providers if p not in extracted_by]
                conflict = f"Not extracted by: {', '.join(missing)}" if missing else ""
            else:
                confidence = ConfidenceLevel.LOW
                consensus = None
                conflict = f"Conflicting values from {', '.join(extracted_by)}"
        
        comparisons.append(RuleComparison(
            rule_path=key,
            confidence=confidence,
            extracted_by=extracted_by,
            values=values,
            consensus_value=consensus,
            conflict_details=conflict
        ))
    
    return comparisons


def generate_comparison_report(
    extractions: Dict[str, Dict[str, Any]],
    output_path: str
) -> Dict[str, Any]:
    """
    Generate comprehensive comparison report.
    
    Args:
        extractions: Dictionary of provider_name -> extracted_rules
        output_path: Path to save JSON report
    
    Returns:
        Report dictionary
    """
    providers = list(extractions.keys())
    
    print("=" * 70)
    print("  MULTI-MODEL EXTRACTION COMPARISON")
    print("=" * 70)
    print(f"  Comparing: {', '.join(providers)}")
    print("=" * 70)
    
    # Compare all rules
    print("\n📊 Analyzing rule agreement...")
    comparisons = compare_rules(extractions)
    
    # Calculate metrics
    print("📈 Calculating agreement metrics...")
    pairwise = calculate_pairwise_agreement(extractions)
    kappa = calculate_fleiss_kappa(extractions)
    
    # Count by confidence level
    high_conf = [c for c in comparisons if c.confidence == ConfidenceLevel.HIGH]
    med_conf = [c for c in comparisons if c.confidence == ConfidenceLevel.MEDIUM]
    low_conf = [c for c in comparisons if c.confidence == ConfidenceLevel.LOW]
    
    summary = ComparisonSummary(
        total_rules=len(comparisons),
        high_confidence=len(high_conf),
        medium_confidence=len(med_conf),
        low_confidence=len(low_conf),
        pairwise_agreement=pairwise,
        fleiss_kappa=kappa,
        providers_compared=providers
    )
    
    # Build report
    report = {
        "summary": asdict(summary),
        "summary_text": {
            "confidence_interpretation": {
                "high": "All models agree - high confidence in correctness",
                "medium": "Majority agrees (2/3) - likely correct, minor variations",
                "low": "Disagreement or single source - needs review/arbitration"
            },
            "kappa_interpretation": interpret_kappa(kappa)
        },
        "rules_by_confidence": {
            "high": [
                {
                    "path": c.rule_path,
                    "value": c.consensus_value,
                    "extracted_by": c.extracted_by
                }
                for c in high_conf
            ],
            "medium": [
                {
                    "path": c.rule_path,
                    "consensus_value": c.consensus_value,
                    "extracted_by": c.extracted_by,
                    "all_values": c.values,
                    "note": c.conflict_details
                }
                for c in med_conf
            ],
            "low": [
                {
                    "path": c.rule_path,
                    "extracted_by": c.extracted_by,
                    "all_values": c.values,
                    "conflict": c.conflict_details
                }
                for c in low_conf
            ]
        },
        "needs_arbitration": [
            {
                "path": c.rule_path,
                "values": c.values,
                "conflict": c.conflict_details
            }
            for c in low_conf
            if len(c.values) > 1  # Only where there's actual disagreement
        ]
    }
    
    # Save report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    # Print summary
    print("\n" + "=" * 70)
    print("  COMPARISON RESULTS")
    print("=" * 70)
    print(f"\n  Total rules analyzed: {len(comparisons)}")
    print(f"\n  📊 Confidence Distribution:")
    print(f"     🟢 High confidence:   {len(high_conf):4d} ({100*len(high_conf)/len(comparisons):.1f}%)")
    print(f"     🟡 Medium confidence: {len(med_conf):4d} ({100*len(med_conf)/len(comparisons):.1f}%)")
    print(f"     🔴 Low confidence:    {len(low_conf):4d} ({100*len(low_conf)/len(comparisons):.1f}%)")
    print(f"\n  📈 Agreement Metrics:")
    for pair, agreement in pairwise.items():
        print(f"     {pair}: {agreement:.1%}")
    print(f"     Fleiss' Kappa: {kappa:.3f} ({interpret_kappa(kappa)})")
    print(f"\n  ⚠️  Needs arbitration: {len(report['needs_arbitration'])} rules")
    print(f"\n  📄 Report saved to: {output_path}")
    print("=" * 70)
    
    return report


def interpret_kappa(kappa: float) -> str:
    """Interpret Kappa coefficient."""
    if kappa < 0:
        return "Less than chance agreement"
    elif kappa < 0.20:
        return "Slight agreement"
    elif kappa < 0.40:
        return "Fair agreement"
    elif kappa < 0.60:
        return "Moderate agreement"
    elif kappa < 0.80:
        return "Substantial agreement"
    else:
        return "Almost perfect agreement"


def load_extractions(input_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Load all extraction files from a directory.
    
    Expects files named: rules_<provider>.json
    """
    extractions = {}
    
    for filename in os.listdir(input_dir):
        if filename.startswith("rules_") and filename.endswith(".json"):
            provider = filename[6:-5]  # Extract provider name
            filepath = os.path.join(input_dir, filename)
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Skip if error
            if "error" in data:
                print(f"  ⚠️  Skipping {provider}: {data['error']}")
                continue
            
            extractions[provider] = data
            print(f"  ✓ Loaded {provider}")
    
    return extractions


def detect_extraction_format(input_dir: str) -> str:
    """
    Detect whether extractions use the legacy flat schema or new open format.
    
    Returns "open" if any file has a "rules" key with a list, otherwise "strict".
    """
    for filename in os.listdir(input_dir):
        if filename.startswith("rules_") and filename.endswith(".json"):
            filepath = os.path.join(input_dir, filename)
            with open(filepath, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict) and "rules" in data and isinstance(data["rules"], list):
                return "open"
    return "strict"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare protocol rule extractions from multiple LLM providers"
    )
    parser.add_argument(
        "--input-dir",
        default="spec_extraction/multimodel_output",
        help="Directory containing rules_*.json files"
    )
    parser.add_argument(
        "--output",
        default="spec_extraction/comparison_results.json",
        help="Output path for comparison report"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # Detect format and route accordingly
    fmt = detect_extraction_format(args.input_dir)
    
    if fmt == "open":
        print(f"\n  Detected OPEN format extractions — using semantic alignment")
        print(f"  Redirecting to align_rules.py...\n")
        from spec_extraction.align_rules import load_open_extractions, align_extractions
        extractions = load_open_extractions(args.input_dir)
        if len(extractions) < 2:
            print(f"\n  Error: Need at least 2 extractions to align")
            print(f"  Found: {list(extractions.keys())}")
            sys.exit(1)
        align_extractions(
            extractions=extractions,
            output_path=args.output.replace("comparison_results", "alignment_results")
        )
    else:
        print(f"\n  Detected STRICT format extractions — using key-based comparison")
        extractions = load_extractions(args.input_dir)
        if len(extractions) < 2:
            print("\n  Error: Need at least 2 extractions to compare")
            print(f"  Found: {list(extractions.keys())}")
            sys.exit(1)
        generate_comparison_report(extractions, args.output)

