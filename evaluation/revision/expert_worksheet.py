#!/usr/bin/env python3
"""Expert validation of the judge LLM (Reviewer 2, comment 2; context/REVIEW_STATUS.md R2-2).

  make   builds an Excel worksheet from the 108-rule stratified sample that the second judge
         (GPT-5) already labeled (evaluation/results/revision/judge_validation_sample.csv).
         The judges' verdicts and reasons are NOT in the worksheet, so the expert labels
         blind. The rows keep the sample's random order.
  merge  reads a filled worksheet, writes its verdicts into the expert_verdict and
         expert_notes columns of judge_validation_sample.csv, and prints the error types.
         Then run:  python evaluation/revision/audit_final_rules.py score --reference expert

No LLM API is used.

Usage:
  python evaluation/revision/expert_worksheet.py make --out evaluation/results/revision/judge_expert_worksheet.xlsx
  python evaluation/revision/expert_worksheet.py merge --filled <filled.xlsx> [--expert NAME]
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "evaluation/results/revision/judge_validation_sample.csv"
VERDICTS = ["correct", "incorrect", "unverifiable"]
ERROR_TYPES = ["none", "wrong value or number", "missing condition or exception",
               "modal strength changed (should/may -> shall/must)", "not in the standard",
               "wrong scope (applies to another component or case)", "too vague to test",
               "other (see notes)"]
COLUMNS = ["No.", "Rule ID", "Category", "Rule name", "Rule (constraint)",
           "Passages found by retrieval (aid only)", "Verdict", "Error type",
           "Where in the standard (section / page)", "Notes"]
WIDTHS = [5, 10, 22, 30, 50, 80, 14, 30, 20, 30]
INSTRUCTIONS = [
    "Expert validation of extracted rules (TAES-2026-2779, Reviewer 2 comment 2)",
    "",
    "For each row, decide whether the rule is a correct statement of ARINC 664 Part 7.",
    "Use the full standard; the passages in column F were found automatically and are only a",
    "starting point (they are what the judge LLM saw). Do not look up the judge's verdict.",
    "",
    "Verdict:",
    "  correct       the standard states this rule (same values, conditions and strength).",
    "  incorrect     the standard contradicts it, or it changes a value, condition or strength.",
    "  unverifiable  the standard neither states nor contradicts it.",
    "",
    "Error type: choose 'none' for a correct rule; otherwise the main problem.",
    "Where in the standard: the section or page you used (e.g. 3.2.6.2.1, p. 45).",
    "",
    "If two experts label: both label rows 1-30 (used to measure agreement between experts);",
    "one expert labels rows 31-108. About 2 minutes per rule.",
    "Return the file with the same name plus your initials, e.g. judge_expert_worksheet_NB.xlsx.",
]


def make(out):
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    wb = Workbook()
    ws = wb.active
    ws.title = "Rules"
    ws.append(COLUMNS)
    for i, r in enumerate(rows, 1):
        passages = r["spec_passages"].replace(" || ", "\n\n")
        ws.append([i, r["id"], r["category"], r["name"], r["constraint"], passages, "", "", "", ""])
    for col, w in zip("ABCDEFGHIJ", WIDTHS):
        ws.column_dimensions[col].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in row[6:10]:
            cell.fill = PatternFill("solid", fgColor="FFF7D6")
    ws.freeze_panes = "C2"
    n = len(rows) + 1
    dv = DataValidation(type="list", formula1='"' + ",".join(VERDICTS) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"G2:G{n}")
    lists = wb.create_sheet("Lists")
    for i, e in enumerate(ERROR_TYPES, 1):
        lists.cell(row=i, column=1, value=e)
    de = DataValidation(type="list", formula1=f"=Lists!$A$1:$A${len(ERROR_TYPES)}", allow_blank=True)
    ws.add_data_validation(de)
    de.add(f"H2:H{n}")
    info = wb.create_sheet("Instructions", 0)
    for line in INSTRUCTIONS:
        info.append([line])
    info.column_dimensions["A"].width = 100
    info["A1"].font = Font(bold=True, size=13)
    wb.save(out)
    print(f"{len(rows)} rules -> {out}")


def merge(filled, expert):
    ws = load_workbook(filled, data_only=True)["Rules"]
    labels = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        rid, verdict, err, where, notes = row[1], row[6], row[7], row[8], row[9]
        if rid and verdict:
            verdict = str(verdict).strip().lower()
            if verdict not in VERDICTS:
                sys.exit(f"{rid}: verdict {verdict!r} is not one of {VERDICTS}")
            labels[rid] = (verdict, err or "", where or "", notes or "")
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    for r in rows:
        if r["id"] in labels:
            v, err, where, notes = labels[r["id"]]
            r["expert_verdict"] = v
            r["expert_notes"] = f"[{expert}] error: {err}; where: {where}; {notes}".strip()
    with SAMPLE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(labels)} expert labels merged into {SAMPLE.name}")
    print("verdicts:", dict(Counter(v[0] for v in labels.values())))
    print("error types:", dict(Counter(v[1] for v in labels.values() if v[0] != "correct")))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--out", required=True)
    g = sub.add_parser("merge")
    g.add_argument("--filled", required=True)
    g.add_argument("--expert", default="expert")
    a = p.parse_args()
    make(a.out) if a.cmd == "make" else merge(a.filled, a.expert)


if __name__ == "__main__":
    main()
