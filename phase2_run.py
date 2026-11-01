"""
phase2_run.py
──────────────
Phase 2 runner: Voice Output via Bulbul v3 TTS.
Takes the plain-language Telugu explanation generated in Phase 1 and converts
it into a high-quality spoken audio file (patient_explanation.wav).

Usage:
    python phase2_run.py
"""

import os
import sys
import json
from pathlib import Path

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

from decoder.speak import text_to_speech_pipeline

EXPLAIN_PATH = Path("mock/explain_result.json")
OUTPUT_AUDIO = Path("mock/patient_explanation.wav")


def run():
    print("\n" + "═" * 60)
    print("  POST-DISCHARGE CARE PLATFORM — Phase 2: Voice Generation")
    print("═" * 60)

    if not EXPLAIN_PATH.exists():
        sys.exit(f"Error: {EXPLAIN_PATH} not found. Run phase1_run.py first.")

    data = json.loads(EXPLAIN_PATH.read_text(encoding="utf-8"))
    
    print("\n[phase2] Loading patient explanation data...")
    print(f"  Greeting: {data.get('greeting', '')[:90]}...")
    print(f"  Medications count: {len(data.get('medications', []))}")
    print(f"  Red flags count: {len(data.get('red_flags', []))}")

    print("\n[phase2] Calling Sarvam Bulbul v3 Text-to-Speech API...")
    out_file = text_to_speech_pipeline(
        explanation_data=data,
        language_name="Telugu",
        output_path=OUTPUT_AUDIO,
        speaker="ritu",
    )

    print("\n" + "═" * 60)
    print("  PHASE 2 COMPLETE: Audio synthesized successfully!")
    print("═" * 60)
    print(f"  Output audio file: {out_file.resolve()}")
    print(f"  File size        : {len(out_file.read_bytes()) / 1024:.2f} KB")
    print(f"  Format           : WAV (Bulbul v3, 22050 Hz)")
    print(f"  Language         : Telugu (te-IN)")
    print(f"  Voice persona    : Ritu (warm, patient-facing)")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    run()
