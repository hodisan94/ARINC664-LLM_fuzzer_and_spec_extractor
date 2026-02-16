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
    checkpoint_file: str = None
) -> Dict[str, Any]:
    """
    Extract test cases for a single rule using LLM.
    
    Args:
        llm_client: LLM client instance
        rule_name: Name of the rule
        rule_data: Rule specification data
        checkpoint_file: Optional checkpoint file for resuming
        
    Returns:
        Dictionary containing extracted test cases
    """
    print(f"\nExtracting test cases for: {rule_name}")
    
    # Generate prompt
    user_prompt = get_test_case_extraction_prompt(rule_name, rule_data)
    
    # Query LLM
    try:
        # Use query_json to automatically get JSON response
        test_cases = llm_client.query_json(
            system_prompt=SYSTEM_PROMPT_TEST_CASE_EXTRACTION,
            user_prompt=user_prompt
        )
        
        # Save checkpoint if specified
        if checkpoint_file:
            with open(checkpoint_file, 'a') as f:
                checkpoint_entry = {
                    "rule_name": rule_name,
                    "test_cases": test_cases
                }
                f.write(json.dumps(checkpoint_entry) + "\n")
        
        return test_cases
    
    except Exception as e:
        print(f"Error extracting test cases for {rule_name}: {e}")
        return {}


def flatten_rules(rules: Dict[str, Any], prefix: str = "") -> List[tuple]:
    """
    Flatten nested rule structure into a list of (name, data) tuples.
    
    Supports two formats:
    1. Legacy nested format: {"bag": {"allowed_values_ms": [...]}, ...}
    2. Open list format: {"rules": [{"id": "rule_001", "name": "...", ...}, ...]}
    
    Args:
        rules: Rules dictionary (either format)
        prefix: Current key prefix (for legacy format)
        
    Returns:
        List of (full_key_path, rule_data) tuples
    """
    # Detect open format
    if "rules" in rules and isinstance(rules["rules"], list):
        return _flatten_open_format(rules["rules"])

    # Legacy nested format
    return _flatten_legacy_format(rules, prefix)


def _flatten_open_format(rules_list: List[Dict[str, Any]]) -> List[tuple]:
    """Flatten open-format rules list into (name, data) tuples."""
    flattened = []
    for rule in rules_list:
        if not rule.get("testable", True):
            continue

        name = rule.get("field_name") or rule.get("name", rule.get("id", "unknown"))
        category = rule.get("category", "")
        full_key = f"{category}.{name}" if category else name

        # Build a data dict that the test case extractor can work with
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

        # Also include raw constraint fields for backward compatibility
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
    
    llm_client = LLMClient(api_key=api_key, model="gpt-5")
    
    # Extract test cases for each rule
    print("\nExtracting test cases...")
    all_test_cases = []
    
    for idx, (rule_name, rule_data) in enumerate(flattened_rules, 1):
        print(f"\n[{idx}/{len(flattened_rules)}] Processing: {rule_name}")
        
        test_cases = extract_test_cases_for_rule(
            llm_client,
            rule_name,
            rule_data,
            checkpoint_file=args.checkpoint
        )
        
        if test_cases:
            all_test_cases.append(test_cases)
            # Print summary of extracted test cases
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

