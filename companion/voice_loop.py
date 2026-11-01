"""
companion/voice_loop.py
───────────────────────
Full end-to-end voice loop for outbound calls:
  Patient Audio In -> Saaras v4 STT -> sarvam-105b Dialogue -> Bulbul v3 TTS Audio Out.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List

from companion.stt import transcribe_audio_bytes
from companion.tts import speak_turn
from companion.checkin import generate_agent_reply, evaluate_call_outcome
from companion.escalate import create_escalation_alert
from db.patients import log_checkin


def run_voice_checkin_session(
    patient: Dict[str, Any],
    patient_audio_turns: List[bytes],
    output_audio_dir: Path = Path("mock/call_audio"),
) -> Dict[str, Any]:
    """
    Executes a complete voice call session:
    - Synthesizes agent spoken turns to disk (WAV)
    - Transcribes patient spoken input with Saaras v4
    - Analyzes dialogue with sarvam-105b
    - Detects clinical flags and translates alerts via Mayura
    """
    output_audio_dir.mkdir(parents=True, exist_ok=True)
    history = []
    call_records = []

    print(f"\n[voice_loop] Starting outbound voice call to: {patient.get('name')} ({patient.get('phone')})")
    print(f"[voice_loop] Patient Language: {patient.get('language', 'Telugu')}")

    # Turn 0: Agent Greeting
    agent_text_0 = generate_agent_reply(patient, history)
    history.append({"role": "assistant", "content": agent_text_0})
    agent_wav_0 = output_audio_dir / "agent_turn_0.wav"
    speak_turn(agent_text_0, language=patient.get("language", "Telugu"), save_to=agent_wav_0)

    print(f"\n📞 Agent (Spoken Turn 0): {agent_text_0}")
    print(f"   ↳ Synthesized Audio: {agent_wav_0.name} ({len(agent_wav_0.read_bytes()) / 1024:.1f} KB)")
    call_records.append({"turn": 0, "speaker": "agent", "text": agent_text_0, "audio": str(agent_wav_0)})

    # Subsequent conversational turns
    for idx, user_audio in enumerate(patient_audio_turns, 1):
        # 1. Speech-to-Text via Saaras v4
        print(f"\n🎤 Patient speaks (Turn {idx})... Transcribing via Saaras v4...")
        user_transcript = transcribe_audio_bytes(user_audio, language=patient.get("language", "Telugu"))
        print(f"👤 Patient Transcribed: {user_transcript}")
        history.append({"role": "user", "content": user_transcript})
        call_records.append({"turn": idx, "speaker": "patient", "text": user_transcript})

        # 2. sarvam-105b generates next spoken reply
        agent_reply = generate_agent_reply(patient, history)
        history.append({"role": "assistant", "content": agent_reply})

        # 3. Bulbul v3 synthesizes spoken response
        agent_wav_file = output_audio_dir / f"agent_turn_{idx}.wav"
        speak_turn(agent_reply, language=patient.get("language", "Telugu"), save_to=agent_wav_file)

        print(f"\n📞 Agent (Spoken Turn {idx}): {agent_reply}")
        print(f"   ↳ Synthesized Audio: {agent_wav_file.name} ({len(agent_wav_file.read_bytes()) / 1024:.1f} KB)")
        call_records.append({"turn": idx, "speaker": "agent", "text": agent_reply, "audio": str(agent_wav_file)})

    # Post-call evaluation
    print("\n[voice_loop] Call ended. Running clinical evaluation...")
    evaluation = evaluate_call_outcome(patient, history)
    flags = evaluation.get("flags", [])

    escalation = None
    if flags:
        print("\n🚨 [ESCALATION] Anomaly detected in voice check-in! Translating via Mayura...")
        escalation = create_escalation_alert(
            patient=patient,
            flags=flags,
            patient_notes=evaluation.get("patient_summary_notes", ""),
            adherence_issues=evaluation.get("missed_medications", []),
            symptoms_reported=evaluation.get("symptoms_reported", []),
        )

    log_id = log_checkin(
        patient_id=patient["patient_id"],
        transcript=history,
        adherence=evaluation.get("adherence", {}),
        symptoms=evaluation.get("symptoms_reported", []),
        flags=flags,
        escalated=bool(flags),
        escalation_details=escalation,
    )
    print(f"[voice_loop] Logged session #{log_id} to database.")

    return {
        "log_id": log_id,
        "transcript": history,
        "evaluation": evaluation,
        "escalation": escalation,
        "audio_files": [r["audio"] for r in call_records if "audio" in r],
    }
