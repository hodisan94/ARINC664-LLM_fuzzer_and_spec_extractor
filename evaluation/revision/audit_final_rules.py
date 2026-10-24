#!/usr/bin/env python3
"""Re-run the Experiment 1 audits on the final rule base (TAES revision: R1-m2, R1-m3, R2-C2).

The submitted correctness (236 rules) and completeness (82 items) results were
computed on an earlier extraction run, and the completeness checklist was
enumerated by an LLM without the specification text. This script audits the
final rule base instead: the judge sees, for every rule, the specification
passages most similar to it (BM25 retrieval over the specification PDF), and
completeness is measured against the normative statements ("shall", "should",
"must") of the specification text itself.

Subcommands (run from the repository root):
  checklist     build the normative-statement checklist from the PDF (no API calls)
  correctness   judge every rule against retrieved passages (OpenAI API)
  completeness  match each checklist item to candidate rules (OpenAI API)
  sample        stratified sample of rules for expert labeling (no API calls)
  crossjudge    second, independent judge on the sample (Anthropic API)
  score         compare expert or second-judge labels with judge verdicts (no API calls)

Outputs go to evaluation/results/revision/.
"""
import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evaluation" / "results" / "revision"
SPEC_PDF = ROOT / "configs" / "ARINC_664P7.pdf"
RULE_SETS = {
    "filtered": ROOT / "spec_extraction/multimodel_output/spec_rules_filtered.json",
    "validated": ROOT / "spec_extraction/multimodel_output/spec_rules_validated.json",
}
VERDICTS = ("correct", "incorrect", "unverifiable")
SECOND_JUDGE = "gpt-5"
JUDGE_INSTRUCTIONS = [
    "You are an avionics protocol expert auditing rules extracted from ARINC "
    "Specification 664 Part 7 (AFDX). For each rule, use ONLY the specification "
    "passages given with it and judge whether the rule is \"correct\" (the passages "
    "support it), \"incorrect\" (the passages contradict it), or \"unverifiable\" "
    "(the passages neither support nor contradict it).",
    'Return JSON: {"results": [{"id": "...", "verdict": "correct|incorrect|unverifiable", '
    '"reason": "one sentence"}]}', ""]
STOP = set("a an and are as at be by for from in is it its of on or that the this to with "
           "which shall should must may can each all any not no be been into per".split())


# ---------------------------------------------------------------- spec text

def spec_pages():
    from PyPDF2 import PdfReader
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(PdfReader(str(SPEC_PDF)).pages)]


def passages(pages, size=900, step=450):
    out = []
    for page_no, text in pages:
        text = re.sub(r"\s+", " ", text).strip()
        for start in range(0, max(len(text) - step, 1), step):
            out.append({"page": page_no, "text": text[start:start + size]})
    return out


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1 and t not in STOP]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [Counter(tokens(d)) for d in docs]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def top(self, query, k):
        q = set(tokens(query))
        scores = []
        for i, (d, length) in enumerate(zip(self.docs, self.lens)):
            s = 0.0
            for t in q & d.keys():
                tf = d[t]
                s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
            scores.append((s, i))
        return [i for s, i in sorted(scores, reverse=True)[:k] if s > 0]


def normative_statements(pages):
    """Sentences containing shall/should/must in Sections 2-5 and the attachments,
    outside COMMENTARY blocks. Front matter and Section 1 are introductory, and the
    appendices (and the APIM form after them) are informative, so they are skipped."""
    items, section, in_commentary = [], "", False
    split = re.compile(r"(?<=[.;])\s+(?=[A-Z])|\s+(?=\d+(?:\.\d+)+\s+[A-Z][a-z])")
    for page_no, text in pages:
        para = []
        for line in text.splitlines() + [""]:
            stripped = line.strip()
            head = re.match(r"^(\d+(?:\.\d+)+)\s+[A-Z]", stripped)
            if head and "...." not in stripped:
                section, in_commentary = head.group(1), False
            annex = re.match(r"^(ATTACHMENT|APPENDIX)\s+([0-9A-Z]+)$", stripped)
            if annex:
                section = f"Att{annex.group(2)}" if annex.group(1) == "ATTACHMENT" else ""
            if stripped.upper() == "COMMENTARY":
                in_commentary = True
                continue
            if not stripped:
                if para and not in_commentary and section and not section.startswith("1"):
                    joined = re.sub(r"\s+", " ", " ".join(para))
                    for sent in split.split(joined):
                        if (re.search(r"\b(shall|should|must)\b", sent) and len(sent) > 30
                                and not re.search(r"\bnot\b[^.]{0,20}\bnorma\s?tive\b", sent)):
                            items.append({"section": section, "page": page_no, "text": sent.strip()})
                para, in_commentary = [], False
                continue
            para.append(stripped)
    seen, unique = set(), []
    for item in items:
        if item["text"] not in seen:
            seen.add(item["text"])
            unique.append(item)
    for i, item in enumerate(unique, 1):
        item["id"] = f"N{i:03d}"
    return unique


# ---------------------------------------------------------------- rules and LLM

def load_rules(which):
    rules = json.loads(RULE_SETS[which].read_text())["rules"]
    for r in rules:
        r["query"] = " ".join(str(r.get(k, "")) for k in ("category", "name", "consensus_value", "source_quote"))
    return rules


def openai_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set")
    return OpenAI()


def fixed_temperature(model):
    """Reasoning models accept only the API default temperature."""
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def ask_json(client, model, prompt, retries=3):
    extra = {} if fixed_temperature(model) else {"temperature": 0.0}
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model, response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}], **extra)
            return json.loads(resp.choices[0].message.content)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"    retry after error: {exc}")
            time.sleep(2 ** (attempt + 1))


def mistral_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT / ".env")
    if not os.getenv("MISTRAL_API_KEY"):
        sys.exit("MISTRAL_API_KEY not set")
    return OpenAI(api_key=os.getenv("MISTRAL_API_KEY"), base_url="https://api.mistral.ai/v1")


def anthropic_client():
    from anthropic import Anthropic
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set")
    return Anthropic()


def ask_json_anthropic(client, model, prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=model, max_tokens=2000, temperature=0.0,
                messages=[{"role": "user", "content": prompt + "\nReturn only the JSON object."}])
            text = resp.content[0].text
            return json.loads(text[text.find("{"):text.rfind("}") + 1])
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"    retry after error: {exc}")
            time.sleep(2 ** (attempt + 1))


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- subcommands

def cmd_checklist(args):
    items = normative_statements(spec_pages())
    save("normative_checklist.json", {"source": SPEC_PDF.name, "count": len(items), "items": items})
    print(f"{len(items)} normative statements -> {OUT / 'normative_checklist.json'}")


def cmd_correctness(args):
    rules = load_rules(args.rules)
    psg = passages(spec_pages())
    index = BM25([p["text"] for p in psg])
    path = OUT / f"rule_correctness_{args.rules}.json"
    verdicts = json.loads(path.read_text())["verdicts"] if path.exists() else {}
    todo = [r for r in rules if r["id"] not in verdicts]
    print(f"{len(rules)} rules, {len(verdicts)} already judged, {len(todo)} to judge")
    client = openai_client()
    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        lines = list(JUDGE_INSTRUCTIONS)
        for r in batch:
            lines += [f"--- Rule {r['id']} ---", f"Category: {r.get('category')}",
                      f"Name: {r.get('name')}", f"Constraint: {r.get('consensus_value')}"]
            for j in index.top(r["query"], args.passages):
                lines.append(f"Specification passage (page {psg[j]['page']}): \"{psg[j]['text']}\"")
            lines.append("")
        answer = ask_json(client, args.model, "\n".join(lines))
        by_id = {str(x.get("id")): x for x in answer.get("results", []) if isinstance(x, dict)}
        for r in batch:
            x = by_id.get(r["id"], {})
            verdict = x.get("verdict") if x.get("verdict") in VERDICTS else "unverifiable"
            verdicts[r["id"]] = {"verdict": verdict, "reason": x.get("reason", "missing from response"),
                                 "agreement": r.get("agreement"), "category": r.get("category")}
        counts = Counter(v["verdict"] for v in verdicts.values())
        save(path.name, {"rule_set": args.rules, "model": args.model, "temperature": 0.0,
                         "passages_per_rule": args.passages, "date": str(date.today()),
                         "total": len(verdicts), "counts": counts, "verdicts": verdicts})
        print(f"  {len(verdicts)}/{len(rules)} judged: {dict(counts)}")
    cats = defaultdict(list)
    for v in verdicts.values():
        cats[v["category"]].append(v["verdict"])
    all_rejected = sorted(c for c, vs in cats.items() if all(x == "incorrect" for x in vs))
    print(f"categories whose rules were all judged incorrect: {len(all_rejected)} {all_rejected}")


def cmd_completeness(args):
    checklist = json.loads((OUT / "normative_checklist.json").read_text())["items"]
    rules = load_rules(args.rules)
    index = BM25([r["query"] for r in rules])
    suffix = "" if args.candidates == 8 else f"_k{args.candidates}"
    path = OUT / f"rule_completeness_{args.rules}{suffix}.json"
    results = json.loads(path.read_text())["items"] if path.exists() else {}
    todo = [c for c in checklist if c["id"] not in results]
    client = openai_client()
    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        lines = [
            "You check whether normative requirements of ARINC Specification 664 Part 7 are "
            "captured by a set of extracted rules. For each requirement, decide whether at "
            "least one of its candidate rules states the same obligation: \"covered\" (same "
            "obligation), \"partial\" (related but missing a key condition or value), or "
            "\"not_covered\".",
            'Return JSON: {"results": [{"id": "...", "status": "covered|partial|not_covered", '
            '"rule_id": "best matching rule id or null"}]}', ""]
        for c in batch:
            lines += [f"--- Requirement {c['id']} (section {c['section']}) ---", c["text"], "Candidates:"]
            for j in index.top(c["text"], args.candidates):
                r = rules[j]
                lines.append(f"  [{r['id']}] {r.get('name')}: {r.get('consensus_value')}")
            lines.append("")
        answer = ask_json(client, args.model, "\n".join(lines))
        by_id = {str(x.get("id")): x for x in answer.get("results", []) if isinstance(x, dict)}
        for c in batch:
            x = by_id.get(c["id"], {})
            status = x.get("status") if x.get("status") in ("covered", "partial", "not_covered") else "not_covered"
            results[c["id"]] = {"status": status, "rule_id": x.get("rule_id"), "section": c["section"]}
        counts = Counter(v["status"] for v in results.values())
        save(path.name, {"rule_set": args.rules, "model": args.model, "temperature": 0.0,
                         "candidates_per_item": args.candidates, "date": str(date.today()),
                         "checklist_items": len(checklist), "counts": counts, "items": results})
        print(f"  {len(results)}/{len(checklist)} matched: {dict(counts)}")


def cmd_sample(args):
    rules = load_rules(args.rules)
    psg = passages(spec_pages())
    index = BM25([p["text"] for p in psg])
    judged_path = OUT / f"rule_correctness_{args.rules}.json"
    judged = json.loads(judged_path.read_text())["verdicts"] if judged_path.exists() else {}
    strata = defaultdict(list)
    for r in rules:
        strata[r.get("agreement")].append(r)
    rng = random.Random(args.seed)
    quota = {s: min(len(rs), max(args.min_per_stratum, round(args.n * len(rs) / len(rules))))
             for s, rs in strata.items()}
    sample = [r for s, rs in sorted(strata.items()) for r in rng.sample(rs, quota[s])]
    rng.shuffle(sample)
    path = OUT / "judge_validation_sample.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "agreement", "category", "name", "constraint", "spec_passages",
                    "judge_verdict", "judge_reason", "expert_verdict", "expert_notes"])
        for r in sample:
            ctx = " || ".join(f"p.{psg[j]['page']}: {psg[j]['text']}" for j in index.top(r["query"], args.passages))
            j = judged.get(r["id"], {})
            w.writerow([r["id"], r.get("agreement"), r.get("category"), r.get("name"),
                        r.get("consensus_value"), ctx, j.get("verdict", ""), j.get("reason", ""), "", ""])
    print(f"{len(sample)} rules ({quota}) -> {path}")


def cmd_crossjudge(args):
    with (OUT / "judge_validation_sample.csv").open() as f:
        rows = list(csv.DictReader(f))
    path = OUT / "judge_validation_second.json"
    verdicts = json.loads(path.read_text())["verdicts"] if path.exists() else {}
    todo = [r for r in rows if r["id"] not in verdicts]
    print(f"{len(rows)} sampled rules, {len(verdicts)} already judged, {len(todo)} to judge")
    if args.model.startswith("claude"):
        client, ask = anthropic_client(), ask_json_anthropic
    elif args.model.startswith("mistral"):
        client, ask = mistral_client(), ask_json
    else:
        client, ask = openai_client(), ask_json
    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        lines = list(JUDGE_INSTRUCTIONS)
        for r in batch:
            lines += [f"--- Rule {r['id']} ---", f"Category: {r['category']}",
                      f"Name: {r['name']}", f"Constraint: {r['constraint']}"]
            for ctx in r["spec_passages"].split(" || "):
                page, _, text = ctx.partition(": ")
                lines.append(f"Specification passage (page {page.removeprefix('p.')}): \"{text}\"")
            lines.append("")
        answer = ask(client, args.model, "\n".join(lines))
        by_id = {str(x.get("id")): x for x in answer.get("results", []) if isinstance(x, dict)}
        for r in batch:
            x = by_id.get(r["id"], {})
            verdict = x.get("verdict") if x.get("verdict") in VERDICTS else "unverifiable"
            verdicts[r["id"]] = {"verdict": verdict, "reason": x.get("reason", "missing from response")}
        counts = Counter(v["verdict"] for v in verdicts.values())
        save(path.name, {"model": args.model,
                         "temperature": "API default" if fixed_temperature(args.model) else 0.0,
                         "date": str(date.today()),
                         "total": len(verdicts), "counts": counts, "verdicts": verdicts})
        print(f"  {len(verdicts)}/{len(rows)} judged: {dict(counts)}")


def cohen_kappa(pairs, labels):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in labels) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def cmd_score(args):
    with (OUT / "judge_validation_sample.csv").open() as f:
        rows = list(csv.DictReader(f))
    if args.reference == "second":
        second = json.loads((OUT / "judge_validation_second.json").read_text())["verdicts"]
        for r in rows:
            r["reference"] = second.get(r["id"], {}).get("verdict", "")
    else:
        for r in rows:
            r["reference"] = r["expert_verdict"]
    rows = [r for r in rows
            if r["reference"].strip() in VERDICTS and r["judge_verdict"].strip() in VERDICTS]
    if not rows:
        sys.exit(f"no rows with both {args.reference} and judge verdicts in " + "/".join(VERDICTS))
    pairs = [(r["reference"].strip(), r["judge_verdict"].strip()) for r in rows]
    confusion = {e: {j: sum(1 for a, b in pairs if a == e and b == j) for j in VERDICTS} for e in VERDICTS}
    strata = defaultdict(lambda: [0, 0])
    for r, (a, b) in zip(rows, pairs):
        strata[r["agreement"]][0] += 1
        strata[r["agreement"]][1] += a == b
    report = {
        "reference": args.reference,
        "labeled_rules": len(pairs),
        "accuracy": round(sum(a == b for a, b in pairs) / len(pairs), 3),
        "cohen_kappa": round(cohen_kappa(pairs, VERDICTS), 3),
        "confusion_reference_rows_judge_columns": confusion,
        "judge_correct_but_reference_not": sum(1 for a, b in pairs if b == "correct" and a != "correct"),
        "judge_incorrect_but_reference_correct": sum(1 for a, b in pairs if b == "incorrect" and a == "correct"),
        "agreement_by_stratum": {s: {"n": n, "agree": k} for s, (n, k) in sorted(strata.items())},
    }
    save(f"judge_validation_metrics_{args.reference}.json", report)
    print(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checklist")
    c = sub.add_parser("correctness")
    c.add_argument("--rules", choices=RULE_SETS, default="filtered")
    c.add_argument("--model", default="gpt-4o-mini")
    c.add_argument("--batch", type=int, default=5)
    c.add_argument("--passages", type=int, default=2)
    m = sub.add_parser("completeness")
    m.add_argument("--rules", choices=RULE_SETS, default="validated")
    m.add_argument("--model", default="gpt-4o-mini")
    m.add_argument("--batch", type=int, default=5)
    m.add_argument("--candidates", type=int, default=8)
    s = sub.add_parser("sample")
    s.add_argument("--rules", choices=RULE_SETS, default="filtered")
    s.add_argument("--n", type=int, default=100)
    s.add_argument("--min-per-stratum", type=int, default=5)
    s.add_argument("--passages", type=int, default=2)
    s.add_argument("--seed", type=int, default=2779)
    x = sub.add_parser("crossjudge")
    x.add_argument("--model", default=SECOND_JUDGE)
    x.add_argument("--batch", type=int, default=5)
    sc = sub.add_parser("score")
    sc.add_argument("--reference", choices=("expert", "second"), default="expert")
    args = p.parse_args()
    {"checklist": cmd_checklist, "correctness": cmd_correctness, "completeness": cmd_completeness,
     "sample": cmd_sample, "crossjudge": cmd_crossjudge, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
