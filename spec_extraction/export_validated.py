#!/usr/bin/env python3
"""
Export validated protocol rules with confidence metadata.

Combines comparison results and arbitration decisions to produce:
1. A validated rules file with confidence levels (for academic reporting)
2. A clean rules file (for fuzzer consumption)

Usage:
    python3 export_validated.py \
        --comparison comparison_results.json \
        --arbitration arbitration_results.json \
        --output-dir configs

Output:
    configs/
    ├── spec_rules_validated.json    # Full rules with validation metadata
    ├── spec_rules.json              # Clean rules for fuzzer
    └── validation_report.json       # Academic reporting summary
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def unflatten_json(flat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert dot-notation keys back to nested structure.
    
    Example:
        {"a.b": 1, "a.c": 2} -> {"a": {"b": 1, "c": 2}}
    """
    result = {}
    
    for key, value in flat.items():
        parts = key.split(".")
        current = result
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    return result


def merge_with_arbitrations(
    comparison: Dict[str, Any],
    arbitration: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merge comparison results with arbitration decisions.
    
    For low-confidence rules that were arbitrated, use the arbitrated value.
    """
    # Build arbitration lookup
    arbitration_lookup = {}
    if arbitration:
        for arb in arbitration.get("arbitrations", []):
            if arb["decision"] is not None:
                arbitration_lookup[arb["rule_path"]] = {
                    "value": arb["decision"],
                    "confidence": arb["confidence"],
                    "justification": arb["justification"],
                    "arbitrator": arb["arbitrator"]
                }
    
    # Process all rules
    validated_rules = {}
    validation_metadata = {}
    
    # High confidence rules
    for rule in comparison.get("rules_by_confidence", {}).get("high", []):
        path = rule["path"]
        validated_rules[path] = rule["value"]
        validation_metadata[path] = {
            "confidence": "high",
            "agreement": rule["extracted_by"],
            "source": "unanimous"
        }
    
    # Medium confidence rules
    for rule in comparison.get("rules_by_confidence", {}).get("medium", []):
        path = rule["path"]
        validated_rules[path] = rule["consensus_value"]
        validation_metadata[path] = {
            "confidence": "medium",
            "agreement": rule["extracted_by"],
            "all_values": rule.get("all_values", {}),
            "note": rule.get("note", ""),
            "source": "majority"
        }
    
    # Low confidence rules - check for arbitration
    for rule in comparison.get("rules_by_confidence", {}).get("low", []):
        path = rule["path"]
        
        if path in arbitration_lookup:
            # Use arbitrated value
            arb = arbitration_lookup[path]
            validated_rules[path] = arb["value"]
            validation_metadata[path] = {
                "confidence": f"arbitrated_{arb['confidence']}",
                "original_values": rule.get("all_values", {}),
                "arbitrator": arb["arbitrator"],
                "justification": arb["justification"],
                "source": "arbitration"
            }
        else:
            # Use first available value with low confidence flag
            values = rule.get("all_values", {})
            if values:
                first_value = list(values.values())[0]
                validated_rules[path] = first_value
                validation_metadata[path] = {
                    "confidence": "low",
                    "extracted_by": rule.get("extracted_by", []),
                    "all_values": values,
                    "conflict": rule.get("conflict", ""),
                    "source": "unresolved",
                    "warning": "This rule had conflicts that were not arbitrated"
                }
    
    return validated_rules, validation_metadata


def calculate_validation_stats(
    validation_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Calculate statistics for the validation report."""
    
    total = len(validation_metadata)
    
    stats = {
        "total_rules": total,
        "by_confidence": {
            "high": 0,
            "medium": 0,
            "arbitrated_high": 0,
            "arbitrated_medium": 0,
            "arbitrated_low": 0,
            "low": 0
        },
        "by_source": {
            "unanimous": 0,
            "majority": 0,
            "arbitration": 0,
            "unresolved": 0
        }
    }
    
    for path, meta in validation_metadata.items():
        conf = meta.get("confidence", "unknown")
        source = meta.get("source", "unknown")
        
        if conf in stats["by_confidence"]:
            stats["by_confidence"][conf] += 1
        
        if source in stats["by_source"]:
            stats["by_source"][source] += 1
    
    # Calculate percentages
    if total > 0:
        stats["confidence_rate"] = {
            "high_or_arbitrated_high": 
                (stats["by_confidence"]["high"] + stats["by_confidence"]["arbitrated_high"]) / total,
            "medium_or_better": 
                (stats["by_confidence"]["high"] + 
                 stats["by_confidence"]["medium"] + 
                 stats["by_confidence"]["arbitrated_high"] + 
                 stats["by_confidence"]["arbitrated_medium"]) / total,
            "needs_review": 
                (stats["by_confidence"]["low"] + stats["by_confidence"]["arbitrated_low"]) / total
        }
    
    return stats


def build_nested_rules(
    flat_rules: Dict[str, Any],
    validation_metadata: Dict[str, Any],
    include_metadata: bool = True
) -> Dict[str, Any]:
    """
    Build nested rules structure with optional validation metadata.
    
    Args:
        flat_rules: Flat dictionary of path -> value
        validation_metadata: Validation info per rule
        include_metadata: Whether to include _validation fields
    
    Returns:
        Nested rules dictionary
    """
    if not include_metadata:
        return unflatten_json(flat_rules)
    
    # Build with metadata
    result = {}
    
    for path, value in flat_rules.items():
        parts = path.split(".")
        current = result
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Set value
        current[parts[-1]] = value
        
        # Add validation metadata as sibling with underscore prefix
        if path in validation_metadata:
            meta_key = f"_{parts[-1]}_validation"
            current[meta_key] = validation_metadata[path]
    
    return result


def export_validated_rules(
    comparison_path: str,
    arbitration_path: Optional[str],
    output_dir: str,
    primary_source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Export validated rules in multiple formats.
    
    Args:
        comparison_path: Path to comparison_results.json
        arbitration_path: Path to arbitration_results.json (optional)
        output_dir: Output directory
        primary_source: If specified, use rules from this provider as base
    
    Returns:
        Summary dictionary
    """
    print("=" * 70)
    print("  EXPORT VALIDATED RULES")
    print("=" * 70)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Load comparison results
    print("\n📄 Loading comparison results...")
    with open(comparison_path, 'r') as f:
        comparison = json.load(f)
    
    # Load arbitration results if available
    arbitration = None
    if arbitration_path and os.path.exists(arbitration_path):
        print(f"📄 Loading arbitration results...")
        with open(arbitration_path, 'r') as f:
            arbitration = json.load(f)
    
    # Merge results
    print("\n🔄 Merging validated rules...")
    flat_rules, validation_metadata = merge_with_arbitrations(comparison, arbitration)
    
    print(f"   Total rules: {len(flat_rules)}")
    
    # Calculate statistics
    stats = calculate_validation_stats(validation_metadata)
    
    # Build nested structures
    print("\n📦 Building output files...")
    
    # 1. Full validated rules with metadata
    validated_rules = build_nested_rules(flat_rules, validation_metadata, include_metadata=True)
    validated_path = os.path.join(output_dir, "spec_rules_validated.json")
    with open(validated_path, 'w') as f:
        json.dump(validated_rules, f, indent=2, default=str)
    print(f"   ✓ {validated_path}")
    
    # 2. Clean rules for fuzzer (no metadata)
    clean_rules = build_nested_rules(flat_rules, validation_metadata, include_metadata=False)
    clean_path = os.path.join(output_dir, "spec_rules.json")
    with open(clean_path, 'w') as f:
        json.dump(clean_rules, f, indent=2, default=str)
    print(f"   ✓ {clean_path}")
    
    # 3. Validation report for academic use
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "comparison_source": comparison_path,
            "arbitration_source": arbitration_path,
            "providers_used": comparison.get("summary", {}).get("providers_compared", [])
        },
        "validation_summary": {
            "methodology": "Multi-Model Cross-Validation with LLM Arbitration",
            "total_rules": stats["total_rules"],
            "confidence_distribution": stats["by_confidence"],
            "source_distribution": stats["by_source"],
            "confidence_rates": stats.get("confidence_rate", {})
        },
        "agreement_metrics": {
            "pairwise_agreement": comparison.get("summary", {}).get("pairwise_agreement", {}),
            "fleiss_kappa": comparison.get("summary", {}).get("fleiss_kappa", None),
            "kappa_interpretation": comparison.get("summary_text", {}).get("kappa_interpretation", "")
        },
        "quality_indicators": {
            "high_confidence_percentage": 
                f"{100 * stats.get('confidence_rate', {}).get('high_or_arbitrated_high', 0):.1f}%",
            "validated_percentage": 
                f"{100 * stats.get('confidence_rate', {}).get('medium_or_better', 0):.1f}%",
            "needs_review_percentage": 
                f"{100 * stats.get('confidence_rate', {}).get('needs_review', 0):.1f}%"
        },
        "rules_needing_review": [
            {
                "path": path,
                "issue": meta.get("warning", meta.get("conflict", "Low confidence"))
            }
            for path, meta in validation_metadata.items()
            if meta.get("confidence") in ["low", "arbitrated_low"]
        ]
    }
    
    report_path = os.path.join(output_dir, "validation_report.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"   ✓ {report_path}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("  EXPORT COMPLETE")
    print("=" * 70)
    print(f"\n  📊 Validation Summary:")
    print(f"     Total rules: {stats['total_rules']}")
    print(f"\n  📈 Confidence Distribution:")
    print(f"     🟢 High confidence:         {stats['by_confidence']['high']:4d}")
    print(f"     🟢 Arbitrated (high):       {stats['by_confidence']['arbitrated_high']:4d}")
    print(f"     🟡 Medium confidence:       {stats['by_confidence']['medium']:4d}")
    print(f"     🟡 Arbitrated (medium):     {stats['by_confidence']['arbitrated_medium']:4d}")
    print(f"     🔴 Low/Unresolved:          {stats['by_confidence']['low']:4d}")
    
    high_rate = stats.get('confidence_rate', {}).get('high_or_arbitrated_high', 0)
    validated_rate = stats.get('confidence_rate', {}).get('medium_or_better', 0)
    
    print(f"\n  ✅ Quality Metrics:")
    print(f"     High confidence: {100*high_rate:.1f}%")
    print(f"     Validated (medium+): {100*validated_rate:.1f}%")
    
    print(f"\n  📁 Output files:")
    print(f"     - {validated_path} (with metadata)")
    print(f"     - {clean_path} (for fuzzer)")
    print(f"     - {report_path} (academic report)")
    print("=" * 70)
    
    return report


def generate_latex_table(report_path: str, output_path: str):
    """Generate LaTeX table for paper inclusion."""
    
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    summary = report["validation_summary"]
    metrics = report["agreement_metrics"]
    quality = report["quality_indicators"]
    
    latex = r"""
\begin{table}[h]
\centering
\caption{Multi-Model Extraction Validation Results}
\label{tab:validation}
\begin{tabular}{|l|r|}
\hline
\textbf{Metric} & \textbf{Value} \\
\hline
Total Rules Extracted & """ + str(summary["total_rules"]) + r""" \\
\hline
\multicolumn{2}{|c|}{\textit{Confidence Distribution}} \\
\hline
High Confidence (All Agree) & """ + str(summary["confidence_distribution"]["high"]) + r""" \\
Medium Confidence (Majority) & """ + str(summary["confidence_distribution"]["medium"]) + r""" \\
Arbitrated & """ + str(
    summary["confidence_distribution"]["arbitrated_high"] + 
    summary["confidence_distribution"]["arbitrated_medium"] +
    summary["confidence_distribution"]["arbitrated_low"]
) + r""" \\
Low Confidence (Unresolved) & """ + str(summary["confidence_distribution"]["low"]) + r""" \\
\hline
\multicolumn{2}{|c|}{\textit{Agreement Metrics}} \\
\hline
Fleiss' Kappa & """ + f"{metrics['fleiss_kappa']:.3f}" + r""" \\
Kappa Interpretation & """ + metrics["kappa_interpretation"] + r""" \\
\hline
\multicolumn{2}{|c|}{\textit{Quality Indicators}} \\
\hline
High Confidence Rate & """ + quality["high_confidence_percentage"] + r""" \\
Validated Rate (Medium+) & """ + quality["validated_percentage"] + r""" \\
\hline
\end{tabular}
\end{table}
"""
    
    with open(output_path, 'w') as f:
        f.write(latex)
    
    print(f"LaTeX table saved to: {output_path}")


def export_from_alignment(
    alignment_path: str,
    output_dir: str
) -> Dict[str, Any]:
    """
    Export validated rules from the new alignment-based format.
    
    Reads alignment_results.json (from align_rules.py) and produces:
    - spec_rules_validated.json (rules with confidence metadata)
    - spec_rules.json (clean rules for fuzzer)
    - validation_report.json (academic reporting)
    
    Args:
        alignment_path: Path to alignment_results.json
        output_dir: Output directory
    
    Returns:
        Report dictionary
    """
    print("=" * 70)
    print("  EXPORT VALIDATED RULES (from alignment)")
    print("=" * 70)

    os.makedirs(output_dir, exist_ok=True)

    with open(alignment_path, 'r') as f:
        alignment_data = json.load(f)

    alignment = alignment_data.get("alignment", {})
    metrics = alignment_data.get("metrics", {})
    metadata = alignment_data.get("metadata", {})

    aligned_groups = alignment.get("aligned_groups", [])
    unique_rules = alignment.get("unique_rules", [])
    unique_verified = alignment.get("unique_rules_verified", unique_rules)

    # Build validated rules list
    validated_rules = []
    rule_counter = 0

    # Process aligned groups
    for group in aligned_groups:
        rule_counter += 1
        confidence = group.get("confidence", "low")
        agreement = group.get("agreement", "unknown")

        rule_entry = {
            "id": f"rule_{rule_counter:03d}",
            "name": group.get("canonical_name", f"Rule {rule_counter}"),
            "category": group.get("canonical_category", "unknown"),
            "consensus_value": group.get("consensus_value"),
            "agreement": agreement,
            "confidence": confidence,
            "providers": [m.get("provider") for m in group.get("matches", [])],
            "provider_values": {
                m.get("provider"): m.get("constraint_value")
                for m in group.get("matches", [])
            }
        }

        if group.get("conflict_details"):
            rule_entry["conflict_details"] = group["conflict_details"]

        validated_rules.append(rule_entry)

    # Process verified unique rules (confirmed only)
    for unique in unique_verified:
        verification = unique.get("verification", "unknown")
        if verification == "confirmed":
            rule_counter += 1
            validated_rules.append({
                "id": f"rule_{rule_counter:03d}",
                "name": unique.get("name", f"Rule {rule_counter}"),
                "category": unique.get("category", "unknown"),
                "consensus_value": unique.get("corrected_value") or None,
                "agreement": "unique_confirmed",
                "confidence": unique.get("confidence", "low"),
                "providers": [unique.get("provider")],
                "source": "verified_unique",
                "justification": unique.get("justification", "")
            })
        elif verification not in ("rejected", "error", "skipped"):
            # Include unverified unique rules with low confidence
            rule_counter += 1
            validated_rules.append({
                "id": f"rule_{rule_counter:03d}",
                "name": unique.get("name", f"Rule {rule_counter}"),
                "category": unique.get("category", "unknown"),
                "consensus_value": None,
                "agreement": "unique_unverified",
                "confidence": "low",
                "providers": [unique.get("provider")],
                "source": "unverified_unique",
                "warning": "Found by only one model, not yet verified"
            })

    # Build clean rules (for fuzzer consumption) — nested by category
    clean_rules = {}
    for rule in validated_rules:
        if rule["confidence"] in ("high", "medium") or rule["agreement"] in ("full", "partial", "unique_confirmed"):
            cat = rule["category"]
            if cat not in clean_rules:
                clean_rules[cat] = {}

            field_key = rule["name"].lower().replace(" ", "_").replace("-", "_")
            clean_rules[cat][field_key] = rule["consensus_value"]

    # Save outputs
    # 1. Full validated rules with metadata
    validated_path = os.path.join(output_dir, "spec_rules_validated.json")
    with open(validated_path, 'w') as f:
        json.dump({"rules": validated_rules}, f, indent=2, default=str)
    print(f"  {validated_path}")

    # 2. Clean rules for fuzzer
    clean_path = os.path.join(output_dir, "spec_rules.json")
    with open(clean_path, 'w') as f:
        json.dump(clean_rules, f, indent=2, default=str)
    print(f"  {clean_path}")

    # 3. Validation report
    n_high = sum(1 for r in validated_rules if r["confidence"] == "high")
    n_med = sum(1 for r in validated_rules if r["confidence"] == "medium")
    n_low = sum(1 for r in validated_rules if r["confidence"] == "low")

    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "alignment_source": alignment_path,
            "providers_used": metadata.get("providers", []),
            "extraction_mode": "open"
        },
        "validation_summary": {
            "methodology": "Open Discovery with Semantic Alignment and LLM Verification",
            "total_rules": len(validated_rules),
            "confidence_distribution": {
                "high": n_high,
                "medium": n_med,
                "low": n_low
            },
            "agreement_distribution": {
                "full": sum(1 for r in validated_rules if r["agreement"] == "full"),
                "partial": sum(1 for r in validated_rules if r["agreement"] == "partial"),
                "conflict": sum(1 for r in validated_rules if r["agreement"] == "conflict"),
                "unique_confirmed": sum(1 for r in validated_rules if r["agreement"] == "unique_confirmed"),
                "unique_unverified": sum(1 for r in validated_rules if r["agreement"] == "unique_unverified")
            },
            "categories_found": sorted(set(r["category"] for r in validated_rules))
        },
        "agreement_metrics": metrics,
        "quality_indicators": {
            "high_confidence_percentage": f"{100 * n_high / max(len(validated_rules), 1):.1f}%",
            "validated_percentage": f"{100 * (n_high + n_med) / max(len(validated_rules), 1):.1f}%",
            "needs_review_percentage": f"{100 * n_low / max(len(validated_rules), 1):.1f}%"
        },
        "rules_needing_review": [
            {"id": r["id"], "name": r["name"], "reason": r.get("warning", r.get("conflict_details", "Low confidence"))}
            for r in validated_rules
            if r["confidence"] == "low"
        ]
    }

    report_path = os.path.join(output_dir, "validation_report.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"  {report_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("  EXPORT COMPLETE")
    print("=" * 70)
    print(f"  Total validated rules: {len(validated_rules)}")
    print(f"  Categories: {len(report['validation_summary']['categories_found'])}")
    print(f"  High confidence: {n_high}")
    print(f"  Medium confidence: {n_med}")
    print(f"  Low confidence: {n_low}")
    print("=" * 70)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export validated protocol rules"
    )
    parser.add_argument(
        "--comparison",
        default="spec_extraction/comparison_results.json",
        help="Path to comparison results JSON (legacy strict mode)"
    )
    parser.add_argument(
        "--alignment",
        default="spec_extraction/alignment_results.json",
        help="Path to alignment results JSON (open mode)"
    )
    parser.add_argument(
        "--arbitration",
        default="spec_extraction/arbitration_results.json",
        help="Path to arbitration results JSON (legacy, optional)"
    )
    parser.add_argument(
        "--output-dir",
        default="configs",
        help="Output directory for validated rules"
    )
    parser.add_argument(
        "--mode",
        choices=["strict", "open", "auto"],
        default="auto",
        help="Export mode: 'strict' uses comparison+arbitration, 'open' uses alignment, 'auto' detects (default: auto)"
    )
    parser.add_argument(
        "--latex",
        action="store_true",
        help="Also generate LaTeX table for paper"
    )
    
    args = parser.parse_args()

    # Auto-detect mode
    if args.mode == "auto":
        if os.path.exists(args.alignment):
            args.mode = "open"
        elif os.path.exists(args.comparison):
            args.mode = "strict"
        else:
            print("Error: No comparison or alignment results found")
            print(f"  Checked: {args.comparison}")
            print(f"  Checked: {args.alignment}")
            sys.exit(1)

    if args.mode == "open":
        if not os.path.exists(args.alignment):
            print(f"Error: Alignment file not found: {args.alignment}")
            sys.exit(1)
        report = export_from_alignment(
            alignment_path=args.alignment,
            output_dir=args.output_dir
        )
    else:
        if not os.path.exists(args.comparison):
            print(f"Error: Comparison file not found: {args.comparison}")
            sys.exit(1)
        report = export_validated_rules(
            comparison_path=args.comparison,
            arbitration_path=args.arbitration if os.path.exists(args.arbitration) else None,
            output_dir=args.output_dir
        )
    
    if args.latex:
        report_path = os.path.join(args.output_dir, "validation_report.json")
        latex_path = os.path.join(args.output_dir, "validation_table.tex")
        generate_latex_table(report_path, latex_path)

