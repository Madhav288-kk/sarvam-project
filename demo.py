"""
demo.py
───────
Interactive CLI Demo for the Sarvam AI Post-Discharge Platform.
Allows you to:
  1. Roleplay a live check-in call with Sarvam-105B & Bulbul v3 voice.
  2. Play the native Hindi discharge summary voice explanation.
  3. Trigger real-time clinical escalation and view Mayura translations.
  4. Launch the web dashboard in your browser.

Usage:
    python demo.py
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

from db.patients import get_patient, init_db, log_checkin
from companion.checkin import generate_agent_reply, evaluate_call_outcome
from companion.tts import speak_turn
from companion.escalate import create_escalation_alert


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def interactive_call_simulation():
    init_db()
    patient = get_patient("APH-2024-087432")
    if not patient:
        print("[!] Patient record not found. Run python phase3_run.py first.")
        input("\nPress Enter to return...")
        return

    lang = patient.get("language", "Hindi")
    print("\n" + "═" * 65)
    print(f"  LIVE OUTBOUND VOICE CALL SIMULATION ({lang.upper()})")
    print("═" * 65)
    print(f"  Patient Name : {patient['name']}")
    print(f"  Hospital     : Apollo Hospitals (Dr. Suresh Reddy)")
    print(f"  Prescription : {', '.join([m.get('name', str(m)) for m in patient.get('medications', [])[:4]])}...")
    print("─" * 65)
    print("  TIP: You are roleplaying the patient.")
    print("  You can reply in Hindi, Hinglish, or English.")
    print("  Try saying something normal ('All good, took my pills') or test")
    print("  an escalation ('I forgot my BP medicine and my chest hurts').")
    print("  Type 'quit' or 'bye' when you want to hang up.")
    print("═" * 65 + "\n")

    history = []
    call_audio_dir = Path("mock/demo_call_audio")
    call_audio_dir.mkdir(parents=True, exist_ok=True)

    # Turn 0: Agent greeting
    print("📞 [Connecting outbound call to patient...] Ringing...\n")
    agent_msg = generate_agent_reply(patient, history)
    history.append({"role": "assistant", "content": agent_msg})

    wav_0 = call_audio_dir / "agent_turn_0.wav"
    speak_turn(agent_msg, language=lang, save_to=wav_0)

    print(f"🤖 Hospital Agent ({lang}):\n   \"{agent_msg}\"")
    print(f"   [Audio synthesized: {wav_0.name}]\n")

    turn_count = 1
    while True:
        try:
            user_input = input("👤 You (Patient): ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input or user_input.lower() in ["quit", "exit", "bye", "hangup"]:
            print("\n[Call ended by patient]")
            break

        history.append({"role": "user", "content": user_input})

        print("\n⏳ Agent is thinking (sarvam-105b)...")
        agent_reply = generate_agent_reply(patient, history)
        history.append({"role": "assistant", "content": agent_reply})

        wav_n = call_audio_dir / f"agent_turn_{turn_count}.wav"
        speak_turn(agent_reply, language=lang, save_to=wav_n)

        print(f"\n🤖 Hospital Agent ({lang}):\n   \"{agent_reply}\"")
        print(f"   [Audio synthesized: {wav_n.name}]\n")
        turn_count += 1

    # Call Outcome Evaluation
    print("\n" + "═" * 65)
    print("  POST-CALL CLINICAL EVALUATION (sarvam-105b-conversations)")
    print("═" * 65)
    evaluation = evaluate_call_outcome(patient, history)

    flags = evaluation.get("flags", [])
    print(f"  Flags Detected   : {flags if flags else 'None (Adherent)'}")
    print(f"  Adherence Status : {json.dumps(evaluation.get('adherence', {}), ensure_ascii=False)}")
    print(f"  Symptoms Reported: {evaluation.get('symptoms_reported', [])}")
    print(f"  Summary Notes    : {evaluation.get('patient_summary_notes', '')}")

    escalation = None
    if flags:
        print("\n🚨 ANOMALY DETECTED! Running Sarvam Mayura Translate...")
        escalation = create_escalation_alert(
            patient=patient,
            flags=flags,
            patient_notes=evaluation.get("patient_summary_notes", ""),
            adherence_issues=evaluation.get("missed_medications", []),
            symptoms_reported=evaluation.get("symptoms_reported", []),
        )

        print("\n" + "─" * 65)
        print(f"  🚨 INCIDENT ALERT [{escalation['priority']}]")
        print("─" * 65)
        print(f"  Alert ID        : {escalation['alert_id']}")
        print(f"  Flags           : {', '.join(escalation['flags'])}")
        print(f"  Mayura Trans.   : {escalation['patient_voice_notes_en']}")
        print(f"  Action Required : {escalation['recommended_action']}")
        print("─" * 65)

    log_id = log_checkin(
        patient_id=patient["patient_id"],
        transcript=history,
        adherence=evaluation.get("adherence", {}),
        symptoms=evaluation.get("symptoms_reported", []),
        flags=flags,
        escalated=bool(flags),
        escalation_details=escalation,
    )
    print(f"\n✔ Call session saved to SQLite DB (Log #{log_id})")
    print("✔ Refresh http://localhost:8080 to see this call live on the coordinator dashboard!")
    input("\nPress Enter to return to menu...")


def play_audio():
    audio_path = Path("mock/patient_explanation.wav")
    if not audio_path.exists():
        print(f"[!] Audio file not found at {audio_path}. Run Phase 2 first.")
    else:
        print(f"\n[Playing] {audio_path.resolve()}")
        try:
            os.startfile(str(audio_path.resolve()))
            print("✔ Opened audio in your default media player.")
        except Exception as e:
            print(f"[!] Could not auto-play: {e}")
            print(f"    You can open it manually at: {audio_path.resolve()}")
    input("\nPress Enter to return...")


def open_dashboard():
    url = "http://localhost:8080"
    print(f"\n[Opening Dashboard] {url} in your browser...")
    try:
        os.startfile(url)
        print("✔ Dashboard opened!")
    except Exception as e:
        print(f"Open manually in your browser: {url}")
    input("\nPress Enter to return...")


def main_menu():
    while True:
        clear_screen()
        print("╔═════════════════════════════════════════════════════════════════╗")
        print("║          SARVAM AI — POST-DISCHARGE CARE COMPANION              ║")
        print("║                     INTERACTIVE DEMO                            ║")
        print("╚═════════════════════════════════════════════════════════════════╝")
        print(" 1. 📞 Roleplay a Live Outbound Voice Call (Simulate Patient)")
        print(" 2. 🔊 Play Native Hindi Spoken Discharge Summary (Bulbul v3)")
        print(" 3. 🌐 Open Web Care Coordinator Dashboard in Browser")
        print(" 4. 🔄 Switch Platform Language (Hindi / Telugu / Tamil / etc.)")
        print(" 5. 🚪 Exit")
        print("─" * 65)
        choice = input("Select an option (1-5): ").strip()

        if choice == "1":
            interactive_call_simulation()
        elif choice == "2":
            play_audio()
        elif choice == "3":
            open_dashboard()
        elif choice == "4":
            new_lang = input("\nEnter target language (e.g. Telugu, Tamil, Bengali, Hindi): ").strip()
            if new_lang:
                os.system(f'python switch_language.py "{new_lang}"')
                input("\nLanguage switched! Press Enter to continue...")
        elif choice == "5":
            print("\nExiting demo. Thank you!")
            break


if __name__ == "__main__":
    main_menu()
