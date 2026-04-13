#!/usr/bin/env python3
"""
Run all 3 fuzzers against the AFDX-NAV simulator.

Patches SimulatorRunner to use NAV paths and scenario,
then delegates to the standard fuzzer main() functions.
"""

import sys
import os
import argparse
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_fuzzer.utils.simulator_runner import SimulatorRunner

NAV_DEFAULTS = dict(
    mutations_file="examples/AFDX_NAV/mutations.json",
    output_dir="examples/AFDX_NAV/output",
    vl_config_file="examples/AFDX_NAV/config/virtual_links.csv",
)
NAV_SCENARIO = "afdx-nav-fuzz"
NAV_CSV = "examples/AFDX_NAV/output/csv/AFDX-LOG-OUTPUT.csv"


def patch_simulator_runner():
    """Monkey-patch SimulatorRunner for NAV paths."""
    _orig_init = SimulatorRunner.__init__

    def _nav_init(self, ns3_path="/home/hodisan1994/ns-3-reset/ns-3", **kwargs):
        merged = {**NAV_DEFAULTS, **kwargs}
        _orig_init(self, ns3_path=ns3_path, **merged)

    SimulatorRunner.__init__ = _nav_init

    _orig_run = SimulatorRunner.run_simulation

    def _nav_run(self, test_inputs, scenario_name=NAV_SCENARIO, **kwargs):
        result = _orig_run(self, test_inputs, scenario_name=scenario_name, **kwargs)
        if result['success'] and not result.get('csv_content'):
            from pathlib import Path
            csv_file = Path("/home/hodisan1994/ns-3-reset/ns-3") / NAV_CSV
            if csv_file.exists():
                result['csv_content'] = csv_file.read_text()
        return result

    SimulatorRunner.run_simulation = _nav_run


NAV_VLS = [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]


NAV_VLS = [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]


def clean_history(output_dir):
    """Ensure clean history for a fresh NAV run."""
    os.makedirs(output_dir, exist_ok=True)
    history_file = os.path.join(output_dir, "iteration_history.jsonl")
    if os.path.exists(history_file):
        os.remove(history_file)
    return history_file


def run_llm(iterations, output_dir):
    """Run LLM fuzzer on NAV."""
    from llm_fuzzer.main import LLMFuzzer
    history_file = clean_history(output_dir)

    fuzzer = LLMFuzzer(
        spec_rules_path="nav_experiment/configs/spec_rules.json",
        test_cases_path="configs/test_cases.json",
        output_dir=output_dir,
        max_iterations=iterations,
        available_vls=NAV_VLS,
        history_path=history_file,
    )
    fuzzer.run()


def run_boofuzz(iterations, output_dir):
    """Run Boofuzz baseline on NAV."""
    from boofuzz_baseline.main import BoofuzzFuzzer
    history_file = clean_history(output_dir)

    fuzzer = BoofuzzFuzzer(
        spec_rules_path="nav_experiment/configs/spec_rules.json",
        test_cases_path="configs/test_cases.json",
        output_dir=output_dir,
        max_iterations=iterations,
        available_vls=NAV_VLS,
        history_path=history_file,
    )
    fuzzer.run()


def run_random(iterations, output_dir):
    """Run Random baseline on NAV."""
    from random_baseline.main import RandomFuzzer
    history_file = clean_history(output_dir)

    fuzzer = RandomFuzzer(
        spec_rules_path="nav_experiment/configs/spec_rules.json",
        test_cases_path="configs/test_cases.json",
        output_dir=output_dir,
        max_iterations=iterations,
        available_vls=NAV_VLS,
        history_path=history_file,
    )
    fuzzer.run()


def main():
    parser = argparse.ArgumentParser(description="Run fuzzers on AFDX-NAV simulator")
    parser.add_argument("--fuzzer", choices=["llm", "boofuzz", "random", "all"], default="all")
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()

    patch_simulator_runner()

    results_base = "nav_experiment/results"
    
    runners = {
        "llm": lambda: run_llm(args.iterations, f"{results_base}/llm"),
        "boofuzz": lambda: run_boofuzz(args.iterations, f"{results_base}/boofuzz"),
        "random": lambda: run_random(args.iterations, f"{results_base}/random"),
    }

    if args.fuzzer == "all":
        for name, runner in runners.items():
            print(f"\n{'='*60}")
            print(f"  Running {name.upper()} on AFDX-NAV ({args.iterations} iterations)")
            print(f"{'='*60}")
            try:
                runner()
            except Exception as e:
                print(f"ERROR running {name}: {e}")
                import traceback; traceback.print_exc()
    else:
        runners[args.fuzzer]()


if __name__ == "__main__":
    main()
