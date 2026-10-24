#!/usr/bin/env python3
"""Which mutations reached the simulator, in the campaigns and in the BDR replay?
(TAES revision: R1-M2, R2-C4, R2-C6.)

Rule Coverage counts the rule label of each iteration, but the harness passes the
simulator only the flat mutation config built by
``SimulatorRunner._translate_to_cpp_format`` (target VL, payload delta, timing offset,
source-MAC mutation, destination-MAC mutation, sequence-number override, TX-drop
probability). This script rebuilds that config for every iteration, without running
the simulator or calling any API:

  LLM       from the logged strategy fields (all of them are logged);
  Boofuzz   by replaying the deterministic strategy generator, because its history
            does not log the MAC, sequence-number-override and probability fields.
            The 200 logged iterations come from two campaigns (0-49 on 2026-03-24,
            50-199 on 2026-04-07) that used different rule bases; the replay uses the
            generator of commit 624b7f651 with the rule base of each campaign and is
            checked against the logged violation_id of every iteration;
  Random    not reconstructable: its history logs no mutation parameters.

It also rebuilds the config that ``evaluation/compute_bdr.py`` replayed for
Experiment 3 (logged fields only, ``prob`` defaulting to 0.5 when the field is absent),
computes the Rule Coverage of a clean 200-iteration Boofuzz schedule on the rule base
that the LLM run used, and replays the coverage-driven redirection of the evaluated
planner (commit ee87bd259) to count the iterations whose recorded label is exactly the
rule that the redirection would have selected.

Run from the repository root:  python3 evaluation/revision/executed_settings.py
Output: evaluation/results/revision/executed_settings.json
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import recompute_coverage_venn as rcv  # noqa: E402

OUT = ROOT / "evaluation/results/revision/executed_settings.json"
HISTORIES = {
    "LLM": ROOT / "llm_fuzzer/data/iteration_history.jsonl",
    "Boofuzz": ROOT / "boofuzz_baseline/data/iteration_history.jsonl",
    "Random": ROOT / "random_baseline/data/iteration_history.jsonl",
}
BOOFUZZ_GENERATOR_COMMIT = "624b7f651"
BOOFUZZ_RULE_BASES = (("8552e023a", 0, 50), ("00a742eec", 50, 200))  # (commit, first, end)
PLANNER_COMMIT = "ee87bd259"
AVAILABLE_VLS = [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
METADATA_FIELDS = ("mutation_type", "bag_value", "frame_size", "timing_jitter_ms",
                   "mac_mutation_type", "prob", "sequence_number_override",
                   "dest_mac_mutation")
SETTING_KEYS = ("vlId", "payload_delta_bytes", "timing_jitter_ms", "mac_mutation",
                "dest_mac_mutation", "sequence_number_override", "prob")


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def git_show(commit, path, dest):
    dest = Path(dest)
    dest.write_bytes(subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                                    capture_output=True, check=True).stdout)
    return dest


class Translator:
    """SimulatorRunner._translate_to_cpp_format without the runner's side effects."""

    def __init__(self):
        sys.path.insert(0, str(ROOT))
        from llm_fuzzer.utils.simulator_runner import SimulatorRunner
        self.runner = SimulatorRunner.__new__(SimulatorRunner)
        self.runner.vl_configs = SimulatorRunner._load_vl_configs(
            self.runner, ROOT / "examples/AFDX_V3/config/virtual_links.csv")

    def __call__(self, vl_id, metadata):
        return self.runner._translate_to_cpp_format({"vl_id": vl_id, "metadata": metadata})


def mechanisms(cfg):
    used = []
    if cfg["payload_delta_bytes"]:
        used.append("frame_size")
    if cfg["timing_jitter_ms"]:
        used.append("timing")
    if cfg["mac_mutation"] != "none":
        used.append("src_mac")
    if cfg["dest_mac_mutation"] not in (None, "none"):
        used.append("dest_mac")
    if cfg["sequence_number_override"]:
        used.append("seq_override")
    if cfg["prob"] > 0:
        used.append("tx_drop")
    return used


def summarize(configs):
    per_mechanism, no_mutation = Counter(), 0
    for cfg in configs:
        used = mechanisms(cfg)
        per_mechanism.update(used)
        no_mutation += not used
    settings = {tuple(cfg[k] for k in SETTING_KEYS) for cfg in configs}
    return {"iterations": len(configs), "distinct_settings": len(settings),
            "iterations_per_mechanism": dict(per_mechanism),
            "iterations_without_mutation": no_mutation}


def campaign_metadata(row, mutation_type):
    meta = {k: row.get(k) for k in METADATA_FIELDS}
    meta["mutation_type"] = mutation_type
    return meta


def bdr_metadata(row):
    """The metadata that compute_bdr.run_single_iteration builds from a history record."""
    meta = {k: row.get(k) for k in METADATA_FIELDS}
    meta["mutation_type"] = row.get("mutation_type", "")
    meta["prob"] = row.get("prob", 0.5)
    return meta


def boofuzz_generator(tmp):
    path = git_show(BOOFUZZ_GENERATOR_COMMIT, "boofuzz_baseline/boofuzz_strategy_generator.py",
                    tmp / "boofuzz_generator.py")
    spec = importlib.util.spec_from_file_location("boofuzz_generator_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BoofuzzStrategyGenerator


def replay_boofuzz(rows, tmp):
    """Replay both Boofuzz campaigns; return the strategies and the replay check."""
    generator_cls = boofuzz_generator(tmp)
    test_cases = git_show("00a742eec", "configs/test_cases.json", tmp / "test_cases.json")
    strategies, matched = [], 0
    for commit, first, end in BOOFUZZ_RULE_BASES:
        spec_rules = git_show(commit, "configs/spec_rules_filtered.json",
                              tmp / f"spec_rules_{commit}.json")
        gen = generator_cls(test_cases_path=str(test_cases), spec_rules_path=str(spec_rules))
        for i in range(first, end):
            s = gen.plan_next_iteration(None, i, {"available_vls": AVAILABLE_VLS})
            matched += s["violation_id"] == rows[i]["violation_id"]
            strategies.append(s)
    clean = generator_cls(test_cases_path=str(test_cases),
                          spec_rules_path=str(ROOT / "configs/spec_rules_filtered.json"))
    clean_labels = [clean.plan_next_iteration(None, i, {"available_vls": AVAILABLE_VLS})
                    ["protocol_rule"] for i in range(200)]
    return strategies, matched, clean_labels


def boofuzz_campaign_configs(rows, strategies, translate):
    configs = []
    for row, s in zip(rows, strategies):
        meta = campaign_metadata(row, row["mutation_type"])
        for k in ("mac_mutation_type", "prob", "sequence_number_override",
                  "dest_mac_mutation", "timing_jitter_ms"):
            meta[k] = s.get(k)
        configs.append(translate(row["target_vl"], meta))
    return configs


def category_curve(labels, categories_of):
    covered, curve = set(), []
    for label in labels:
        covered |= categories_of(label)
        curve.append(len(covered))
    return covered, curve


def redirect_replay(rows, tmp, categories_of):
    """Count LLM iterations whose label is the rule the evaluated redirection picks."""
    tree = tmp / "planner_tree"
    tree.mkdir()
    archive = subprocess.run(["git", "archive", PLANNER_COMMIT, "llm_fuzzer"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    code = (
        "import json, sys\n"
        "import pandas as pd\n"
        f"sys.path.insert(0, {str(tree)!r})\n"
        "from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner\n"
        "from llm_fuzzer.utils.spec_loader import SpecificationLoader\n"
        "from llm_fuzzer.utils.test_case_loader import TestCaseLoader\n"
        "sr, tc, hist_path = sys.argv[1:4]\n"
        "p = LLMStrategyPlanner.__new__(LLMStrategyPlanner)\n"
        "p.spec_rules = SpecificationLoader(sr).get_all_rules()\n"
        "p.test_cases = TestCaseLoader(tc).get_all_test_cases()\n"
        "p._rule_to_cat, p._cat_to_rules = p._build_category_maps(sr)\n"
        "p._all_known_rules = sorted(set(p.spec_rules) | set(p.test_cases))\n"
        "rows = [json.loads(l) for l in open(hist_path) if l.strip()]\n"
        "picks = []\n"
        "for i in range(len(rows)):\n"
        "    hist = pd.DataFrame(rows[:i], dtype=object) if i else None\n"
        "    stats = p._compute_coverage_stats(hist)\n"
        "    tested = set(hist['protocol_rule'].dropna().unique()) if i else set()\n"
        "    covered = set()\n"
        "    for r in tested:\n"
        "        covered |= p._all_categories_for_rule(str(r))\n"
        "    unc = [c for c in stats['uncovered_categories'] if p._norm(c) not in covered]\n"
        "    picks.append(p._pick_untested_rule_from_category(unc, tested, {}, {}) if unc else None)\n"
        "print(json.dumps(picks))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code,
                           str(ROOT / "configs/spec_rules_filtered.json"),
                           str(ROOT / "configs/test_cases.json"), str(HISTORIES["LLM"])],
                          cwd=tmp, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    picks = json.loads(proc.stdout.strip().splitlines()[-1])
    is_pick = [row["protocol_rule"] == pick for row, pick in zip(rows, picks)]
    own = [row["protocol_rule"] for row, hit in zip(rows, is_pick) if not hit]
    own_categories, _ = category_curve(own, categories_of)
    return {"label_equals_redirect_pick": sum(is_pick),
            "label_differs_from_redirect_pick": len(rows) - sum(is_pick),
            "categories_from_other_iterations": len(own_categories),
            "first_iterations_label_equals_pick": [int(r["iteration"]) for r, h in
                                                   zip(rows, is_pick) if h][:20]}


def main():
    translate = Translator()
    spec_rules = json.loads((ROOT / "configs/spec_rules_filtered.json").read_text())
    categories_of = rcv.build_matcher(spec_rules)
    rows = {name: load(path) for name, path in HISTORIES.items()}
    report = {"campaign": {}, "bdr_replay": {}}

    llm_configs = [translate(r["target_vl"], campaign_metadata(
        r, r.get("mutation_type") or r.get("protocol_rule") or "generic")) for r in rows["LLM"]]
    report["campaign"]["LLM"] = summarize(llm_configs)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        strategies, matched, clean_labels = replay_boofuzz(rows["Boofuzz"], tmp)
        boofuzz_configs = boofuzz_campaign_configs(rows["Boofuzz"], strategies, translate)
        report["campaign"]["Boofuzz"] = summarize(boofuzz_configs)
        report["campaign"]["Boofuzz"]["replay_matches_logged_violation_id"] = matched
        report["campaign"]["Random"] = {"iterations": len(rows["Random"]),
                                        "note": "mutation parameters not logged"}
        report["redirect_replay_LLM"] = redirect_replay(rows["LLM"], tmp, categories_of)

    for name, history in rows.items():
        report["bdr_replay"][name] = summarize(
            [translate(r.get("target_vl", 2001), bdr_metadata(r)) for r in history])

    stitched, _ = category_curve([r["protocol_rule"] for r in rows["Boofuzz"]], categories_of)
    clean, curve = category_curve(clean_labels, categories_of)
    llm_cats, _ = category_curve([r["protocol_rule"] for r in rows["LLM"]], categories_of)
    report["boofuzz_rule_coverage"] = {
        "stitched_history_categories": len(stitched),
        "clean_200_iteration_schedule_categories": len(clean),
        "clean_curve_at_50_100_150_200": [curve[49], curve[99], curve[149], curve[199]],
        "clean_and_llm": len(clean & llm_cats), "clean_only": len(clean - llm_cats),
        "llm_only": len(llm_cats - clean)}

    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
