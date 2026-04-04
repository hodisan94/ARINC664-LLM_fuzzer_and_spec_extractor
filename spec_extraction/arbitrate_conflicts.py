#!/usr/bin/env python3
"""
Arbitrate conflicts between LLM extractions using a neutral judge.

When multiple LLMs disagree on a rule extraction, this script uses
an independent LLM (or panel of LLMs) to determine the correct interpretation
based on the original specification text.

Usage:
    python3 arbitrate_conflicts.py \
        --comparison comparison_results.json \
        --pdf ARINC_664P7.pdf \
        --output arbitration_results.json

Output:
    arbitration_results.json with resolved conflicts and justifications
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spec_extraction.pdf_utils import get_all_relevant_text
from spec_extraction.llm_providers import MultiModelClient, ModelProvider


# Arbitration prompts
SYSTEM_PROMPT_ARBITRATOR = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

You are acting as a neutral arbitrator to resolve disagreements between different AI systems 
that extracted protocol rules from the specification.

Your task is to:
1. Carefully read the relevant specification text
2. Review the conflicting interpretations from different AI systems
3. Determine which interpretation is correct (or provide the correct interpretation if all are wrong)
4. Provide clear justification citing the specification

Be precise and objective. Base your decision ONLY on what the specification text says.
If the specification is ambiguous or doesn't clearly specify something, indicate that.

Always respond in JSON format:
{
    "decision": "The correct value/interpretation",
    "confidence": "high/medium/low",
    "justification": "Explanation citing specific text from the specification",
    "source_quote": "Direct quote from spec supporting the decision (if available)",
    "notes": "Any additional context or caveats"
}
"""


def get_arbitration_prompt(
    rule_path: str,
    conflicting_values: Dict[str, Any],
    relevant_text: str
) -> str:
    """Generate prompt for arbitrating a specific conflict."""
    
    values_text = "\n".join([
        f"  - {provider}: {json.dumps(value, indent=4)}"
        for provider, value in conflicting_values.items()
    ])
    
    return f"""Please arbitrate the following conflict in protocol rule extraction.

RULE PATH: {rule_path}

CONFLICTING EXTRACTIONS:
{values_text}

RELEVANT SPECIFICATION TEXT:
---
{relevant_text}
---

Based on the specification text above, determine the correct interpretation for "{rule_path}".
If the specification doesn't clearly define this, indicate that with confidence "low".

Respond in JSON format with: decision, confidence, justification, source_quote, notes
"""


def find_relevant_text(rule_path: str, chapter_texts: Dict[str, str]) -> str:
    """
    Find the most relevant specification text for a given rule path.
    
    Uses keyword matching to find relevant sections.
    """
    # Extract keywords from rule path
    keywords = rule_path.lower().replace("_", " ").replace(".", " ").split()
    
    # Add domain-specific keywords
    keyword_mapping = {
        "bag": ["bandwidth allocation gap", "bag", "bagi"],
        "lmin": ["minimum", "frame length", "64 bytes"],
        "lmax": ["maximum", "frame length", "1518"],
        "sequence": ["sequence number", "rsn", "redundancy"],
        "redundancy": ["network a", "network b", "dual", "redundant"],
        "priority": ["high priority", "low priority", "qos"],
        "policing": ["traffic policing", "filtering", "drop"],
        "virtual_link": ["virtual link", "vl", "vli"],
        "mac": ["mac address", "destination mac", "ethernet"],
        "ip": ["ip header", "internet protocol", "ipv4"],
        "udp": ["udp", "user datagram"],
        "ttl": ["time to live", "ttl", "aging"],
        "buffer": ["buffer", "queue", "overflow"],
        "switch": ["switch", "forwarding", "switching function"],
        "monitoring": ["monitoring", "mib", "snmp", "statistics"]
    }
    
    # Expand keywords
    expanded_keywords = set(keywords)
    for keyword in keywords:
        if keyword in keyword_mapping:
            expanded_keywords.update(keyword_mapping[keyword])
    
    # Score each chapter
    chapter_scores = {}
    for chapter_name, text in chapter_texts.items():
        text_lower = text.lower()
        score = sum(1 for kw in expanded_keywords if kw in text_lower)
        chapter_scores[chapter_name] = score
    
    # Get best matching chapter
    if not chapter_scores:
        return "No relevant text found in specification."
    
    best_chapter = max(chapter_scores, key=chapter_scores.get)
    
    # Extract relevant portion (limit size for LLM context)
    text = chapter_texts[best_chapter]
    
    # Try to find most relevant paragraph
    paragraphs = text.split("\n\n")
    scored_paragraphs = []
    
    for para in paragraphs:
        para_lower = para.lower()
        score = sum(1 for kw in expanded_keywords if kw in para_lower)
        if score > 0:
            scored_paragraphs.append((score, para))
    
    # Return top paragraphs (up to 2000 chars)
    scored_paragraphs.sort(reverse=True)
    
    result = []
    total_len = 0
    for score, para in scored_paragraphs[:10]:
        if total_len + len(para) > 2000:
            break
        result.append(para)
        total_len += len(para)
    
    if result:
        return f"[From: {best_chapter}]\n\n" + "\n\n".join(result)
    else:
        # Return first portion of best chapter
        return f"[From: {best_chapter}]\n\n" + text[:2000]


@dataclass
class ArbitrationResult:
    """Result of arbitrating a single conflict."""
    rule_path: str
    original_values: Dict[str, Any]
    decision: Any
    confidence: str
    justification: str
    source_quote: str
    notes: str
    arbitrator: str  # Which LLM made the decision


def arbitrate_conflict(
    client: MultiModelClient,
    rule_path: str,
    conflicting_values: Dict[str, Any],
    chapter_texts: Dict[str, str],
    arbitrator_provider: Optional[ModelProvider] = None
) -> ArbitrationResult:
    """
    Arbitrate a single conflict using an LLM.
    
    Args:
        client: Multi-model client
        rule_path: Path of the conflicting rule
        conflicting_values: Dictionary of provider -> value
        chapter_texts: PDF text by chapter
        arbitrator_provider: Specific provider to use as arbitrator
    
    Returns:
        ArbitrationResult with decision and justification
    """
    # Find relevant specification text
    relevant_text = find_relevant_text(rule_path, chapter_texts)
    
    # Generate arbitration prompt
    prompt = get_arbitration_prompt(rule_path, conflicting_values, relevant_text)
    
    # Choose arbitrator (prefer one not involved in the conflict, or use default)
    available = client.get_available_providers()
    
    if arbitrator_provider and arbitrator_provider in available:
        arbitrator = arbitrator_provider
    else:
        # Try to find a provider not involved in the conflict
        conflict_providers = set(conflicting_values.keys())
        neutral = [p for p in available if p.value not in conflict_providers]
        
        if neutral:
            arbitrator = neutral[0]
        else:
            # Use first available
            arbitrator = available[0] if available else None
    
    if not arbitrator:
        return ArbitrationResult(
            rule_path=rule_path,
            original_values=conflicting_values,
            decision=None,
            confidence="low",
            justification="No LLM available for arbitration",
            source_quote="",
            notes="Failed to arbitrate - no providers available",
            arbitrator="none"
        )
    
    # Query arbitrator
    try:
        response = client.query_json(
            provider=arbitrator,
            system_prompt=SYSTEM_PROMPT_ARBITRATOR,
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=1000
        )
        
        return ArbitrationResult(
            rule_path=rule_path,
            original_values=conflicting_values,
            decision=response.get("decision"),
            confidence=response.get("confidence", "medium"),
            justification=response.get("justification", ""),
            source_quote=response.get("source_quote", ""),
            notes=response.get("notes", ""),
            arbitrator=arbitrator.value
        )
        
    except Exception as e:
        return ArbitrationResult(
            rule_path=rule_path,
            original_values=conflicting_values,
            decision=None,
            confidence="low",
            justification=f"Arbitration failed: {str(e)}",
            source_quote="",
            notes="Error during arbitration",
            arbitrator=arbitrator.value
        )


def arbitrate_all_conflicts(
    comparison_path: str,
    pdf_path: str,
    output_path: str,
    arbitrator: Optional[str] = None
) -> Dict[str, Any]:
    """
    Arbitrate all conflicts from a comparison report.
    
    Args:
        comparison_path: Path to comparison_results.json
        pdf_path: Path to ARINC 664 Part 7 PDF
        output_path: Path to save arbitration results
        arbitrator: Specific provider to use as arbitrator
    
    Returns:
        Arbitration results dictionary
    """
    print("=" * 70)
    print("  CONFLICT ARBITRATION")
    print("=" * 70)
    
    # Load comparison results
    print("\n📄 Loading comparison results...")
    with open(comparison_path, 'r') as f:
        comparison = json.load(f)
    
    conflicts = comparison.get("needs_arbitration", [])
    print(f"   Found {len(conflicts)} conflicts to arbitrate")
    
    if not conflicts:
        print("\n✓ No conflicts to arbitrate!")
        return {"message": "No conflicts found", "arbitrations": []}
    
    # Load PDF text
    print(f"\n📄 Loading specification text from {pdf_path}...")
    chapter_texts = get_all_relevant_text(pdf_path)
    print(f"   Loaded {len(chapter_texts)} chapters")
    
    # Initialize LLM client
    print("\n📡 Initializing LLM client...")
    client = MultiModelClient()
    
    arbitrator_provider = None
    if arbitrator:
        arbitrator_provider = ModelProvider(arbitrator)
    
    # Arbitrate each conflict
    print(f"\n⚖️  Arbitrating {len(conflicts)} conflicts...")
    
    results = []
    for i, conflict in enumerate(conflicts):
        rule_path = conflict["path"]
        values = conflict["values"]
        
        print(f"\n   [{i+1}/{len(conflicts)}] {rule_path}")
        print(f"       Conflicting values: {list(values.keys())}")
        
        result = arbitrate_conflict(
            client=client,
            rule_path=rule_path,
            conflicting_values=values,
            chapter_texts=chapter_texts,
            arbitrator_provider=arbitrator_provider
        )
        
        results.append(asdict(result))
        
        print(f"       Decision: {result.decision}")
        print(f"       Confidence: {result.confidence}")
        print(f"       Arbitrator: {result.arbitrator}")
    
    # Build output
    output = {
        "summary": {
            "total_conflicts": len(conflicts),
            "arbitrated": len([r for r in results if r["decision"] is not None]),
            "failed": len([r for r in results if r["decision"] is None]),
            "high_confidence": len([r for r in results if r["confidence"] == "high"]),
            "medium_confidence": len([r for r in results if r["confidence"] == "medium"]),
            "low_confidence": len([r for r in results if r["confidence"] == "low"])
        },
        "arbitrations": results
    }
    
    # Save results
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    # Print summary
    print("\n" + "=" * 70)
    print("  ARBITRATION COMPLETE")
    print("=" * 70)
    print(f"\n  Total conflicts: {output['summary']['total_conflicts']}")
    print(f"  Successfully arbitrated: {output['summary']['arbitrated']}")
    print(f"  Failed: {output['summary']['failed']}")
    print(f"\n  Confidence levels:")
    print(f"     🟢 High: {output['summary']['high_confidence']}")
    print(f"     🟡 Medium: {output['summary']['medium_confidence']}")
    print(f"     🔴 Low: {output['summary']['low_confidence']}")
    print(f"\n  📄 Results saved to: {output_path}")
    print("=" * 70)
    
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Arbitrate conflicts between LLM extractions"
    )
    parser.add_argument(
        "--comparison",
        default="spec_extraction/comparison_results.json",
        help="Path to comparison results JSON"
    )
    parser.add_argument(
        "--pdf",
        default="configs/ARINC_664P7.pdf",
        help="Path to ARINC 664 Part 7 PDF"
    )
    parser.add_argument(
        "--output",
        default="spec_extraction/arbitration_results.json",
        help="Output path for arbitration results"
    )
    parser.add_argument(
        "--arbitrator",
        choices=["openai", "anthropic", "mistral"],
        help="Specific provider to use as arbitrator"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.comparison):
        print(f"Error: Comparison file not found: {args.comparison}")
        sys.exit(1)
    
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)
    
    arbitrate_all_conflicts(
        comparison_path=args.comparison,
        pdf_path=args.pdf,
        output_path=args.output,
        arbitrator=args.arbitrator
    )

