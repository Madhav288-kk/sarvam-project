"""
phase4_run.py
──────────────
Phase 4 runner: Full Voice Loop with Streaming STT (Saaras v4) + TTS (Bulbul v3).
Simulates a live phone call session with real audio input and output:
  1. Patient speaks in Telugu (audio generated with male patient persona).
  2. Saaras v4 transcribes the patient's audio into text in real time.
  3. sarvam-105b processes the clinical conversation.
  4. Bulbul v3 synthesizes the nurse agent's Telugu response audio into WAV files.
  5. Post-call evaluation triggers Mayura Translate and coordinator escalation alert.

Usage:
    python phase4_run.py
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

from db.patients import get_patient, init_db
from companion.tts import speak_turn
from companion.voice_loop import run_voice_checkin_session

AUDIO_DIR = Path("mock/voice_call_session")


def prepare_simulated_patient_audio(language: str = "Telugu") -> list:
    """
    Synthesizes realistic patient audio inputs using Bulbul v3 (male patient persona 'shubh').
    This simulates audio streaming in from the patient's phone microphone.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    patient_utterances = [
        # Turn 1: Confirmation
        "అవునండీ, నేను రామయ్యనే మాట్లాడుతున్నాను.",
        # Turn 2: Missed medication disclosure
        "నిన్నటి నుంచి కడుపు నొప్పిగా ఉండటం వల్ల నేను మెట్ఫార్మిన్ మరియు బీపీ మాత్రలు వేసుకోలేదు.",
        # Turn 3: Acute red-flag symptom report
        "నాకు ఛాతీలో చాలా బరువుగా నొప్పిగా ఉంది, ఊపిరి ఆడటం లేదు, దయచేసి సహాయం చేయండి.",
    ]

    patient_audio_bytes = []
    print("\n[setup] Generating simulated patient phone audio streams (persona: shubh)...")
    for idx, text in enumerate(patient_utterances, 1):
        target_file = AUDIO_DIR / f"patient_input_turn_{idx}.wav"
        print(f"  • Generating patient audio {idx}: '{text[:40]}...'")
        audio = speak_turn(text, language=language, speaker="shubh", pace=0.9, save_to=target_file)
        patient_audio_bytes.append(audio)

    return patient_audio_bytes


def run():
    print("\n" + "═" * 60)
    print("  POST-DISCHARGE CARE PLATFORM — Phase 4: Voice Loop")
    print("═" * 60)

    init_db()
    patient = get_patient("APH-2024-087432")
    if not patient:
        sys.exit("Patient record not found. Run phase3_run.py first.")

    print(f"\n[phase4] Target Patient: {patient['name']} | ID: {patient['patient_id']}")
    print(f"[phase4] Native Language: {patient['language']} | Tel: {patient['phone']}")

    # 1. Synthesize patient's voice audio turns
    patient_audio = prepare_simulated_patient_audio(language=patient["language"])

    # 2. Run full bidirectional voice loop
    session_result = run_voice_checkin_session(
        patient=patient,
        patient_audio_turns=patient_audio,
        output_audio_dir=AUDIO_DIR,
    )

    # 3. Present Results
    print("\n" + "═" * 60)
    print("  PHASE 4 COMPLETE: Voice Loop Successfully Verified!")
    print("═" * 60)

    eval_data = session_result["evaluation"]
    esc = session_result.get("escalation")

    print("\n📊 SESSION SUMMARY:")
    print(f"  Database Log ID : #{session_result['log_id']}")
    print(f"  Dialogue Turns  : {len(session_result['transcript'])}")
    print(f"  Flags Detected  : {eval_data.get('flags', [])}")
    print(f"  Missed Meds     : {eval_data.get('missed_medications', [])}")
    print(f"  Reported Symptoms: {eval_data.get('symptoms_reported', [])}")

    if esc:
        print("\n🚨 AUTOMATED ESCALATION PACKET (via Mayura Translate):")
        print(f"  Alert ID        : {esc['alert_id']}")
        print(f"  Priority Level  : {esc['priority']}")
        print(f"  English Notes   : {esc['patient_voice_notes_en']}")
        print(f"  Recommended Act : {esc['recommended_action']}")

    print("\n📁 AUDIO RECORDINGS SAVED ON DISK:")
    for f in AUDIO_DIR.glob("*.wav"):
        print(f"  🔊 {f.name} ({f.stat().st_size / 1024:.1f} KB)")

    print("═" * 60 + "\n")


if __name__ == "__main__":
    run()
