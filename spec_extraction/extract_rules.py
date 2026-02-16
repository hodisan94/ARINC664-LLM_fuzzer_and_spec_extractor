!/usr/bin/env python
"""
Main script for extracting protocol rules from ARINC  Part  specification.

This implements the "Specification Knowledge Extraction" phase described in the paper:
. Extract relevant sections from the PDF
. Chunk the text into manageable pieces
. Send each chunk to GPT- for rule extraction
. Aggregate all extractions into a single protocol_rules.json
"""

import os
import sys
import json
import time
from pathlib import Path

 Add parent directory to path to import modules
sys.path.insert(, str(Path(__file__).parent.parent))

from spec_extraction.pdf_utils import (
    get_all_relevant_text,
    chunk_text,
    RELEVANT_CHAPTERS
)
from spec_extraction.llm_client import LLMClient
from spec_extraction.prompts import (
    SYSTEM_PROMPT_DISCOVERY,
    SYSTEM_PROMPT_RULE_EXTRACTION,
    SYSTEM_PROMPT_AGGREGATION,
    get_discovery_user_prompt,
    get_extraction_user_prompt,
    get_aggregation_user_prompt
)


def extract_rules_from_pdf(
    pdf_path: str,
    output_path: str = "spec_extraction/protocol_rules.json",
    checkpoint_dir: str = "spec_extraction/checkpoints",
    discovery_only: bool = False,
    skip_discovery: bool = False
):
    """
    Extract protocol rules from ARINC  Part  PDF using two-phase approach.
    
    Phase : Discovery - Open-ended discovery of all protocol elements
    Phase : Structured Extraction - Extract in structured JSON format
    
    Args:
        pdf_path: Path to ARINC_P.pdf
        output_path: Where to save the final protocol_rules.json
        checkpoint_dir: Directory to save intermediate results
        discovery_only: If True, only run Phase  (Discovery)
    """
    print("="  )
    print(" ARINC  Part  - Protocol Rule Extraction")
    print("="  )
    if skip_discovery:
        print("\n Phase  ONLY: Structured Extraction (JSON format)")
    elif discovery_only:
        print("\n Phase  ONLY: Discovery (open-ended exploration)")
    else:
        print("\n Phase : Discovery (open-ended exploration)")
        print(" Phase : Structured Extraction (JSON format)")
    print("="  )
    
     Create checkpoint directory
    os.makedirs(checkpoint_dir, exist_ok=True)
    
     Initialize LLM client
    print("\n Initializing LLM client (GPT-5)...")
    try:
        llm = LLMClient(model="gpt-5")
        print(" LLM client ready")
    except Exception as e:
        print(f" Failed to initialize LLM client: {e}")
        print("\n Make sure OPENAI_API_KEY environment variable is set")
        return
    
     Step : Extract text from all relevant chapters
    print("\n" + "="  )
    print(" Step : Extracting text from relevant chapters")
    print("="  )
    
    chapter_texts = get_all_relevant_text(pdf_path)
    print(f"\n Extracted {len(chapter_texts)} chapters:")
    for chapter_name in chapter_texts.keys():
        text_len = len(chapter_texts[chapter_name])
        print(f"   - {chapter_name}: {text_len:,} characters")
    
     Step : Phase  - Discovery (open-ended) - Skip if requested
    if skip_discovery:
        print("\n  Skipping Phase  (Discovery) as requested")
        discovery_results = []
    else:
        print("\n" + "="  )
        print(" Step : Phase  - Discovery (finding all protocol elements)")
        print("="  )
        
        discovery_results = []
        discovery_dir = os.path.join(checkpoint_dir, "phase_discovery")
        os.makedirs(discovery_dir, exist_ok=True)
        
        for chapter_name, chapter_text in chapter_texts.items():
            print(f"\n Discovery: {chapter_name}")
            
             Chunk the chapter text
            chunks = chunk_text(chapter_text, max_chars=)
            print(f"   ├─ Split into {len(chunks)} chunks")
            
            chapter_discoveries = []
            
            for i, chunk in enumerate(chunks):
                print(f"   ├─ Chunk {i+}/{len(chunks)}...", end=" ", flush=True)
                
                 Check if we have a checkpoint for this chunk
                checkpoint_file = os.path.join(
                    discovery_dir,
                    f"{chapter_name.replace('/', '_').replace(' ', '_')}_chunk_{i}.txt"
                )
                
                if os.path.exists(checkpoint_file):
                    print("(loaded from checkpoint)")
                    with open(checkpoint_file, 'r') as f:
                        discovery_text = f.read()
                else:
                     Query GPT- for discovery
                    try:
                        user_prompt = get_discovery_user_prompt(
                            chapter_name, chunk, i, len(chunks)
                        )
                        
                        discovery_text = llm.query(
                            system_prompt=SYSTEM_PROMPT_DISCOVERY,
                            user_prompt=user_prompt,
                            temperature=.,
                            max_tokens=
                        )
                        
                         Save checkpoint
                        with open(checkpoint_file, 'w') as f:
                            f.write(discovery_text)
                        
                        print("")
                        
                         Rate limiting (avoid hitting API limits)
                        time.sleep()
                    
                    except Exception as e:
                        print(f" Error: {e}")
                        discovery_text = f"ERROR: {str(e)}"
                
                chapter_discoveries.append({
                    "chapter": chapter_name,
                    "chunk_index": i,
                    "discoveries": discovery_text
                })
            
            discovery_results.extend(chapter_discoveries)
            print(f"   └─  Completed discovery for {chapter_name}")
        
        print(f"\n Discovery completed for {len(discovery_results)} chunks")
        
         Save all discoveries
        discovery_output = os.path.join(checkpoint_dir, "phase_all_discoveries.json")
        with open(discovery_output, 'w') as f:
            json.dump(discovery_results, f, indent=)
        print(f" Saved all discoveries to: {discovery_output}")
        
         Also save as readable text
        discovery_text_output = os.path.join(checkpoint_dir, "phase_all_discoveries.txt")
        with open(discovery_text_output, 'w') as f:
            f.write("="   + "\n")
            f.write("ARINC  Part  - Discovery Phase Results\n")
            f.write("="   + "\n\n")
            for item in discovery_results:
                f.write(f"\n{'='}\n")
                f.write(f"Chapter: {item['chapter']} (Chunk {item['chunk_index'] + })\n")
                f.write(f"{'='}\n\n")
                f.write(item['discoveries'])
                f.write("\n\n")
        print(f" Saved readable discoveries to: {discovery_text_output}")
        
         If discovery_only mode, stop here
        if discovery_only:
            print("\n" + "="  )
            print(" DISCOVERY PHASE COMPLETE!")
            print("="  )
            print(f" Discovery results: {discovery_output}")
            print(f" Readable format: {discovery_text_output}")
            print("\n Next steps:")
            print("   . Review the discoveries to understand what was found")
            print("   . Update the JSON schema if needed")
            print("   . Run Phase  (structured extraction) with discovery_only=False")
            return
    
     Step : Phase  - Structured extraction
    step_num =  if skip_discovery else 
    print("\n" + "="  )
    print(f" Step {step_num}: Phase  - Structured Extraction (JSON format)")
    print("="  )
    
    all_extractions = []
    extraction_dir = os.path.join(checkpoint_dir, "phase_structured")
    os.makedirs(extraction_dir, exist_ok=True)
    
    for chapter_name, chapter_text in chapter_texts.items():
        print(f"\n Extracting: {chapter_name}")
        
         Chunk the chapter text
        chunks = chunk_text(chapter_text, max_chars=)
        print(f"   ├─ Split into {len(chunks)} chunks")
        
        chapter_extractions = []
        
        for i, chunk in enumerate(chunks):
            print(f"   ├─ Chunk {i+}/{len(chunks)}...", end=" ", flush=True)
            
             Check if we have a checkpoint for this chunk
            checkpoint_file = os.path.join(
                extraction_dir,
                f"{chapter_name.replace('/', '_').replace(' ', '_')}_chunk_{i}.json"
            )
            
            if os.path.exists(checkpoint_file):
                print("(loaded from checkpoint)")
                with open(checkpoint_file, 'r') as f:
                    extraction = json.load(f)
            else:
                 Query GPT- for rule extraction
                try:
                    user_prompt = get_extraction_user_prompt(
                        chapter_name, chunk, i, len(chunks)
                    )
                    
                    extraction = llm.query_json(
                        system_prompt=SYSTEM_PROMPT_RULE_EXTRACTION,
                        user_prompt=user_prompt,
                        temperature=.,
                        max_tokens=
                    )
                    
                     Save checkpoint
                    with open(checkpoint_file, 'w') as f:
                        json.dump(extraction, f, indent=)
                    
                    print("")
                    
                     Rate limiting (avoid hitting API limits)
                    time.sleep()
                
                except Exception as e:
                    print(f" Error: {e}")
                    extraction = {"error": str(e)}
            
            chapter_extractions.append({
                "chapter": chapter_name,
                "chunk_index": i,
                "extraction": extraction
            })
        
        all_extractions.extend(chapter_extractions)
        print(f"   └─  Completed {chapter_name}")
    
    print(f"\n Extracted rules from {len(all_extractions)} chunks across {len(chapter_texts)} chapters")
    
     Save intermediate results
    intermediate_file = os.path.join(checkpoint_dir, "phase_all_extractions.json")
    with open(intermediate_file, 'w') as f:
        json.dump(all_extractions, f, indent=)
    print(f" Saved intermediate results to: {intermediate_file}")
    
     Step : Aggregate all extractions into one document
    print("\n" + "="  )
    print(" Step : Aggregating all extractions")
    print("="  )
    
     Extract just the rule dictionaries (skip metadata)
    rule_dicts = [item["extraction"] for item in all_extractions if "error" not in item["extraction"]]
    
    print(f"   ├─ Aggregating {len(rule_dicts)} successful extractions...")
    
    try:
        aggregation_prompt = get_aggregation_user_prompt(rule_dicts)
        
        final_rules = llm.query_json(
            system_prompt=SYSTEM_PROMPT_AGGREGATION,
            user_prompt=aggregation_prompt,
            temperature=.,
            max_tokens=
        )
        
        print("   └─  Aggregation complete")
    
    except Exception as e:
        print(f"   └─  Aggregation failed: {e}")
        print("\n  Falling back to manual merge (combining all extractions)")
        final_rules = {
            "note": "Automatic aggregation failed, manual review required",
            "extractions": rule_dicts
        }
    
     Step : Save final output
    print("\n" + "="  )
    print(" Step : Saving final protocol rules")
    print("="  )
    
    with open(output_path, 'w') as f:
        json.dump(final_rules, f, indent=)
    
    print(f" Final protocol rules saved to: {output_path}")
    print(f" Size: {os.path.getsize(output_path):,} bytes")
    
     Summary
    print("\n" + "="  )
    print(" TWO-PHASE EXTRACTION COMPLETE!")
    print("="  )
    print(f" Final rules: {output_path}")
    print(f" Phase  discoveries: {checkpoint_dir}/phase_all_discoveries.txt")
    print(f" Phase  extractions: {checkpoint_dir}/phase_all_extractions.json")
    print(f" Processed {len(chapter_texts)} chapters, {len(all_extractions)} chunks")
    print("\n Next step: Review protocol_rules.json and compare with existing spec_rules.json")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract protocol rules from ARINC  Part  using two-phase LLM approach"
    )
    parser.add_argument(
        "--pdf",
        default="ARINC_P.pdf",
        help="Path to ARINC  Part  PDF (default: ARINC_P.pdf)"
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Run only Phase  (Discovery) and stop"
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip Phase  (Discovery) and run only Phase  (Extraction)"
    )
    parser.add_argument(
        "--output",
        default="spec_extraction/protocol_rules.json",
        help="Output path for final protocol rules JSON"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f" Error: PDF file not found: {args.pdf}")
        print("\n Make sure the PDF file exists")
        sys.exit()
    
    extract_rules_from_pdf(
        pdf_path=args.pdf,
        output_path=args.output,
        discovery_only=args.discovery_only,
        skip_discovery=args.skip_discovery
    )

