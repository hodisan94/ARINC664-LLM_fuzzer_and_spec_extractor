#!/usr/bin/env python3
"""
Compute Rule Completeness: fraction of normative requirements in
ARINC 664 Part 7 that are covered by at least one extracted rule.

Approach:
  1. Ask the LLM to enumerate all major normative requirements from the
     ARINC 664 Part 7 specification (grouped by section).
  2. For each requirement, check whether our spec_rules_filtered.json
     contains a matching rule (using LLM-based matching).
  3. Compute: Completeness = #covered / #total_requirements

Results are cached in evaluation/results/rule_completeness.json.

Usage:
    python3 evaluation/compute_rule_completeness.py [--model gpt-4o-mini]
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

CACHE_PATH = RESULTS_DIR / "rule_completeness.json"
SPEC_RULES_PATH = CONFIGS_DIR / "spec_rules_filtered.json"


def load_spec_rules() -> dict:
    with open(SPEC_RULES_PATH) as f:
        return json.load(f)


def call_llm(client, model: str, prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    Retry {attempt+1}/{retries} after error: {e} (waiting {wait}s)")
                time.sleep(wait)
            else:
                raise
    return "{}"


def enumerate_requirements(client, model: str) -> list[dict]:
    """Ask the LLM to enumerate major normative requirements from ARINC 664 Part 7.
    
    Two-pass approach: first enumerate by section, then fill gaps from
    a cross-check pass to reach better coverage.
    """
    pass1_prompt = """You are an avionics protocol expert with deep knowledge of 
ARINC Specification 664 Part 7 (AFDX - Avionics Full Duplex Switched Ethernet).

Enumerate ALL normative requirements ("shall", "must", "should") from 
ARINC 664 Part 7 that a compliant AFDX implementation must satisfy. 

Go section by section through the specification. The main sections are:
  2.1 - Physical Layer & Ethernet
  2.2 - End System (transmit side: traffic shaping, BAG enforcement, sub-VL scheduling)
  2.3 - End System (receive side: frame filtering, policing, integrity checking, redundancy management)
  2.4 - Virtual Links (definition, single-source constraint, bandwidth allocation)
  2.5 - Switching (filtering, policing, forwarding, buffering, priority, latency)
  2.6 - Frame format (MAC addressing, IP/UDP encapsulation, payload structure)
  2.7 - Network configuration (OPS files, switch modes, port configuration)
  2.8 - Quality of Service (latency guarantees, jitter bounds, fault isolation)
  2.9 - IP/TCP optional services (IP addressing, ICMP, TCP connections)
  2.10 - Redundancy (dual-lane, sequence numbering, first-valid-wins)
  2.11 - Communication ports (queuing, sampling, SAP ports)
  2.12 - Error handling

For each requirement, provide:
  - id: a short identifier (section_number.requirement_name)
  - section: the section name
  - description: one sentence stating what must be done

Return JSON: {"requirements": [{"id":"...", "section":"...", "description":"..."}]}

Be EXHAUSTIVE. Aim for 80-120 requirements. Include requirements about:
  - Frame size limits (min, max, Lmax per VL)
  - MAC address format (destination: group bit, locally administered bit; source format)
  - BAG values and enforcement
  - Sequence number range and wrap-around
  - Policing algorithms (byte-based, frame-based)
  - Switch latency bounds
  - Port speed requirements
  - IP header fields (TTL, checksum, version)
  - Fragmentation handling
  - Sub-VL FIFO constraints
  - Configuration file requirements
  - Error reporting mechanisms"""

    text = call_llm(client, model, pass1_prompt)
    parsed = json.loads(text)
    reqs = parsed.get("requirements", [])
    if not reqs:
        for v in parsed.values():
            if isinstance(v, list):
                reqs = v
                break
    
    if len(reqs) < 60:
        pass2_prompt = f"""You previously enumerated {len(reqs)} requirements from ARINC 664 Part 7.
Here are their IDs:
{chr(10).join(f"  - {r['id']}" for r in reqs)}

Many requirements are still missing. Please enumerate ADDITIONAL requirements 
that are NOT in the list above. Focus on:
  - Detailed MAC address bit-field requirements
  - IP/UDP encapsulation requirements
  - Specific policing algorithm constraints
  - Switch configuration table requirements
  - Communication port (queuing/sampling) detailed rules
  - TCP optional service constraints
  - Specific error-handling requirements
  - Sub-VL scheduling details
  - Network management interface requirements

Return JSON: {{"requirements": [{{"id":"...", "section":"...", "description":"..."}}]}}
Aim for 30-50 additional requirements."""

        text2 = call_llm(client, model, pass2_prompt)
        parsed2 = json.loads(text2)
        reqs2 = parsed2.get("requirements", [])
        if not reqs2:
            for v in parsed2.values():
                if isinstance(v, list):
                    reqs2 = v
                    break
        
        existing_ids = {r["id"] for r in reqs}
        for r in reqs2:
            if r["id"] not in existing_ids:
                reqs.append(r)
                existing_ids.add(r["id"])
    
    return reqs


def match_requirements_to_rules(
    client, model: str, requirements: list[dict], rule_categories: list[str]
) -> list[dict]:
    """Ask the LLM to match each requirement to extracted rules."""
    categories_str = "\n".join(f"  - {c}" for c in sorted(rule_categories))

    BATCH_SIZE = 15
    all_results = []

    for i in range(0, len(requirements), BATCH_SIZE):
        batch = requirements[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(requirements) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Matching batch {batch_num}/{total_batches} ({len(batch)} requirements)...")

        reqs_str = ""
        for j, req in enumerate(batch, 1):
            reqs_str += f"\n{j}. [{req['id']}] {req['description']}"

        prompt = f"""You are matching ARINC 664 Part 7 requirements to extracted rules.

Here are the rule categories that were extracted from the spec:
{categories_str}

For each requirement below, determine if it is COVERED by one or more 
of the extracted rule categories above, or NOT COVERED.

A requirement is "covered" if any of the rule categories addresses the 
same concern, even if the name differs slightly. Be generous in matching 
— if the concept is captured, it counts as covered.

Requirements:{reqs_str}

Return a JSON object with key "matches" containing an array with one entry 
per requirement:
[{{"id": "...", "covered": true/false, "matching_category": "name or null", 
   "reason": "one-line explanation"}}]"""

        text = call_llm(client, model, prompt)
        parsed = json.loads(text)
        results = parsed.get("matches", [])
        if not results:
            for v in parsed.values():
                if isinstance(v, list):
                    results = v
                    break

        for j, req in enumerate(batch):
            if j < len(results):
                req["covered"] = results[j].get("covered", False)
                req["matching_category"] = results[j].get("matching_category")
                req["match_reason"] = results[j].get("reason", "")
            else:
                req["covered"] = False
                req["matching_category"] = None
                req["match_reason"] = "No LLM response for this requirement"
            all_results.append(req)

        time.sleep(0.5)

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Compute Rule Completeness")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--force", action="store_true", help="Re-run from scratch")
    args = parser.parse_args()

    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    spec = load_spec_rules()
    categories = list(spec.keys())
    print(f"Loaded {len(categories)} rule categories from {SPEC_RULES_PATH.name}")

    cache = {}
    if CACHE_PATH.exists() and not args.force:
        with open(CACHE_PATH) as f:
            cache = json.load(f)

    if "requirements" in cache and not args.force:
        requirements = cache["requirements"]
        print(f"Using cached {len(requirements)} requirements")
    else:
        print("Enumerating normative requirements from ARINC 664 Part 7...")
        requirements = enumerate_requirements(client, args.model)
        print(f"  Found {len(requirements)} requirements")
        cache["requirements"] = requirements
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    if "matched_requirements" in cache and not args.force:
        matched = cache["matched_requirements"]
        print(f"Using cached matching results ({len(matched)} requirements)")
    else:
        print("Matching requirements to extracted rules...")
        matched = match_requirements_to_rules(client, args.model, requirements, categories)
        cache["matched_requirements"] = matched
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    covered = sum(1 for r in matched if r.get("covered", False))
    not_covered = sum(1 for r in matched if not r.get("covered", False))
    total = len(matched)
    completeness = covered / total if total > 0 else 0

    report = {
        "metric": "Rule Completeness",
        "formula": "#spec_requirements_covered / #total_spec_requirements",
        "total_spec_requirements": total,
        "covered_by_extracted_rules": covered,
        "not_covered": not_covered,
        "completeness": round(completeness, 4),
        "completeness_percent": f"{completeness * 100:.1f}%",
        "model_used": args.model,
        "extracted_rule_categories": len(categories),
        "requirements": matched,
    }

    cache.update(report)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"RULE COMPLETENESS")
    print(f"{'='*60}")
    print(f"  Spec requirements found:   {total}")
    print(f"  Covered by our rules:      {covered}")
    print(f"  Not covered:               {not_covered}")
    print(f"  Completeness:              {completeness * 100:.1f}%")
    print(f"  (Our extracted categories: {len(categories)})")
    print(f"\n  Report saved: {CACHE_PATH}")

    if not_covered > 0:
        print(f"\n  Uncovered requirements (first 15):")
        uncovered = [r for r in matched if not r.get("covered", False)]
        for r in uncovered[:15]:
            print(f"    - [{r['id']}] {r['description']}")
        if len(uncovered) > 15:
            print(f"    ... and {len(uncovered) - 15} more")


if __name__ == "__main__":
    main()
