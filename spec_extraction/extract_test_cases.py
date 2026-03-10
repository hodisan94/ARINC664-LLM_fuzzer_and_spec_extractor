#!/usr/bin/env python3
"""
AFDX Test Case Extraction Script
Extracts test cases that violate AFDX protocol rules using LLM.

This script implements the "Test Case Extraction via LLM" step from the paper.
It queries the LLM to propose out-of-range values that intentionally violate protocol rules.

Usage:
    python3 extract_test_cases.py [--validate] [--output OUTPUT]
"""

import json
import argparse
import os
from typing import Dict, Any, List
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from llm_client import LLMClient
from test_case_prompts import (
    SYSTEM_PROMPT_TEST_CASE_EXTRACTION,
    get_test_case_extraction_prompt
)
from validate_test_cases import TestCaseValidator


def load_spec_rules(spec_file: str) -> Dict[str, Any]:
    """Load AFDX specification rules from JSON file."""
    with open(spec_file, 'r') as f:
        return json.load(f)


def extract_test_cases_for_rule(
    llm_client: LLMClient,
    rule_name: str,
    rule_data: Any,
    checkpoint_file: str = None,
    timeout_seconds: int = 90
) -> Dict[str, Any]:
    """
    Extract test cases for a single rule using LLM.
    
    Args:
        llm_client: LLM client instance
        rule_name: Name of the rule
        rule_data: Rule specification data
        checkpoint_file: Optional checkpoint file for resuming
        timeout_seconds: Max seconds to wait for a single API call
        
    Returns:
        Dictionary containing extracted test cases
    """
    import signal

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"API call timed out after {timeout_seconds}s")

    print(f"\nExtracting test cases for: {rule_name}")
    
    user_prompt = get_test_case_extraction_prompt(rule_name, rule_data)
    
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        test_cases = llm_client.query_json(
            system_prompt=SYSTEM_PROMPT_TEST_CASE_EXTRACTION,
            user_prompt=user_prompt
        )
        signal.alarm(0)
        
        if checkpoint_file:
            with open(checkpoint_file, 'a') as f:
                checkpoint_entry = {
                    "rule_name": rule_name,
                    "test_cases": test_cases
                }
                f.write(json.dumps(checkpoint_entry) + "\n")
        
        return test_cases
    
    except TimeoutError:
        signal.alarm(0)
        print(f"  TIMEOUT extracting test cases for {rule_name} — skipping")
        if checkpoint_file:
            with open(checkpoint_file, 'a') as f:
                f.write(json.dumps({"rule_name": rule_name, "test_cases": {}}) + "\n")
        return {}
    except Exception as e:
        signal.alarm(0)
        print(f"Error extracting test cases for {rule_name}: {e}")
        return {}
    finally:
        signal.signal(signal.SIGALRM, old_handler)


def flatten_rules(rules: Dict[str, Any], prefix: str = "") -> List[tuple]:
    """
    Flatten nested rule structure into a list of (name, data) tuples.
    
    Supports three formats:
    1. Open list format: {"rules": [{"id": "rule_001", ...}, ...]}
    2. Clean 2-level format: {"Category": {"rule_name": value_or_dict, ...}, ...}
    3. Legacy nested format: {"bag": {"allowed_values_ms": [...]}, ...}
    
    Returns:
        List of (full_key_path, rule_data) tuples
    """
    if "rules" in rules and isinstance(rules["rules"], list):
        return _flatten_open_format(rules["rules"])

    if _is_clean_format(rules):
        return _flatten_clean_format(rules)

    return _flatten_legacy_format(rules, prefix)


def _is_clean_format(rules: Dict[str, Any]) -> bool:
    """
    Detect whether rules are in the clean 2-level format produced by
    export_validated.py: {category: {rule_name: value_or_enriched_dict}}.
    
    Heuristic: all top-level values are dicts, and at least some of their
    sub-values are enriched dicts (containing 'value' or 'test_hint' keys)
    or simple scalar/list values (not deeply nested category dicts).
    """
    if not rules or not all(isinstance(v, dict) for v in rules.values()):
        return False
    enriched_keys = {"value", "data_type", "test_hint", "source_quote", "unit"}
    for cat_fields in rules.values():
        for v in cat_fields.values():
            if isinstance(v, dict) and enriched_keys & set(v.keys()):
                return True
            if isinstance(v, (str, int, float, bool, list)):
                return True
    return False


def _flatten_clean_format(rules: Dict[str, Any]) -> List[tuple]:
    """Flatten clean {category: {rule_name: value}} format."""
    flattened = []
    for category, fields in rules.items():
        if not isinstance(fields, dict):
            continue
        for rule_name, rule_data in fields.items():
            full_key = f"{category}.{rule_name}"
            flattened.append((full_key, rule_data))
    return flattened


def _flatten_open_format(rules_list: List[Dict[str, Any]]) -> List[tuple]:
    """Flatten open-format rules list into (name, data) tuples."""
    flattened = []
    for rule in rules_list:
        if not rule.get("testable", True):
            continue

        name = rule.get("field_name") or rule.get("name", rule.get("id", "unknown"))
        category = rule.get("category", "")
        full_key = f"{category}.{name}" if category else name

        constraint = rule.get("constraint", {})
        data = {
            "name": rule.get("name", name),
            "constraint_type": constraint.get("type", "unknown"),
            "constraint_value": constraint.get("value"),
            "unit": constraint.get("unit"),
            "data_type": rule.get("data_type", "unknown"),
            "test_hint": rule.get("test_hint", ""),
            "source_quote": rule.get("source_quote", "")
        }

        if isinstance(constraint.get("value"), list):
            data["allowed_values"] = constraint["value"]
        elif isinstance(constraint.get("value"), (int, float)):
            data["value"] = constraint["value"]

        flattened.append((full_key, data))

    return flattened


def _flatten_legacy_format(rules: Dict[str, Any], prefix: str = "") -> List[tuple]:
    """Flatten legacy nested rule structure into (name, data) tuples."""
    flattened = []
    
    for key, value in rules.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            has_rule_indicators = any(
                indicator in value
                for indicator in ["min", "max", "allowed_values", "allowed_values_ms",
                                 "constraints", "range", "format", "must", "required",
                                 "constraint_type", "constraint_value"]
            )
            
            if has_rule_indicators:
                flattened.append((full_key, value))
            else:
                flattened.extend(_flatten_legacy_format(value, full_key))
        elif isinstance(value, list):
            flattened.append((full_key, value))
    
    return flattened


def merge_test_cases(all_test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge test cases from multiple LLM responses into a single structure.
    
    Args:
        all_test_cases: List of test case dictionaries from LLM
        
    Returns:
        Merged dictionary of all test cases
    """
    merged = {}
    
    for test_case_group in all_test_cases:
        for param_name, param_data in test_case_group.items():
            if param_name in merged:
                # Merge test cases for same parameter
                if "test_cases" in param_data and "test_cases" in merged[param_name]:
                    merged[param_name]["test_cases"].extend(param_data["test_cases"])
            else:
                merged[param_name] = param_data
    
    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Extract AFDX protocol violation test cases using LLM"
    )
    parser.add_argument(
        "--spec-file",
        default="configs/spec_rules.json",
        help="Path to specification rules JSON file"
    )
    parser.add_argument(
        "--output",
        default="configs/test_cases.json",
        help="Output file for extracted test cases"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation after extraction"
    )
    parser.add_argument(
        "--checkpoint",
        default="spec_extraction/test_case_extraction_checkpoint.jsonl",
        help="Checkpoint file for resuming extraction"
    )
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    os.makedirs(os.path.dirname(args.checkpoint), exist_ok=True)
    
    print("="*60)
    print("AFDX TEST CASE EXTRACTION")
    print("="*60)
    
    # Load specification rules
    print(f"\nLoading specification rules from: {args.spec_file}")
    spec_rules = load_spec_rules(args.spec_file)
    
    # Flatten rules
    flattened_rules = flatten_rules(spec_rules)
    print(f"Found {len(flattened_rules)} extractable rules")
    
    # Initialize LLM client
    print("\nInitializing LLM client...")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment")
        return 1
    
    model = os.getenv("TEST_CASE_MODEL", "gpt-4o")
    llm_client = LLMClient(api_key=api_key, model=model)
    print(f"Using model: {model}")
    
    # Load checkpoint if exists (for resume support)
    already_done = set()
    all_test_cases = []
    if os.path.exists(args.checkpoint):
        print(f"\nResuming from checkpoint: {args.checkpoint}")
        with open(args.checkpoint) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    already_done.add(entry["rule_name"])
                    if entry.get("test_cases"):
                        all_test_cases.append(entry["test_cases"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"  Loaded {len(already_done)} already-processed rules")

    # Extract test cases for each rule
    print("\nExtracting test cases...")
    
    for idx, (rule_name, rule_data) in enumerate(flattened_rules, 1):
        if rule_name in already_done:
            print(f"\n[{idx}/{len(flattened_rules)}] SKIP (done): {rule_name}")
            continue

        print(f"\n[{idx}/{len(flattened_rules)}] Processing: {rule_name}")
        
        test_cases = extract_test_cases_for_rule(
            llm_client,
            rule_name,
            rule_data,
            checkpoint_file=args.checkpoint
        )
        
        if test_cases:
            all_test_cases.append(test_cases)
            total_cases = sum(
                len(data.get("test_cases", []))
                for data in test_cases.values()
            )
            print(f"  Extracted {total_cases} test cases")
    
    # Merge all test cases
    print("\nMerging test cases...")
    merged_test_cases = merge_test_cases(all_test_cases)
    
    # Save to output file
    print(f"\nSaving test cases to: {args.output}")
    with open(args.output, 'w') as f:
        json.dump(merged_test_cases, f, indent=2)
    
    # Count total test cases
    total_test_cases = sum(
        len(data.get("test_cases", []))
        for data in merged_test_cases.values()
    )
    
    print(f"\nExtraction complete!")
    print(f"Total parameters with test cases: {len(merged_test_cases)}")
    print(f"Total test cases generated: {total_test_cases}")
    
    # Validate if requested
    if args.validate:
        print("\n" + "="*60)
        print("VALIDATION")
        print("="*60)
        
        validator = TestCaseValidator(spec_rules)
        validation_results = validator.validate_all(merged_test_cases)
        validator.print_summary()
        
        # Save validation results
        validation_file = args.output.replace(".json", "_validation.json")
        with open(validation_file, 'w') as f:
            json.dump(validation_results, f, indent=2)
        print(f"\nValidation results saved to: {validation_file}")
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)
    
    return 0


if __name__ == "__main__":
    exit(main())

