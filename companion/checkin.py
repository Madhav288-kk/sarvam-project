"""
companion/checkin.py
────────────────────
Structured conversational check-in engine powered by sarvam-105b-conversations.
Conducts empathetic, non-diagnostic post-discharge reviews in regional Indian languages.
Evaluates medication adherence, screens for red-flag symptoms, and extracts clinical flags.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from sarvamai import SarvamAI
import json_repair

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _get_client():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set.")
    return SarvamAI(api_subscription_key=key)


def build_system_prompt(patient: Dict[str, Any]) -> str:
    meds_str = ", ".join([
        f"{m.get('name', '')} ({m.get('frequency', '')})" if isinstance(m, dict) else str(m)
        for m in patient.get("medications", [])
    ])
    follow_ups_str = ", ".join([str(f) for f in patient.get("follow_ups", [])])
    lang = patient.get("language", "Telugu")

    return f"""You are a compassionate, non-diagnostic post-discharge care companion calling from Apollo Hospitals on behalf of Dr. Suresh Reddy.
You are calling patient {patient.get('name')} who was recently discharged.

LANGUAGE CONSTRAINT:
Speak strictly and fluently in {lang}. Use warm, respectful spoken tone (use honorifics like 'గారు' in Telugu or 'जी' in Hindi).

PATIENT CLINICAL CONTEXT (GROUNDING):
- Discharged Medications: {meds_str}
- Scheduled Follow-ups: {follow_ups_str}

CONVERSATION SCRIPT PROTOCOL:
1. Greet warmly and confirm identity ("Am I speaking with {patient.get('name')}?").
2. Inquire whether they took their key medications today (specifically mention Metformin and BP medicines).
3. Conduct symptom screening: ask if they have any fever, worsening breathlessness, chest discomfort, or leg swelling.
4. Ask how they are feeling overall compared to when they left the hospital (better, same, or worse).
5. Remind them gently of their upcoming follow-up appointment.
6. If the patient mentions pain, breathlessness, or missed pills, reassure them calmly without giving medical diagnoses, and let them know the hospital care team is being notified.
7. Keep each spoken turn short, conversational, and ask ONLY ONE question at a time.
"""


def generate_agent_reply(
    patient: Dict[str, Any],
    history: List[Dict[str, str]],
) -> str:
    """
    Given the current conversation history, generates the agent's next spoken turn.
    """
    client = _get_client()
    system_prompt = build_system_prompt(patient)

    messages = [{"role": "system", "content": system_prompt}] + history
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
    )
    return response.choices[0].message.content.strip()


def evaluate_call_outcome(
    patient: Dict[str, Any],
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Analyzes the full conversation transcript and produces a structured clinical evaluation:
    {
      "adherence": {"medication_name": bool},
      "missed_medications": [str],
      "symptoms_reported": [str],
      "flags": ["MISSED_DOSE" | "URGENT_SYMPTOM" | "NEEDS_CALLBACK"],
      "patient_summary_notes": str
    }
    """
    client = _get_client()
    transcript_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])

    eval_prompt = f"""You are a clinical supervisor evaluating a completed post-discharge check-in call.
Analyze the transcript below for patient: {patient.get('name')}.

Transcript:
\"\"\"
{transcript_text}
\"\"\"

Prescribed Medications: {patient.get('medications')}

Carefully detect:
1. Did the patient report skipping or missing any medication? If yes, flag 'MISSED_DOSE'.
2. Did the patient report any warning symptoms like chest pain, breathlessness, severe cough, dizziness, or leg swelling? If yes, flag 'URGENT_SYMPTOM'.
3. Does the patient feel worse or requested assistance? If yes, flag 'NEEDS_CALLBACK'.

Output strict JSON only with this schema:
{{
  "adherence": {{"med_name": true_or_false}},
  "missed_medications": ["list of medications skipped or missed"],
  "symptoms_reported": ["list of symptoms reported by patient"],
  "flags": ["MISSED_DOSE", "URGENT_SYMPTOM", "NEEDS_CALLBACK"],
  "patient_summary_notes": "concise factual summary of patient status in 2-3 sentences"
}}
"""

    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[{"role": "user", "content": eval_prompt}],
    )

    content = response.choices[0].message.content.strip()
    return json_repair.loads(content)
