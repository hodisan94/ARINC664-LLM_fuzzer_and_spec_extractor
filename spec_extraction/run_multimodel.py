#!/usr/bin/env python3
"""
Multi-model extraction orchestrator.

Runs protocol rule extraction using multiple LLM providers (GPT, Claude, Gemini)
in parallel for cross-validation purposes.

Supports two extraction modes:
  --mode strict  : Legacy mode with predefined JSON schema (prompts_strict.py)
  --mode open    : New open-discovery mode where LLMs freely discover rules (prompts_open.py)

Usage:
    python3 run_multimodel.py --pdf configs/ARINC_664P7.pdf --mode open
    python3 run_multimodel.py --pdf configs/ARINC_664P7.pdf --mode strict  # legacy

Output:
    spec_extraction/multimodel_output/
    ├── rules_openai.json
    ├── rules_anthropic.json
    ├── rules_google.json
    └── extraction_summary.json
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spec_extraction.pdf_utils import get_all_relevant_text, chunk_text
from spec_extraction.llm_providers import (
    MultiModelClient, 
    ModelProvider, 
    BaseLLMProvider,
    get_single_provider
)

# Strict (legacy) prompts
from spec_extraction.prompts_strict import (
    SYSTEM_PROMPT_STRICT_EXTRACTION,
    SYSTEM_PROMPT_STRICT_AGGREGATION,
    get_strict_extraction_prompt,
    get_strict_aggregation_prompt
)

# Open discovery prompts
from spec_extraction.prompts_open import (
    SYSTEM_PROMPT_OPEN_EXTRACTION,
    SYSTEM_PROMPT_OPEN_AGGREGATION,
    get_open_extraction_prompt,
    get_open_aggregation_prompt
)


def _get_prompts(mode: str):
    """Return the appropriate prompt set based on extraction mode."""
    if mode == "open":
        return {
            "extraction_system": SYSTEM_PROMPT_OPEN_EXTRACTION,
            "aggregation_system": SYSTEM_PROMPT_OPEN_AGGREGATION,
            "extraction_user": get_open_extraction_prompt,
            "aggregation_user": get_open_aggregation_prompt,
        }
    else:
        return {
            "extraction_system": SYSTEM_PROMPT_STRICT_EXTRACTION,
            "aggregation_system": SYSTEM_PROMPT_STRICT_AGGREGATION,
            "extraction_user": get_strict_extraction_prompt,
            "aggregation_user": get_strict_aggregation_prompt,
        }


# Legacy aliases for backward compatibility
SYSTEM_PROMPT_RULE_EXTRACTION = SYSTEM_PROMPT_STRICT_EXTRACTION
SYSTEM_PROMPT_AGGREGATION = SYSTEM_PROMPT_STRICT_AGGREGATION
get_extraction_user_prompt = get_strict_extraction_prompt
get_aggregation_user_prompt = get_strict_aggregation_prompt


def extract_rules_with_provider(
    provider: BaseLLMProvider,
    provider_name: str,
    chapter_texts: Dict[str, str],
    checkpoint_dir: str,
    mode: str = "strict"
) -> Dict[str, Any]:
    """
    Extract rules using a single provider.
    
    Args:
        provider: LLM provider instance
        provider_name: Name for logging and checkpointing
        chapter_texts: Dictionary of chapter_name -> text
        checkpoint_dir: Directory for checkpoints
        mode: "strict" for legacy schema, "open" for free discovery
    
    Returns:
        Aggregated rules dictionary
    """
    prompts = _get_prompts(mode)

    print(f"\n{'='*60}")
    print(f"  Extracting with {provider_name.upper()} (mode: {mode})")
    print(f"{'='*60}")
    
    all_extractions = []
    provider_checkpoint_dir = os.path.join(checkpoint_dir, f"{provider_name}_{mode}")
    os.makedirs(provider_checkpoint_dir, exist_ok=True)
    
    for chapter_name, chapter_text in chapter_texts.items():
        print(f"\n  {chapter_name}")
        
        chunks = chunk_text(chapter_text, max_chars=6000)
        print(f"     Split into {len(chunks)} chunks")
        
        chapter_extractions = []
        
        for i, chunk in enumerate(chunks):
            checkpoint_file = os.path.join(
                provider_checkpoint_dir,
                f"{chapter_name.replace('/', '_').replace(' ', '_')}_chunk_{i}.json"
            )
            
            if os.path.exists(checkpoint_file):
                print(f"     Chunk {i+1}/{len(chunks)}: loaded from checkpoint")
                with open(checkpoint_file, 'r') as f:
                    extraction = json.load(f)
            else:
                print(f"     Chunk {i+1}/{len(chunks)}: extracting...", end=" ", flush=True)
                try:
                    user_prompt = prompts["extraction_user"](
                        chapter_name, chunk, i, len(chunks)
                    )
                    
                    extraction = provider.query_json(
                        system_prompt=prompts["extraction_system"],
                        user_prompt=user_prompt,
                        temperature=0.3,
                        max_tokens=4096
                    )
                    
                    # Save checkpoint
                    with open(checkpoint_file, 'w') as f:
                        json.dump(extraction, f, indent=2)
                    
                    print("done")
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    print(f"Error: {e}")
                    extraction = {"error": str(e)}
            
            chapter_extractions.append({
                "chapter": chapter_name,
                "chunk_index": i,
                "extraction": extraction
            })
        
        all_extractions.extend(chapter_extractions)
    
    # Aggregate all extractions
    print(f"\n  Aggregating {len(all_extractions)} extractions...")
    
    rule_dicts = [
        item["extraction"] 
        for item in all_extractions 
        if "error" not in item.get("extraction", {})
    ]
    
    try:
        aggregation_prompt = prompts["aggregation_user"](rule_dicts)
        
        final_rules = provider.query_json(
            system_prompt=prompts["aggregation_system"],
            user_prompt=aggregation_prompt,
            temperature=0.3,
            max_tokens=8000
        )
        
        print(f"  Aggregation complete")
        return final_rules
        
    except Exception as e:
        print(f"  Aggregation failed: {e}")
        # For open mode, try to merge without LLM
        if mode == "open":
            return _merge_open_extractions_locally(rule_dicts, provider_name)
        return {
            "note": f"Aggregation failed for {provider_name}",
            "error": str(e),
            "raw_extractions": rule_dicts[:10]
        }


def _merge_open_extractions_locally(
    rule_dicts: List[Dict[str, Any]],
    provider_name: str
) -> Dict[str, Any]:
    """
    Merge open-format extractions locally when LLM aggregation fails.
    Simply concatenates all rules and renumbers them.
    """
    print(f"  Falling back to local merge for {provider_name}...")
    all_rules = []
    seen_fields = set()

    for chunk_data in rule_dicts:
        for rule in chunk_data.get("rules", []):
            # Basic dedup by field_name + category
            dedup_key = f"{rule.get('category','')}/{rule.get('field_name','')}"
            if dedup_key not in seen_fields:
                seen_fields.add(dedup_key)
                all_rules.append(rule)

    # Renumber
    for i, rule in enumerate(all_rules):
        rule["id"] = f"rule_{i+1:03d}"

    categories = list(set(r.get("category", "unknown") for r in all_rules))
    testable = sum(1 for r in all_rules if r.get("testable", False))

    return {
        "rules": all_rules,
        "extraction_stats": {
            "total_rules": len(all_rules),
            "categories_found": categories,
            "testable_rules": testable,
            "note": "Aggregated locally (LLM aggregation failed)"
        }
    }


def run_multimodel_extraction(
    pdf_path: str,
    output_dir: str,
    providers: Optional[List[str]] = None,
    parallel: bool = False,
    mode: str = "strict"
) -> Dict[str, Any]:
    """
    Run extraction with multiple LLM providers.
    
    Args:
        pdf_path: Path to ARINC 664 Part 7 PDF
        output_dir: Output directory for results
        providers: List of provider names to use (default: all available)
        parallel: Run extractions in parallel (default: sequential)
        mode: "strict" for predefined schema, "open" for free discovery
    
    Returns:
        Summary dictionary with results and metadata
    """
    start_time = datetime.now()
    os.makedirs(output_dir, exist_ok=True)
    checkpoint_dir = os.path.join(output_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    print("=" * 70)
    print("  MULTI-MODEL PROTOCOL RULE EXTRACTION")
    print("=" * 70)
    print(f"  PDF: {pdf_path}")
    print(f"  Output: {output_dir}")
    print(f"  Execution: {'Parallel' if parallel else 'Sequential'}")
    print(f"  Extraction mode: {mode.upper()}")
    if mode == "open":
        print(f"  (LLMs freely discover and categorize rules)")
    else:
        print(f"  (LLMs fill predefined JSON schema)")
    print("=" * 70)
    
    # Initialize providers
    print("\n📡 Initializing LLM providers...")
    
    if providers:
        target_providers = [ModelProvider(p) for p in providers]
    else:
        target_providers = list(ModelProvider)
    
    client = MultiModelClient(providers=target_providers)
    available = client.get_available_providers()
    
    if len(available) < 2:
        print("\n⚠️  Warning: Less than 2 providers available.")
        print("   Cross-validation requires at least 2 providers.")
        print("   Make sure API keys are set in environment variables:")
        print("   - OPENAI_API_KEY")
        print("   - ANTHROPIC_API_KEY")
        print("   - GOOGLE_API_KEY")
    
    # Extract text from PDF
    print(f"\n📄 Extracting text from PDF...")
    chapter_texts = get_all_relevant_text(pdf_path)
    print(f"   Found {len(chapter_texts)} chapters")
    
    # Run extraction for each provider
    results = {}
    
    if parallel and len(available) > 1:
        # Parallel execution
        print(f"\n  Running parallel extraction with {len(available)} providers...")
        
        with ThreadPoolExecutor(max_workers=len(available)) as executor:
            futures = {}
            
            for provider in available:
                provider_instance = client.providers[provider]
                future = executor.submit(
                    extract_rules_with_provider,
                    provider_instance,
                    provider.value,
                    chapter_texts,
                    checkpoint_dir,
                    mode
                )
                futures[future] = provider.value
            
            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    results[provider_name] = future.result()
                except Exception as e:
                    print(f"  {provider_name} failed: {e}")
                    results[provider_name] = {"error": str(e)}
    else:
        # Sequential execution
        for provider in available:
            provider_instance = client.providers[provider]
            try:
                results[provider.value] = extract_rules_with_provider(
                    provider_instance,
                    provider.value,
                    chapter_texts,
                    checkpoint_dir,
                    mode
                )
            except Exception as e:
                print(f"  {provider.value} failed: {e}")
                results[provider.value] = {"error": str(e)}
    
    # Save individual results
    print(f"\n💾 Saving results...")
    
    for provider_name, rules in results.items():
        output_file = os.path.join(output_dir, f"rules_{provider_name}.json")
        with open(output_file, 'w') as f:
            json.dump(rules, f, indent=2)
        print(f"   ✓ {output_file}")
    
    # Create summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Mode-specific next steps
    if mode == "open":
        next_steps = [
            "Run align_rules.py to semantically align rules across models",
            "Run align_rules.py --verify-unique to verify rules found by only one model",
            "Run export_validated.py --mode open to generate final validated rules"
        ]
    else:
        next_steps = [
            "Run compare_extractions.py to analyze agreement between models",
            "Run arbitrate_conflicts.py if there are significant disagreements",
            "Run export_validated.py to generate final validated rules"
        ]

    summary = {
        "metadata": {
            "pdf_path": pdf_path,
            "extraction_date": start_time.isoformat(),
            "duration_seconds": duration,
            "extraction_mode": mode,
            "providers_used": [p for p in results.keys() if "error" not in results[p]],
            "providers_failed": [p for p in results.keys() if "error" in results[p]]
        },
        "files_generated": {
            provider: f"rules_{provider}.json"
            for provider in results.keys()
        },
        "next_steps": next_steps
    }
    
    summary_file = os.path.join(output_dir, "extraction_summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"   ✓ {summary_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("  EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"  Duration: {duration:.1f} seconds")
    print(f"  Successful: {len(summary['metadata']['providers_used'])} providers")
    print(f"  Failed: {len(summary['metadata']['providers_failed'])} providers")
    print(f"  Output directory: {output_dir}")
    print("=" * 70)
    
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract protocol rules using multiple LLM providers"
    )
    parser.add_argument(
        "--pdf",
        default="configs/ARINC_664P7.pdf",
        help="Path to ARINC 664 Part 7 PDF"
    )
    parser.add_argument(
        "--output-dir",
        default="spec_extraction/multimodel_output",
        help="Output directory for results"
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=["openai", "anthropic", "google"],
        help="Specific providers to use (default: all available)"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run extractions in parallel"
    )
    parser.add_argument(
        "--mode",
        choices=["strict", "open"],
        default="open",
        help="Extraction mode: 'strict' uses predefined schema, 'open' lets LLMs freely discover rules (default: open)"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)
    
    run_multimodel_extraction(
        pdf_path=args.pdf,
        output_dir=args.output_dir,
        providers=args.providers,
        parallel=args.parallel,
        mode=args.mode
    )

