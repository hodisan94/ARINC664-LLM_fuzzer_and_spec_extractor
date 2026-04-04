#!/usr/bin/env python3
"""
Semantic rule alignment across multiple LLM provider extractions.

This module replaces the old key-based comparison (compare_extractions.py) with
semantic alignment that works with the open-discovery extraction format.

Instead of comparing fixed JSON keys, it:
1. Collects all rules from all providers
2. Uses an LLM to semantically match rules that describe the same constraint
3. Classifies matches by agreement level (full, partial, conflict)
4. Identifies unique rules (found by only one model) for verification
5. Optionally verifies unique rules against the spec text

Usage:
    python3 align_rules.py \\
        --input-dir spec_extraction/multimodel_output \\
        --output spec_extraction/alignment_results.json \\
        [--verify-unique] [--pdf configs/ARINC_664P7.pdf]

Output:
    alignment_results.json with:
    - Aligned rule groups with confidence levels
    - Unique rules needing verification
    - Alignment statistics and agreement metrics
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv(Path(__file__).parent.parent / ".env")

from spec_extraction.llm_providers import (
    MultiModelClient,
    ModelProvider,
    get_single_provider
)
from spec_extraction.prompts_open import (
    SYSTEM_PROMPT_RULE_ALIGNMENT,
    SYSTEM_PROMPT_VERIFY_UNIQUE,
    SYSTEM_PROMPT_RESOLVE_CONFLICT,
    get_alignment_prompt,
    get_verify_unique_prompt,
    get_resolve_conflict_prompt
)


def load_open_extractions(input_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Load open-format extraction files from a directory.
    
    Expects files named: rules_<provider>.json
    Each file should contain: {"rules": [...], "extraction_stats": {...}}
    
    Also supports legacy format (flat JSON without "rules" key) by wrapping it.
    """
    extractions = {}

    for filename in os.listdir(input_dir):
        if filename.startswith("rules_") and filename.endswith(".json"):
            provider = filename[6:-5]
            filepath = os.path.join(input_dir, filename)

            with open(filepath, 'r') as f:
                data = json.load(f)

            # Skip if error
            if isinstance(data, dict) and "error" in data:
                print(f"  Skipping {provider}: {data['error']}")
                continue

            # Detect format
            if isinstance(data, dict) and "rules" in data and isinstance(data["rules"], list):
                # New open format
                extractions[provider] = data
                n_rules = len(data["rules"])
            elif isinstance(data, dict):
                # Legacy flat format — skip (not compatible with alignment)
                print(f"  Skipping {provider}: legacy flat format (use compare_extractions.py instead)")
                continue
            else:
                print(f"  Skipping {provider}: unexpected format")
                continue

            print(f"  Loaded {provider}: {n_rules} rules")

    return extractions


def compute_local_agreement_metrics(alignment: Dict[str, Any], n_providers: int) -> Dict[str, Any]:
    """
    Compute agreement metrics from alignment results without requiring LLM.
    """
    groups = alignment.get("aligned_groups", [])
    unique = alignment.get("unique_rules", [])

    n_full = sum(1 for g in groups if g.get("agreement") == "full")
    n_partial = sum(1 for g in groups if g.get("agreement") == "partial")
    n_conflict = sum(1 for g in groups if g.get("agreement") == "conflict")
    n_unique = len(unique)

    total_items = len(groups) + n_unique

    # Compute pairwise agreement from aligned groups
    provider_pairs = {}
    for g in groups:
        matches = g.get("matches", [])
        providers_in_group = [m["provider"] for m in matches]
        for i, p1 in enumerate(providers_in_group):
            for p2 in providers_in_group[i+1:]:
                pair_key = f"{min(p1,p2)}_vs_{max(p1,p2)}"
                if pair_key not in provider_pairs:
                    provider_pairs[pair_key] = {"agree": 0, "total": 0}
                provider_pairs[pair_key]["total"] += 1
                if g.get("agreement") in ("full", "partial"):
                    provider_pairs[pair_key]["agree"] += 1

    pairwise = {
        k: v["agree"] / max(v["total"], 1) for k, v in provider_pairs.items()
    }

    # Simplified Fleiss' Kappa
    if total_items > 0 and n_providers >= 2:
        observed = (n_full + 0.5 * n_partial) / total_items
        expected = 1 / n_providers
        if expected < 1:
            kappa = (observed - expected) / (1 - expected)
        else:
            kappa = 1.0
    else:
        kappa = 1.0

    return {
        "total_aligned_groups": len(groups),
        "full_agreement": n_full,
        "partial_agreement": n_partial,
        "conflicts": n_conflict,
        "unique_rules": n_unique,
        "total_distinct_rules": total_items,
        "pairwise_agreement": pairwise,
        "fleiss_kappa": round(max(-1, min(1, kappa)), 3),
        "kappa_interpretation": _interpret_kappa(kappa)
    }


def _interpret_kappa(kappa: float) -> str:
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


def align_extractions(
    extractions: Dict[str, Dict[str, Any]],
    arbiter_provider_name: str = "openai",
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Align rules across multiple provider extractions using LLM.
    
    Args:
        extractions: Dict of provider_name -> {"rules": [...]}
        arbiter_provider_name: Which LLM provider to use for alignment
        output_path: Optional path to save results
    
    Returns:
        Alignment results dictionary
    """
    providers = list(extractions.keys())
    n_providers = len(providers)

    print("=" * 70)
    print("  SEMANTIC RULE ALIGNMENT")
    print("=" * 70)
    print(f"  Providers: {', '.join(providers)}")
    print(f"  Arbiter: {arbiter_provider_name}")

    # Print extraction summary
    for p in providers:
        n = len(extractions[p].get("rules", []))
        cats = set(r.get("category", "unknown") for r in extractions[p].get("rules", []))
        print(f"  {p}: {n} rules in {len(cats)} categories")

    print("=" * 70)

    # Initialize arbiter LLM
    print(f"\n  Initializing {arbiter_provider_name} as alignment arbiter...")
    try:
        arbiter = get_single_provider(arbiter_provider_name)
    except Exception as e:
        print(f"  Failed to init {arbiter_provider_name}: {e}")
        print("  Trying openai as fallback...")
        arbiter = get_single_provider("openai")

    # Build alignment prompt
    print("\n  Generating alignment prompt...")
    user_prompt = get_alignment_prompt(extractions)

    # Check if the prompt is very large — if so, chunk it
    total_rules = sum(len(e.get("rules", [])) for e in extractions.values())

    if total_rules > 60:
        # Too many rules for one prompt — align in batches by category
        print(f"  Large extraction ({total_rules} rules) — aligning by category batches...")
        alignment = _align_in_batches(extractions, arbiter)
    else:
        # Single alignment call
        print(f"\n  Aligning {total_rules} rules across {n_providers} providers...")
        try:
            alignment = arbiter.query_json(
                system_prompt=SYSTEM_PROMPT_RULE_ALIGNMENT,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=8000
            )
            print("  Alignment complete")
        except Exception as e:
            print(f"  Alignment failed: {e}")
            alignment = _fallback_alignment(extractions)

    # Compute local metrics
    metrics = compute_local_agreement_metrics(alignment, n_providers)

    # Build final result
    result = {
        "metadata": {
            "providers": providers,
            "arbiter": arbiter_provider_name,
            "timestamp": datetime.now().isoformat(),
            "total_rules_input": {p: len(e.get("rules", [])) for p, e in extractions.items()}
        },
        "alignment": alignment,
        "metrics": metrics
    }

    # Save if output path specified
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Saved alignment results to: {output_path}")

    # Print summary
    _print_summary(metrics, providers)

    return result


def _align_in_batches(
    extractions: Dict[str, Dict[str, Any]],
    arbiter
) -> Dict[str, Any]:
    """
    Align rules in batches when there are too many for a single prompt.
    Groups rules by category first, then aligns each category batch.
    """
    # Collect all categories across all providers
    all_categories = set()
    for data in extractions.values():
        for rule in data.get("rules", []):
            all_categories.add(rule.get("category", "uncategorized").lower().strip())

    # Group rules by category
    aligned_groups = []
    unique_rules = []
    batch_num = 0

    # Process in batches of ~5 categories
    cat_list = sorted(all_categories)
    batch_size = 5

    for i in range(0, len(cat_list), batch_size):
        batch_cats = set(cat_list[i:i + batch_size])
        batch_num += 1

        # Filter rules to this batch
        batch_extractions = {}
        for provider, data in extractions.items():
            batch_rules = [
                r for r in data.get("rules", [])
                if r.get("category", "uncategorized").lower().strip() in batch_cats
            ]
            if batch_rules:
                batch_extractions[provider] = {"rules": batch_rules}

        if not batch_extractions:
            continue

        total_in_batch = sum(len(e["rules"]) for e in batch_extractions.values())
        print(f"    Batch {batch_num}: {len(batch_cats)} categories, {total_in_batch} rules...")

        try:
            user_prompt = get_alignment_prompt(batch_extractions)
            batch_result = arbiter.query_json(
                system_prompt=SYSTEM_PROMPT_RULE_ALIGNMENT,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=8000
            )

            # Renumber group IDs
            for g in batch_result.get("aligned_groups", []):
                g["group_id"] = f"G{len(aligned_groups) + 1:03d}"
                aligned_groups.append(g)

            unique_rules.extend(batch_result.get("unique_rules", []))
            print(f"      -> {len(batch_result.get('aligned_groups', []))} groups, "
                  f"{len(batch_result.get('unique_rules', []))} unique")

        except Exception as e:
            print(f"      -> Batch failed: {e}")

    return {
        "aligned_groups": aligned_groups,
        "unique_rules": unique_rules,
        "alignment_stats": {
            "total_groups": len(aligned_groups),
            "full_agreement": sum(1 for g in aligned_groups if g.get("agreement") == "full"),
            "partial_agreement": sum(1 for g in aligned_groups if g.get("agreement") == "partial"),
            "conflicts": sum(1 for g in aligned_groups if g.get("agreement") == "conflict"),
            "unique_rules": len(unique_rules)
        }
    }


def _fallback_alignment(extractions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fallback alignment using simple field_name matching when LLM alignment fails.
    """
    print("  Using fallback (field-name matching)...")

    # Group rules by normalized field_name
    field_groups = {}
    for provider, data in extractions.items():
        for rule in data.get("rules", []):
            field = rule.get("field_name", "").lower().strip()
            if not field:
                field = rule.get("name", "unknown").lower().strip()

            if field not in field_groups:
                field_groups[field] = []
            field_groups[field].append({
                "provider": provider,
                "rule": rule
            })

    aligned_groups = []
    unique_rules = []

    for field, entries in field_groups.items():
        providers_found = set(e["provider"] for e in entries)

        if len(providers_found) >= 2:
            group = {
                "group_id": f"G{len(aligned_groups) + 1:03d}",
                "canonical_name": entries[0]["rule"].get("name", field),
                "canonical_category": entries[0]["rule"].get("category", "unknown"),
                "matches": [
                    {
                        "provider": e["provider"],
                        "rule_id": e["rule"].get("id", "unknown"),
                        "field_name": e["rule"].get("field_name", field),
                        "constraint_value": e["rule"].get("constraint", {}).get("value")
                    }
                    for e in entries
                ],
                "agreement": "partial",
                "consensus_value": None,
                "conflict_details": "Aligned by field name only (fallback)",
                "confidence": "medium" if len(providers_found) >= 2 else "low"
            }
            aligned_groups.append(group)
        else:
            for e in entries:
                unique_rules.append({
                    "provider": e["provider"],
                    "rule_id": e["rule"].get("id", "unknown"),
                    "name": e["rule"].get("name", field),
                    "category": e["rule"].get("category", "unknown"),
                    "needs_verification": True,
                    "reason": "Only found by one model"
                })

    return {
        "aligned_groups": aligned_groups,
        "unique_rules": unique_rules,
        "alignment_stats": {
            "total_groups": len(aligned_groups),
            "full_agreement": 0,
            "partial_agreement": len(aligned_groups),
            "conflicts": 0,
            "unique_rules": len(unique_rules)
        }
    }


def verify_unique_rules(
    alignment_result: Dict[str, Any],
    extractions: Dict[str, Dict[str, Any]],
    pdf_path: str,
    verifier_provider_name: str = "openai"
) -> Dict[str, Any]:
    """
    Verify unique rules (found by only one model) against the specification.
    
    Args:
        alignment_result: Output from align_extractions
        extractions: Original provider extractions
        pdf_path: Path to ARINC 664 Part 7 PDF
        verifier_provider_name: LLM provider to use for verification
    
    Returns:
        Updated alignment result with verification decisions
    """
    unique_rules = alignment_result.get("alignment", {}).get("unique_rules", [])

    if not unique_rules:
        print("  No unique rules to verify")
        return alignment_result

    print(f"\n  Verifying {len(unique_rules)} unique rules...")

    # Load spec text
    from spec_extraction.pdf_utils import get_all_relevant_text
    chapter_texts = get_all_relevant_text(pdf_path)
    full_spec_text = "\n\n".join(chapter_texts.values())

    # Limit spec text size for prompts
    max_spec_chars = 4000

    verifier = get_single_provider(verifier_provider_name)

    verified = []
    confirmed_count = 0
    rejected_count = 0

    for i, unique in enumerate(unique_rules):
        provider = unique.get("provider", "unknown")
        rule_id = unique.get("rule_id", "unknown")

        # Find the full rule object
        full_rule = None
        if provider in extractions:
            for r in extractions[provider].get("rules", []):
                if r.get("id") == rule_id:
                    full_rule = r
                    break

        if not full_rule:
            verified.append({**unique, "verification": "skipped", "reason": "Rule not found"})
            continue

        # Use source_quote to find relevant spec section
        source_section = full_rule.get("source_section", "")
        source_quote = full_rule.get("source_quote", "")

        # Find relevant text chunk
        relevant_text = _find_relevant_text(source_quote, full_spec_text, max_spec_chars)

        print(f"    [{i+1}/{len(unique_rules)}] Verifying: {full_rule.get('name', rule_id)}...", end=" ")

        try:
            user_prompt = get_verify_unique_prompt(full_rule, relevant_text, provider)
            result = verifier.query_json(
                system_prompt=SYSTEM_PROMPT_VERIFY_UNIQUE,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=1000
            )

            decision = result.get("verification", "unknown")
            if decision == "confirmed":
                confirmed_count += 1
                print("CONFIRMED")
            elif decision == "rejected":
                rejected_count += 1
                print("REJECTED")
            else:
                print(f"{decision}")

            verified.append({**unique, **result})

        except Exception as e:
            print(f"ERROR: {e}")
            verified.append({**unique, "verification": "error", "reason": str(e)})

    # Update alignment result
    alignment_result["alignment"]["unique_rules_verified"] = verified
    alignment_result["verification_stats"] = {
        "total_verified": len(verified),
        "confirmed": confirmed_count,
        "rejected": rejected_count,
        "errors": len(verified) - confirmed_count - rejected_count
    }

    print(f"\n  Verification complete: {confirmed_count} confirmed, {rejected_count} rejected")

    return alignment_result


def resolve_conflicts(
    alignment_result: Dict[str, Any],
    extractions: Dict[str, Dict[str, Any]],
    pdf_path: str,
    judge_provider_name: str = "openai"
) -> Dict[str, Any]:
    """
    Resolve conflicts where models disagree on a rule's value.

    For each aligned group marked as "conflict", the judge LLM receives:
      1. The conflicting values from each model
      2. The relevant section of the ARINC 664 spec
    and determines which model (if any) extracted the correct value.

    Args:
        alignment_result: Output from align_extractions()
        extractions: Original provider extractions (to find source_quotes)
        pdf_path: Path to ARINC 664 Part 7 PDF
        judge_provider_name: LLM provider to use as the judge

    Returns:
        Updated alignment_result with resolved conflicts
    """
    aligned_groups = alignment_result.get("alignment", {}).get("aligned_groups", [])
    conflicts = [g for g in aligned_groups if g.get("agreement") == "conflict"]

    if not conflicts:
        print("  No conflicts to resolve.")
        return alignment_result

    print(f"\n  Resolving {len(conflicts)} conflicts using {judge_provider_name} as judge...")

    from spec_extraction.pdf_utils import get_all_relevant_text
    chapter_texts = get_all_relevant_text(pdf_path)
    full_spec_text = "\n\n".join(chapter_texts.values())

    judge = get_single_provider(judge_provider_name)

    max_spec_chars = 5000
    resolved_count = 0
    unresolvable_count = 0

    for i, group in enumerate(conflicts):
        group_id = group.get("group_id", f"G{i+1}")
        canonical_name = group.get("canonical_name", "Unknown")

        print(f"    [{i+1}/{len(conflicts)}] {canonical_name}...", end=" ")

        # Gather source quotes from the original extractions to locate spec text
        source_hints = _collect_source_hints(group, extractions)
        relevant_text = _find_relevant_text(source_hints, full_spec_text, max_spec_chars)

        try:
            user_prompt = get_resolve_conflict_prompt(group, relevant_text)
            resolution = judge.query_json(
                system_prompt=SYSTEM_PROMPT_RESOLVE_CONFLICT,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=1500
            )

            decision = resolution.get("resolution", "unresolvable")

            if decision == "unresolvable":
                unresolvable_count += 1
                print("UNRESOLVABLE")
            else:
                resolved_count += 1
                group["agreement"] = "resolved"
                group["consensus_value"] = resolution.get("chosen_value")
                group["confidence"] = resolution.get("confidence", "medium")
                print(f"RESOLVED ({decision}) -> {resolution.get('chosen_value', '?')[:60]}")

            group["judge_resolution"] = resolution

        except Exception as e:
            print(f"ERROR: {e}")
            group["judge_resolution"] = {"resolution": "error", "error": str(e)}

    # Update metrics
    alignment_result["conflict_resolution_stats"] = {
        "total_conflicts": len(conflicts),
        "resolved": resolved_count,
        "unresolvable": unresolvable_count,
        "errors": len(conflicts) - resolved_count - unresolvable_count,
        "judge": judge_provider_name
    }

    print(f"\n  Conflict resolution complete: "
          f"{resolved_count} resolved, {unresolvable_count} unresolvable")

    return alignment_result


def _collect_source_hints(
    group: Dict[str, Any],
    extractions: Dict[str, Dict[str, Any]]
) -> str:
    """
    Collect source_quote and field_name from the original rule objects
    so we can locate the relevant spec section.
    """
    hints = []
    for match in group.get("matches", []):
        provider = match.get("provider", "")
        rule_id = match.get("rule_id", "")

        if provider in extractions:
            for r in extractions[provider].get("rules", []):
                if r.get("id") == rule_id:
                    quote = r.get("source_quote", "")
                    if quote:
                        hints.append(quote)
                    name = r.get("name", "")
                    if name:
                        hints.append(name)
                    break

    if not hints:
        hints.append(group.get("canonical_name", ""))

    return " ".join(hints)


def _find_relevant_text(source_quote: str, full_text: str, max_chars: int) -> str:
    """Find the section of text most relevant to a source quote."""
    if not source_quote or not full_text:
        return full_text[:max_chars]

    # Try to find the quote in the full text
    quote_lower = source_quote.lower()[:100]
    text_lower = full_text.lower()

    idx = text_lower.find(quote_lower)
    if idx >= 0:
        start = max(0, idx - max_chars // 4)
        end = min(len(full_text), idx + max_chars * 3 // 4)
        return full_text[start:end]

    # Fallback: find by keywords
    keywords = [w for w in source_quote.split() if len(w) > 4][:5]
    best_idx = 0
    best_score = 0

    chunk_size = max_chars
    for pos in range(0, len(text_lower), chunk_size // 2):
        chunk = text_lower[pos:pos + chunk_size]
        score = sum(1 for kw in keywords if kw.lower() in chunk)
        if score > best_score:
            best_score = score
            best_idx = pos

    return full_text[best_idx:best_idx + max_chars]


def _print_summary(metrics: Dict[str, Any], providers: List[str]):
    """Print alignment summary."""
    print("\n" + "=" * 70)
    print("  ALIGNMENT RESULTS")
    print("=" * 70)
    print(f"\n  Providers: {', '.join(providers)}")
    print(f"\n  Total distinct rules: {metrics['total_distinct_rules']}")
    print(f"  Aligned groups: {metrics['total_aligned_groups']}")
    print(f"\n  Agreement Distribution:")
    print(f"     Full agreement:    {metrics['full_agreement']:4d}")
    print(f"     Partial agreement: {metrics['partial_agreement']:4d}")
    print(f"     Conflicts:         {metrics['conflicts']:4d}")
    print(f"     Unique rules:      {metrics['unique_rules']:4d}")
    print(f"\n  Pairwise Agreement:")
    for pair, val in metrics.get("pairwise_agreement", {}).items():
        print(f"     {pair}: {val:.1%}")
    print(f"\n  Fleiss' Kappa: {metrics['fleiss_kappa']:.3f} ({metrics['kappa_interpretation']})")
    print("=" * 70)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Semantically align protocol rules across multiple LLM extractions"
    )
    parser.add_argument(
        "--input-dir",
        default="spec_extraction/multimodel_output",
        help="Directory containing rules_*.json files (open format)"
    )
    parser.add_argument(
        "--output",
        default="spec_extraction/alignment_results.json",
        help="Output path for alignment results"
    )
    parser.add_argument(
        "--arbiter",
        default="openai",
        choices=["openai", "anthropic", "mistral"],
        help="LLM provider to use as alignment arbiter"
    )
    parser.add_argument(
        "--resolve-conflicts",
        action="store_true",
        help="Resolve conflicts by having a judge LLM check the spec"
    )
    parser.add_argument(
        "--verify-unique",
        action="store_true",
        help="Verify rules found by only one model"
    )
    parser.add_argument(
        "--judge",
        default=None,
        choices=["openai", "anthropic", "mistral"],
        help="LLM provider to use as conflict judge (default: same as --arbiter)"
    )
    parser.add_argument(
        "--pdf",
        default="configs/ARINC_664P7.pdf",
        help="Path to spec PDF (required for --resolve-conflicts and --verify-unique)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Shortcut: align + resolve conflicts + verify unique rules"
    )

    args = parser.parse_args()

    if args.full:
        args.resolve_conflicts = True
        args.verify_unique = True

    judge_provider = args.judge or args.arbiter

    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)

    # Load extractions
    print(f"\n  Loading extractions from {args.input_dir}...")
    extractions = load_open_extractions(args.input_dir)

    if len(extractions) < 2:
        print(f"\n  Error: Need at least 2 extractions to align")
        print(f"  Found: {list(extractions.keys())}")
        sys.exit(1)

    # Step 1: Align rules across models
    result = align_extractions(
        extractions=extractions,
        arbiter_provider_name=args.arbiter,
        output_path=args.output
    )

    # Step 2: Resolve conflicts — judge goes back to the spec
    if args.resolve_conflicts:
        if not os.path.exists(args.pdf):
            print(f"  Error: PDF not found: {args.pdf} (needed for conflict resolution)")
        else:
            result = resolve_conflicts(
                alignment_result=result,
                extractions=extractions,
                pdf_path=args.pdf,
                judge_provider_name=judge_provider
            )
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Updated {args.output} with conflict resolutions")

    # Step 3: Verify unique rules
    if args.verify_unique:
        if not os.path.exists(args.pdf):
            print(f"  Error: PDF not found: {args.pdf} (needed for unique verification)")
        else:
            result = verify_unique_rules(
                alignment_result=result,
                extractions=extractions,
                pdf_path=args.pdf,
                verifier_provider_name=judge_provider
            )
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Updated {args.output} with verification results")
