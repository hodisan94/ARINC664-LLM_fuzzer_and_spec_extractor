#!/usr/bin/env python3
"""
Export validated protocol rules from open-discovery alignment results.

This is the export step used by the paper pipeline:
run_multimodel.py -> align_rules.py -> export_validated.py -> filter_rules.py.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _build_clean_rule_entry(rule: Dict[str, Any]) -> Any:
    """Build the fuzzer-facing value for a validated rule."""
    value = rule.get("consensus_value")

    if isinstance(value, (int, float, bool, list)):
        return value

    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
        try:
            return float(value)
        except (ValueError, TypeError):
            pass
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

    provider_values = rule.get("provider_values", {})
    best_value = value
    if best_value is None and provider_values:
        best_value = next(iter(provider_values.values()), None)

    if isinstance(best_value, (int, float, bool, list)):
        return best_value

    return best_value


def _load_original_rules(extraction_dir: Path) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Index original per-provider rules by provider and rule id."""
    original_rules_by_provider: Dict[str, Dict[str, Dict[str, Any]]] = {}

    if not extraction_dir.exists():
        return original_rules_by_provider

    for file_path in extraction_dir.glob("rules_*.json"):
        provider_name = file_path.stem.replace("rules_", "")
        try:
            with open(file_path) as file:
                provider_data = json.load(file)
        except Exception:
            continue

        rule_index = {
            rule.get("id", ""): rule
            for rule in provider_data.get("rules", [])
        }
        original_rules_by_provider[provider_name] = rule_index
        print(f"  Loaded original {provider_name}: {len(rule_index)} rules")

    return original_rules_by_provider


def export_from_alignment(
    alignment_path: str,
    output_dir: str,
    extraction_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Export validated and fuzzer-ready rules from alignment results."""
    print("=" * 70)
    print("  EXPORT VALIDATED RULES (OPEN DISCOVERY)")
    print("=" * 70)

    os.makedirs(output_dir, exist_ok=True)

    with open(alignment_path) as file:
        alignment_data = json.load(file)

    alignment = alignment_data.get("alignment", {})
    metrics = alignment_data.get("metrics", {})
    metadata = alignment_data.get("metadata", {})

    aligned_groups = alignment.get("aligned_groups", [])
    unique_rules = alignment.get("unique_rules", [])
    unique_verified = alignment.get("unique_rules_verified", unique_rules)

    if extraction_dir is None:
        extraction_dir = str(Path(alignment_path).parent / "multimodel_output")
    original_rules_by_provider = _load_original_rules(Path(extraction_dir))

    validated_rules = []
    rule_counter = 0

    for group in aligned_groups:
        rule_counter += 1
        agreement = group.get("agreement", "unknown")
        rule_entry = {
            "id": f"rule_{rule_counter:03d}",
            "name": group.get("canonical_name", f"Rule {rule_counter}"),
            "category": group.get("canonical_category", "unknown"),
            "consensus_value": group.get("consensus_value"),
            "agreement": agreement,
            "confidence": group.get("confidence", "low"),
            "providers": [match.get("provider") for match in group.get("matches", [])],
            "provider_values": {
                match.get("provider"): match.get("constraint_value")
                for match in group.get("matches", [])
            },
        }

        if group.get("conflict_details"):
            rule_entry["conflict_details"] = group["conflict_details"]

        judge_resolution = group.get("judge_resolution")
        if judge_resolution and agreement == "resolved":
            rule_entry["judge_decision"] = judge_resolution.get("resolution")
            rule_entry["judge_justification"] = judge_resolution.get("justification")
            rule_entry["judge_source_quote"] = judge_resolution.get("source_quote")

        validated_rules.append(rule_entry)

    for unique in unique_verified:
        verification = unique.get("verification", "unknown")
        if verification == "rejected":
            continue

        rule_counter += 1
        provider = unique.get("provider", "")
        rule_id = unique.get("rule_id", "")
        original_rule = original_rules_by_provider.get(provider, {}).get(rule_id, {})
        constraint = original_rule.get("constraint", {})
        constraint_value = constraint.get("value") if isinstance(constraint, dict) else None
        corrected_value = unique.get("corrected_value")

        if verification == "confirmed":
            agreement = "unique_confirmed"
            confidence = unique.get("confidence", "low")
            source = "verified_unique"
        else:
            agreement = "unique_unverified"
            confidence = "low"
            source = "unverified_unique"

        validated_rules.append({
            "id": f"rule_{rule_counter:03d}",
            "name": unique.get("name", f"Rule {rule_counter}"),
            "category": unique.get("category", "unknown"),
            "consensus_value": corrected_value if corrected_value is not None else constraint_value,
            "agreement": agreement,
            "confidence": confidence,
            "providers": [provider],
            "source": source,
            "justification": unique.get("justification", ""),
            "data_type": original_rule.get("data_type"),
            "constraint_type": constraint.get("type") if isinstance(constraint, dict) else None,
            "unit": constraint.get("unit") if isinstance(constraint, dict) else None,
            "test_hint": original_rule.get("test_hint"),
            "source_quote": original_rule.get("source_quote", unique.get("source_quote", "")),
        })

    clean_rules: Dict[str, Dict[str, Any]] = {}
    for rule in validated_rules:
        if rule["confidence"] not in ("high", "medium") and rule["agreement"] not in (
            "full",
            "partial",
            "resolved",
            "unique_confirmed",
        ):
            continue

        category = rule["category"]
        clean_rules.setdefault(category, {})
        field_key = rule["name"].lower().replace(" ", "_").replace("-", "_")
        entry = _build_clean_rule_entry(rule)

        if entry is None or isinstance(entry, str):
            enriched = {
                "value": entry,
                "data_type": rule.get("data_type"),
                "unit": rule.get("unit"),
                "test_hint": rule.get("test_hint"),
                "source_quote": (
                    rule.get("source_quote", "")[:200]
                    if rule.get("source_quote")
                    else None
                ),
            }
            enriched = {key: value for key, value in enriched.items() if value is not None}
            if len(enriched) > 1:
                entry = enriched

        clean_rules[category][field_key] = entry

    validated_path = os.path.join(output_dir, "spec_rules_validated.json")
    with open(validated_path, "w") as file:
        json.dump({"rules": validated_rules}, file, indent=2, default=str)
    print(f"  {validated_path}")

    clean_path = os.path.join(output_dir, "spec_rules.json")
    with open(clean_path, "w") as file:
        json.dump(clean_rules, file, indent=2, default=str)
    print(f"  {clean_path}")

    n_high = sum(1 for rule in validated_rules if rule["confidence"] == "high")
    n_medium = sum(1 for rule in validated_rules if rule["confidence"] == "medium")
    n_low = sum(1 for rule in validated_rules if rule["confidence"] == "low")
    total = max(len(validated_rules), 1)

    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "alignment_source": alignment_path,
            "providers_used": metadata.get("providers", []),
            "extraction_mode": "open",
        },
        "validation_summary": {
            "methodology": "Open Discovery with Semantic Alignment and LLM Verification",
            "total_rules": len(validated_rules),
            "confidence_distribution": {
                "high": n_high,
                "medium": n_medium,
                "low": n_low,
            },
            "agreement_distribution": {
                "full": sum(1 for rule in validated_rules if rule["agreement"] == "full"),
                "partial": sum(1 for rule in validated_rules if rule["agreement"] == "partial"),
                "resolved": sum(1 for rule in validated_rules if rule["agreement"] == "resolved"),
                "conflict": sum(1 for rule in validated_rules if rule["agreement"] == "conflict"),
                "unique_confirmed": sum(
                    1 for rule in validated_rules if rule["agreement"] == "unique_confirmed"
                ),
                "unique_unverified": sum(
                    1 for rule in validated_rules if rule["agreement"] == "unique_unverified"
                ),
            },
            "categories_found": sorted({rule["category"] for rule in validated_rules}),
        },
        "agreement_metrics": metrics,
        "quality_indicators": {
            "high_confidence_percentage": f"{100 * n_high / total:.1f}%",
            "validated_percentage": f"{100 * (n_high + n_medium) / total:.1f}%",
            "needs_review_percentage": f"{100 * n_low / total:.1f}%",
        },
        "rules_needing_review": [
            {
                "id": rule["id"],
                "name": rule["name"],
                "reason": rule.get("warning", rule.get("conflict_details", "Low confidence")),
            }
            for rule in validated_rules
            if rule["confidence"] == "low"
        ],
    }

    report_path = os.path.join(output_dir, "validation_report.json")
    with open(report_path, "w") as file:
        json.dump(report, file, indent=2)
    print(f"  {report_path}")

    print("=" * 70)
    print(f"  Total validated rules: {len(validated_rules)}")
    print(f"  Categories: {len(report['validation_summary']['categories_found'])}")
    print(f"  High confidence: {n_high}")
    print(f"  Medium confidence: {n_medium}")
    print(f"  Low confidence: {n_low}")
    print("=" * 70)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export validated protocol rules from open-discovery alignment results"
    )
    parser.add_argument(
        "--alignment",
        default="spec_extraction/alignment_results.json",
        help="Path to alignment results JSON"
    )
    parser.add_argument(
        "--output-dir",
        default="configs",
        help="Output directory for validated rules"
    )
    parser.add_argument(
        "--extraction-dir",
        default=None,
        help="Directory with original per-provider extraction files"
    )
    parser.add_argument(
        "--mode",
        choices=["open"],
        default="open",
        help="Only open-discovery exports are supported"
    )

    args = parser.parse_args()

    if not os.path.exists(args.alignment):
        print(f"Error: alignment file not found: {args.alignment}")
        raise SystemExit(1)

    export_from_alignment(
        alignment_path=args.alignment,
        output_dir=args.output_dir,
        extraction_dir=args.extraction_dir,
    )
