"""
companion/escalate.py
─────────────────────
Handles clinical escalation of detected anomalies from check-in calls.
Leverages Sarvam Mayura Translate to convert regional Indic patient reports
into English for hospital coordinator alerts.
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Dict, Any, List

API_BASE = "https://api.sarvam.ai"

LANGUAGE_CODE_MAP = {
    "telugu": "te-IN",
    "hindi": "hi-IN",
    "tamil": "ta-IN",
    "bengali": "bn-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "punjabi": "pa-IN",
    "odia": "od-IN",
    "english": "en-IN",
}


def _headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set.")
    return {"api-subscription-key": key, "Content-Type": "application/json"}


def translate_to_english(text: str, source_language: str = "Telugu") -> str:
    """Translates regional text to English using Sarvam Mayura model."""
    if not text or not text.strip():
        return ""
    src_code = LANGUAGE_CODE_MAP.get(source_language.lower(), "auto")
    if src_code == "en-IN":
        return text

    payload = {
        "input": text,
        "source_language_code": src_code if src_code != "auto" else "te-IN",
        "target_language_code": "en-IN",
        "mode": "formal",
        "model": "mayura:v1",
    }
    try:
        resp = requests.post(f"{API_BASE}/translate", headers=_headers(), json=payload, timeout=30)
        if resp.ok:
            return resp.json().get("translated_text", text)
    except Exception as e:
        print(f"[escalate] Translation warning: {e}")
    return text


def create_escalation_alert(
    patient: Dict[str, Any],
    flags: List[str],
    patient_notes: str,
    adherence_issues: List[str],
    symptoms_reported: List[str],
    webhook_url: str = None,
) -> Dict[str, Any]:
    """
    Constructs an actionable escalation alert.
    Translates patient feedback to English and calculates priority severity.
    """
    # 1. Determine severity
    has_urgent_symptom = "URGENT_SYMPTOM" in flags or any(
        s in str(symptoms_reported).lower() for s in ["chest", "breath", "dizzy", "pain", "swelling", "fever"]
    )
    has_missed_dose = "MISSED_DOSE" in flags or len(adherence_issues) > 0

    if has_urgent_symptom:
        priority = "CRITICAL - IMMEDIATE INTERVENTION REQUIRED"
        recommended_action = "Dispatch ambulance or arrange emergency telehealth evaluation immediately."
    elif has_missed_dose:
        priority = "HIGH - CLINICAL FOLLOW-UP REQUIRED"
        recommended_action = "Nurse/Coordinator to place follow-up call within 2 hours to address adherence barriers."
    else:
        priority = "MEDIUM - ROUTINE ATTENTION"
        recommended_action = "Review during standard morning post-discharge rounds."

    # 2. Translate regional patient feedback
    print(f"[escalate] Translating patient report via Mayura Translate ({patient.get('language', 'Telugu')} -> English)...")
    translated_notes = translate_to_english(patient_notes, source_language=patient.get("language", "Telugu"))
    translated_symptoms = [
        translate_to_english(s, source_language=patient.get("language", "Telugu")) for s in symptoms_reported
    ]

    alert_packet = {
        "alert_id": f"ESC-{patient.get('patient_id', 'UNKNOWN')[-6:]}-{os.urandom(2).hex()}",
        "priority": priority,
        "patient_id": patient.get("patient_id"),
        "patient_name": patient.get("name"),
        "phone": patient.get("phone"),
        "language": patient.get("language"),
        "flags": flags,
        "missed_medications": adherence_issues,
        "reported_symptoms": symptoms_reported,
        "reported_symptoms_en": translated_symptoms,
        "patient_voice_notes_original": patient_notes,
        "patient_voice_notes_en": translated_notes,
        "recommended_action": recommended_action,
    }

    # 3. Optional Webhook dispatch
    if webhook_url:
        try:
            requests.post(webhook_url, json=alert_packet, timeout=10)
        except Exception as e:
            print(f"[escalate] Webhook dispatch error: {e}")

    return alert_packet
