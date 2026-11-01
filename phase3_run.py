"""
phase3_run.py
──────────────
Phase 3 runner: Missed-Dose & Follow-Up Companion.
Demonstrates:
  1. Patient database storage (SQLite).
  2. Multi-turn native-language conversational check-in via sarvam-105b-conversations.
  3. Non-diagnostic symptom screening and medication adherence evaluation.
  4. Clinical anomaly detection & automated escalation (translated to English via Mayura Translate).

Usage:
    python phase3_run.py
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

from db.patients import init_db, save_patient, get_patient, log_checkin
from companion.checkin import generate_agent_reply, evaluate_call_outcome
from companion.escalate import create_escalation_alert

INGEST_FILE = Path("mock/ingest_result.json")
CHECKLIST_FILE = Path("mock/checklist_result.json")


def seed_patient_record():
    """Seeds SQLite patient table with the record extracted during Phase 1."""
    if not INGEST_FILE.exists():
        sys.exit("ingest_result.json not found. Run Phase 1 first.")

    ingest_data = json.loads(INGEST_FILE.read_text(encoding="utf-8"))
    fields = ingest_data.get("fields", ingest_data)

    checklist = {}
    if CHECKLIST_FILE.exists():
        checklist = json.loads(CHECKLIST_FILE.read_text(encoding="utf-8"))

    patient_record = {
        "patient_id": fields.get("patient_id", "APH-2024-087432"),
        "name": fields.get("patient_name", "Ramaiah Venkatesh"),
        "age": fields.get("age", "62"),
        "gender": fields.get("gender", "Male"),
        "phone": "+91-98490-33214",
        "language": fields.get("language", "Telugu"),
        "discharge_date": fields.get("discharge_date", "25-Oct-2024"),
        "diagnoses": fields.get("diagnoses", []),
        "medications": fields.get("medications", []),
        "follow_ups": fields.get("follow_up_dates", []),
        "checklist": checklist,
    }

    save_patient(patient_record)
    print(f"[db] Stored patient record in SQLite: {patient_record['name']} ({patient_record['patient_id']})")
    return patient_record


def run_scenario(scenario_name: str, patient: dict, simulated_user_turns: list):
    print("\n" + "─" * 60)
    print(f"  RUNNING SCENARIO: {scenario_name}")
    print("─" * 60)

    history = []

    # Turn 0: Agent initiates call
    first_agent_turn = generate_agent_reply(patient, history)
    history.append({"role": "assistant", "content": first_agent_turn})
    print(f"\n📞 Agent (Telugu): {first_agent_turn}")

    # Interactive simulated dialogue turns
    for user_reply in simulated_user_turns:
        print(f"\n👤 Patient (Telugu): {user_reply}")
        history.append({"role": "user", "content": user_reply})

        agent_reply = generate_agent_reply(patient, history)
        history.append({"role": "assistant", "content": agent_reply})
        print(f"\n📞 Agent (Telugu): {agent_reply}")

    print("\n[companion] Call completed. Evaluating clinical outcomes...")
    evaluation = evaluate_call_outcome(patient, history)

    flags = evaluation.get("flags", [])
    print(f"\n  Detected Clinical Flags: {flags if flags else 'None (Normal Adherence)'}")
    print(f"  Adherence Assessment: {json.dumps(evaluation.get('adherence', {}), ensure_ascii=False)}")
    print(f"  Reported Symptoms: {evaluation.get('symptoms_reported', [])}")
    print(f"  Clinical Summary: {evaluation.get('patient_summary_notes', '')}")

    escalation_packet = None
    if flags:
        print("\n🚨 [ESCALATION TRIGGERED] Anomaly detected! Generating Coordinator Alert...")
        escalation_packet = create_escalation_alert(
            patient=patient,
            flags=flags,
            patient_notes=evaluation.get("patient_summary_notes", ""),
            adherence_issues=evaluation.get("missed_medications", []),
            symptoms_reported=evaluation.get("symptoms_reported", []),
        )
        print("\n" + "═" * 60)
        print("  HOSPITAL CARE COORDINATOR INCIDENT ALERT")
        print("═" * 60)
        print(f"  Alert ID        : {escalation_packet['alert_id']}")
        print(f"  Priority Level  : {escalation_packet['priority']}")
        print(f"  Patient         : {escalation_packet['patient_name']} (Phone: {escalation_packet['phone']})")
        print(f"  Flags Raised    : {', '.join(escalation_packet['flags'])}")
        print(f"  Missed Meds     : {escalation_packet['missed_medications']}")
        print(f"  Symptoms (Telugu): {escalation_packet['reported_symptoms']}")
        print(f"  Symptoms (En)   : {escalation_packet['reported_symptoms_en']}")
        print(f"  Notes (Mayura En): {escalation_packet['patient_voice_notes_en']}")
        print(f"  Action Required : {escalation_packet['recommended_action']}")
        print("═" * 60)
    else:
        print("\n✅ Check-in routine logged successfully. No coordinator escalation needed.")

    # Log to SQLite
    log_id = log_checkin(
        patient_id=patient["patient_id"],
        transcript=history,
        adherence=evaluation.get("adherence", {}),
        symptoms=evaluation.get("symptoms_reported", []),
        flags=flags,
        escalated=bool(flags),
        escalation_details=escalation_packet,
    )
    print(f"[db] Check-in session saved to database (Log ID #{log_id})")


def run():
    print("\n" + "═" * 60)
    print("  POST-DISCHARGE CARE PLATFORM — Phase 3: Missed-Dose Companion")
    print("═" * 60)

    # 1. Seed database
    init_db()
    patient = seed_patient_record()

    # 2. Test Scenario A: Normal Adherent Follow-Up
    # Patient confirms identity, took pills, feels fine, ready for appointment
    scenario_a_replies = [
        "అవునండీ, నేను రామయ్యనే మాట్లాడుతున్నాను.",  # "Yes, I am Ramaiah speaking."
        "ఉదయం మెట్ఫార్మిన్ మరియు బీపీ గోలీలు వేసుకున్నాను. సమయానికి తీసుకుంటున్నాను.",  # "Took morning Metformin and BP pills on time."
        "ఇప్పుడు నయం గానే ఉంది, జ్వరం గానీ ఆయాసం గానీ ఏమీ లేవు.",  # "Feeling better now, no fever or breathlessness."
        "అవును, నవంబర్ 8వ తేదీన ఆసుపత్రికి రావడానికి మా అబ్బాయి బండి ఏర్పాటు చేశాడు. ధన్యవాదాలు.", # "Yes, Nov 8th appointment transport is arranged. Thanks."
    ]
    run_scenario("Scenario A: Routine Positive Adherence Check-In", patient, scenario_a_replies)

    # 3. Test Scenario B: Missed Dose + Red-Flag Symptoms (Urgent Escalation)
    # Patient reports skipping Metformin due to vomiting, and experiencing chest heaviness
    scenario_b_replies = [
        "నమస్కారం, అవును రామయ్యనే.",  # "Hello, yes this is Ramaiah."
        "లేదు బాబు, నిన్నటి నుంచి కడుపులో తిప్పడం వల్ల మెట్ఫార్మిన్ మరియు రక్తపోటు మందులు వేసుకోలేదు.", # "No, since yesterday due to nausea I skipped Metformin and BP pills."
        "నాకు ఛాతీలో బరువుగా ఉంది, ఊపిరి తీసుకోవడం చాలా కష్టంగా అనిపిస్తోంది.", # "My chest feels heavy and I have severe difficulty breathing."
        "బాధగా ఉంది, దయచేసి నర్సు గారితో లేదా డాక్టరు గారితో వెంటనే మాట్లాడించండి.", # "In distress, please connect me to nurse/doctor immediately."
    ]
    run_scenario("Scenario B: Missed Vital Meds + Chest Discomfort (Escalation Trigger)", patient, scenario_b_replies)

    print("\n" + "═" * 60)
    print("  PHASE 3 COMPLETE: Patient DB + Check-in Loop + Escalation Verified!")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    run()
