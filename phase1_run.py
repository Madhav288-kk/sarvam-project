"""
phase1_run.py
──────────────
Phase 1 runner: PDF → Vision (ingest) → LLM (explain + checklist)

Usage:
    python phase1_run.py
    python phase1_run.py --mock-ingest   # skip Vision API, use saved JSON
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Fix Windows console encoding for Unicode / Indian language output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Load .env ────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from decoder.ingest import ingest
from decoder.explain import explain
from decoder.checklist import generate_checklist

PDF_PATH     = Path("mock/discharge_summary.pdf")
INGEST_OUT   = Path("mock/ingest_result.json")
EXPLAIN_OUT  = Path("mock/explain_result.json")
CHECKLIST_OUT = Path("mock/checklist_result.json")


def run(mock_ingest: bool = False):
    print("\n" + "═" * 60)
    print("  POST-DISCHARGE CARE PLATFORM — Phase 1")
    print("═" * 60)

    # ── STEP 1: Ingest ───────────────────────────────────────────────────
    if mock_ingest and INGEST_OUT.exists():
        print("\n[phase1] Using cached ingest result (--mock-ingest)")
        ingest_data = json.loads(INGEST_OUT.read_text(encoding="utf-8"))
    else:
        print("\n[phase1] STEP 1 — Sarvam Vision: digitise + extract")
        if not PDF_PATH.exists():
            sys.exit(
                f"PDF not found at {PDF_PATH}\n"
                "Run first:  python mock/generate_discharge_pdf.py"
            )
        ingest_data = ingest(PDF_PATH)
        INGEST_OUT.write_text(
            json.dumps(ingest_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  → Saved to {INGEST_OUT}")

    fields = ingest_data.get("fields", ingest_data)
    patient_name = fields.get("patient_name", "Patient")
    language = fields.get("language", "Telugu")
    print(f"\n  Patient : {patient_name}")
    print(f"  Language: {language}")

    # ── STEP 2: Explain ──────────────────────────────────────────────────
    print("\n[phase1] STEP 2 — sarvam-105b: plain-language explanation")
    explanation = explain(fields, language=language)
    EXPLAIN_OUT.write_text(
        json.dumps(explanation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → Saved to {EXPLAIN_OUT}")

    # ── STEP 3: Checklist ────────────────────────────────────────────────
    print("\n[phase1] STEP 3 — sarvam-105b: 30-day recovery checklist")
    checklist = generate_checklist(fields, language=language)
    CHECKLIST_OUT.write_text(
        json.dumps(checklist, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → Saved to {CHECKLIST_OUT}")

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  PHASE 1 COMPLETE")
    print("═" * 60)

    print(f"\n  Greeting : {explanation.get('greeting', '')[:120]} ...")
    print(f"\n  Explanation (first 200 chars):")
    print(f"  {explanation.get('explanation', '')[:200]} ...")

    print(f"\n  Medications decoded: {len(explanation.get('medications', []))}")
    for m in explanation.get("medications", [])[:3]:
        print(f"    • {m.get('name','')} — {m.get('what_it_does','')[:60]}")

    print(f"\n  Red flags: {len(explanation.get('red_flags', []))}")
    for rf in explanation.get("red_flags", [])[:3]:
        print(f"    ⚠  {rf[:80]}")

    print(f"\n  Week 1 focus: {checklist.get('week_1', {}).get('focus', '')}")
    print(f"  Week 1 tasks: {len(checklist.get('week_1', {}).get('daily_tasks', []))}")

    print("\n  All output files:")
    print(f"    {INGEST_OUT}")
    print(f"    {EXPLAIN_OUT}")
    print(f"    {CHECKLIST_OUT}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mock-ingest",
        action="store_true",
        help="Skip Vision API call and reuse saved ingest_result.json",
    )
    args = parser.parse_args()
    run(mock_ingest=args.mock_ingest)
