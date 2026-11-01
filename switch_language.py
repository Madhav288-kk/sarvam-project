"""
switch_language.py
──────────────────
Switches the entire platform's language across:
  1. Plain-Language Explanation (sarvam-105b)
  2. 30-Day Recovery Checklist (sarvam-105b)
  3. Patient Spoken Audio (Bulbul v3 TTS)
  4. Outbound Voice Check-in Turns (Saaras v4 STT + Sarvam 105B + Bulbul v3)
  5. SQLite Patient Record & Live Dashboard

Usage:
    python switch_language.py Hindi
    python switch_language.py Tamil
    python switch_language.py Telugu
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

from decoder.explain import explain
from decoder.checklist import generate_checklist
from decoder.speak import text_to_speech_pipeline
from db.patients import save_patient, get_patient
from companion.tts import speak_turn
from companion.voice_loop import run_voice_checkin_session


HINDI_PATIENT_UTTERANCES = [
    # Turn 1: Identity confirm
    "हाँ जी, मैं रमैया वेंकटेश ही बोल रहा हूँ।",
    # Turn 2: Missed meds
    "कल से पेट में बहुत दर्द और उल्टी जैसा लग रहा था, इसलिए मैंने मेटफॉर्मिन और बीपी की गोलियां नहीं लीं।",
    # Turn 3: Urgent symptom
    "मुझे छाती में बहुत भारीपन और दर्द महसूस हो रहा है, और सांस लेने में बहुत तकलीफ हो रही है। कृपया जल्दी मदद कीजिए।",
]


def switch_language(target_language: str = "Hindi"):
    print("\n" + "═" * 60)
    print(f"  SWITCHING CARE PLATFORM TO: {target_language.upper()}")
    print("═" * 60)

    # 1. Ingest Data
    ingest_file = Path("mock/ingest_result.json")
    if not ingest_file.exists():
        sys.exit("ingest_result.json not found. Run Phase 1 first.")

    data = json.loads(ingest_file.read_text(encoding="utf-8"))
    fields = data.get("fields", data)

    # 2. Generate Explanation in Target Language
    print(f"\n[1/4] Generating plain-language explanation in {target_language} (sarvam-105b)...")
    explanation = explain(fields, language=target_language)
    Path("mock/explain_result.json").write_text(
        json.dumps(explanation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Greeting: {explanation.get('greeting', '')[:80]}...")

    # 3. Generate Checklist in Target Language
    print(f"\n[2/4] Generating 30-day recovery checklist in {target_language} (sarvam-105b)...")
    checklist = generate_checklist(fields, language=target_language)
    Path("mock/checklist_result.json").write_text(
        json.dumps(checklist, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    w1_focus = checklist.get("week_1", {}).get("focus", "")
    print(f"  Week 1 Focus: {w1_focus[:80]}...")

    # 4. Synthesize Spoken Audio in Target Language
    print(f"\n[3/4] Synthesizing spoken audio via Bulbul v3 ({target_language})...")
    audio_path = text_to_speech_pipeline(
        explanation,
        language_name=target_language,
        output_path=Path("mock/patient_explanation.wav"),
        speaker="ritu",
    )
    print(f"  Generated Audio: {audio_path} ({audio_path.stat().st_size / 1024:.1f} KB)")

    # 5. Update Database Record
    patient_record = {
        "patient_id": fields.get("patient_id", "APH-2024-087432"),
        "name": fields.get("patient_name", "Ramaiah Venkatesh"),
        "age": fields.get("age", "62"),
        "gender": fields.get("gender", "Male"),
        "phone": "+91-98490-33214",
        "language": target_language,
        "discharge_date": fields.get("discharge_date", "25-Oct-2024"),
        "diagnoses": fields.get("diagnoses", []),
        "medications": fields.get("medications", []),
        "follow_ups": fields.get("follow_up_dates", []),
        "checklist": checklist,
    }
    save_patient(patient_record)
    print(f"\n[4/4] Updated patient record in SQLite to {target_language}.")

    # 6. Run Voice Call in Target Language
    print(f"\n[5/5] Running outbound voice check-in in {target_language}...")
    audio_dir = Path("mock/voice_call_session")
    audio_dir.mkdir(parents=True, exist_ok=True)

    patient_audio_bytes = []
    for idx, text in enumerate(HINDI_PATIENT_UTTERANCES, 1):
        target_f = audio_dir / f"patient_input_turn_{idx}.wav"
        print(f"  • Synthesizing patient utterance {idx} ({target_language}): '{text[:35]}...'")
        ab = speak_turn(text, language=target_language, speaker="shubh", pace=0.9, save_to=target_f)
        patient_audio_bytes.append(ab)

    call_result = run_voice_checkin_session(
        patient=patient_record,
        patient_audio_turns=patient_audio_bytes,
        output_audio_dir=audio_dir,
    )

    print("\n" + "═" * 60)
    print(f"  LANGUAGE SWITCH TO {target_language.upper()} COMPLETE!")
    print("═" * 60)
    print(f"  Dashboard updated: http://localhost:8080")
    print(f"  Audio player now plays {target_language} Bulbul v3 voice")
    print(f"  Call transcript now reflects {target_language} Saaras v4 + Sarvam 105B turns")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "Hindi"
    switch_language(lang)
