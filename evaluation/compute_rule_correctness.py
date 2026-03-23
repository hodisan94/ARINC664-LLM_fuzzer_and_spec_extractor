#!/usr/bin/env python3
"""
Compute Rule Correctness: fraction of extracted rules whose constraints
are accurate with respect to the ARINC 664 Part 7 specification.

Uses an LLM to validate each rule against the spec (source_quote when
available, general spec knowledge otherwise).  Results are cached in
evaluation/results/rule_correctness.json so re-runs skip already-judged
rules.

Usage:
    python3 evaluation/compute_rule_correctness.py [--model gpt-4o-mini]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"
RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CACHE_PATH = RESULTS_DIR / "rule_correctness.json"
SPEC_RULES_PATH = CONFIGS_DIR / "spec_rules_filtered.json"

BATCH_SIZE = 5


def load_spec_rules() -> dict:
    with open(SPEC_RULES_PATH) as f:
        return json.load(f)


def flatten_rules(spec: dict) -> list[dict]:
    """Flatten the hierarchical spec into a list of individual rules."""
    flat = []
    for category, items in spec.items():
        if isinstance(items, dict):
            for sub_rule, value in items.items():
                entry = {
                    "category": category,
                    "sub_rule": sub_rule,
                    "key": f"{category}.{sub_rule}",
                }
                if isinstance(value, dict):
                    entry["value"] = value.get("value", str(value))
                    entry["source_quote"] = value.get("source_quote", "")
                    entry["data_type"] = value.get("data_type", "")
                    entry["test_hint"] = value.get("test_hint", "")
                else:
                    entry["value"] = str(value)
                    entry["source_quote"] = ""
                flat.append(entry)
        else:
            flat.append({
                "category": category,
                "sub_rule": "",
                "key": category,
                "value": str(items),
                "source_quote": "",
            })
    return flat


def build_validation_prompt(batch: list[dict]) -> str:
    lines = [
        "You are an avionics protocol expert validating extracted rules from "
        "ARINC Specification 664 Part 7 (AFDX).\n",
        "For each rule below, judge whether the extracted constraint is "
        "**correct** (accurately reflects the ARINC 664 Part 7 specification), "
        "**incorrect** (contradicts the spec or contains a factual error), "
        "or **unverifiable** (cannot be confirmed from the spec alone).\n",
        "Return a JSON array with one object per rule in the same order:",
        '  [{"key": "...", "verdict": "correct|incorrect|unverifiable", '
        '"reason": "one-line explanation"}]\n',
        "Rules to validate:\n",
    ]
    for i, rule in enumerate(batch, 1):
        lines.append(f"--- Rule {i} ---")
        lines.append(f"Key: {rule['key']}")
        lines.append(f"Extracted value: {rule['value']}")
        if rule.get("source_quote"):
            lines.append(f"Source quote from spec: \"{rule['source_quote']}\"")
        if rule.get("data_type"):
            lines.append(f"Data type: {rule['data_type']}")
        lines.append("")

    return "\n".join(lines)


def call_llm(client, model: str, prompt: str, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content.strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        return v
            return [parsed]
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    Retry {attempt+1}/{retries} after error: {e} (waiting {wait}s)")
                time.sleep(wait)
            else:
                raise
    return []


def load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(data: dict):
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Compute Rule Correctness")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--force", action="store_true", help="Re-validate all rules")
    args = parser.parse_args()

    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    spec = load_spec_rules()
    rules = flatten_rules(spec)
    print(f"Loaded {len(rules)} rules from {SPEC_RULES_PATH.name}")

    cache = {} if args.force else load_cache()
    verdicts = cache.get("verdicts", {})

    to_validate = [r for r in rules if r["key"] not in verdicts]
    print(f"Already validated: {len(verdicts)}, remaining: {len(to_validate)}")

    for i in range(0, len(to_validate), BATCH_SIZE):
        batch = to_validate[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(to_validate) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} rules)...")

        prompt = build_validation_prompt(batch)
        results = call_llm(client, args.model, prompt)

        for j, rule in enumerate(batch):
            if j < len(results):
                verdicts[rule["key"]] = {
                    "verdict": results[j].get("verdict", "unverifiable"),
                    "reason": results[j].get("reason", ""),
                }
            else:
                verdicts[rule["key"]] = {
                    "verdict": "unverifiable",
                    "reason": "LLM response did not include this rule",
                }

        save_cache({"verdicts": verdicts})
        time.sleep(0.5)

    correct = sum(1 for v in verdicts.values() if v["verdict"] == "correct")
    incorrect = sum(1 for v in verdicts.values() if v["verdict"] == "incorrect")
    unverifiable = sum(1 for v in verdicts.values() if v["verdict"] == "unverifiable")
    total = len(verdicts)

    correctness = correct / total if total > 0 else 0

    report = {
        "metric": "Rule Correctness",
        "formula": "#correctly_extracted_rules / #total_extracted_rules",
        "total_rules": total,
        "correct": correct,
        "incorrect": incorrect,
        "unverifiable": unverifiable,
        "correctness": round(correctness, 4),
        "correctness_percent": f"{correctness * 100:.1f}%",
        "model_used": args.model,
        "verdicts": verdicts,
    }

    save_cache(report)
    print(f"\n{'='*60}")
    print(f"RULE CORRECTNESS")
    print(f"{'='*60}")
    print(f"  Total rules:   {total}")
    print(f"  Correct:       {correct}")
    print(f"  Incorrect:     {incorrect}")
    print(f"  Unverifiable:  {unverifiable}")
    print(f"  Correctness:   {correctness * 100:.1f}%")
    print(f"\n  Report saved: {CACHE_PATH}")

    if incorrect > 0:
        print(f"\n  Incorrect rules:")
        for key, v in verdicts.items():
            if v["verdict"] == "incorrect":
                print(f"    - {key}: {v['reason']}")


if __name__ == "__main__":
    main()
