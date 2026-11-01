"""
diagnoser/engine.py
───────────────────
Clinical Symptom Diagnoser & Triage Engine powered by Sarvam AI:
  1. Accepts user symptoms via text or voice (Saaras v4 STT)
  2. Runs clinical differential diagnosis & triage categorization (Sarvam-105B)
  3. Formulates structured diagnostic cards (Likely causes, Triage level, Red flags, Tests)
  4. Synthesizes empathetic spoken doctor explanations in Hindi/Indic (Bulbul v3 TTS)
"""

import os
import sys
import json
import base64
from pathlib import Path
from typing import Dict, Any, List

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sarvamai import SarvamAI
import json_repair
from companion.tts import speak_turn
from companion.stt import transcribe_audio_bytes


def _get_client():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set.")
    return SarvamAI(api_subscription_key=key)


DIAGNOSTIC_SYSTEM_PROMPT = """You are an advanced, empathetic AI Clinical Diagnostic & Triage Copilot designed to assist patients in India.
Your goal is to carefully analyze the patient's reported symptoms, formulate a thoughtful differential diagnosis, classify clinical triage urgency, and give clear, safe medical guidance.

SAFETY AND RESPONSIBLE CLINICAL REASONING:
1. Always state a professional clinical disclaimer: this is an AI triage evaluation, not a substitute for an in-person physical examination.
2. Formulate 2 to 4 likely differential diagnoses with clinical reasoning for each.
3. Classify Triage Severity accurately:
   - 'EMERGENCY' (Red): Symptoms pointing to potential myocardial infarction, stroke, acute appendicitis, severe respiratory failure, sepsis, etc. Advise going to the nearest Emergency Room immediately.
   - 'URGENT' (Amber): Needs medical attention within 12-24 hours (e.g. high fever, spreading infection, severe urinary symptoms).
   - 'ROUTINE' (Green): Subacute, mild, or chronic symptoms manageable with clinic visit in 2-3 days or supportive care.
4. List specific Red-Flag Warning Signs that would require immediate hospital visit.
5. Recommend 2 to 4 relevant diagnostic tests or questions the patient should bring to their doctor.
6. SAFE MILD PAIN RELIEF & SUPPORTIVE MEASURES (कम से कम दुष्प्रभाव वाली प्राथमिक राहत):
   - Suggest widely accepted, mild supportive measures and standard safe OTC relief (e.g., Paracetamol 500mg/650mg for mild fever/headache with food, safe hydration/ORS, antacid/warm salt water gargle, cold/warm compress).
   - Include clear safety caveats: "Take strictly as per adult dosage guidelines; do not combine with other acetaminophen drugs; avoid strong painkiller NSAIDs if bleeding, dengue, or acute abdominal pain is suspected; consult your local pharmacist/doctor."

LANGUAGE REQUIREMENT:
Generate the entire response in fluent, empathetic Hindi (or the user's preferred Indic language). Keep medical terms easily understandable with Hindi/English brackets where helpful.

Output format: STRICT JSON matching this schema:
{
  "triage_level": "EMERGENCY" | "URGENT" | "ROUTINE",
  "triage_label_hi": "आपातकालीन स्थिति (तत्काल अस्पताल जाएं)" | "त्वरित चिकित्सा परामर्श (24 घंटे में डॉक्टर को दिखाएं)" | "सामान्य परामर्श (नियमित जांच)",
  "patient_summary": "1-2 sentence plain Hindi summary of the problem presented",
  "differential_diagnoses": [
    {
      "condition": "Condition name in Hindi (English)",
      "likelihood": "उच्च (High)" | "मध्यम (Moderate)" | "संभावित (Possible)",
      "clinical_reasoning": "Plain Hindi explanation of why symptoms match this condition"
    }
  ],
  "safe_pain_relief": [
    {
      "medicine_or_remedy": "Name of safe medicine or natural remedy (e.g., पैरासिटामोल 500mg / ORS घोल / सिकाई)",
      "purpose": "किस दर्द या परेशानी से राहत के लिए",
      "dosage_and_instructions": "खाने के बाद, सुरक्षित अंतराल (जैसे 6-8 घंटे में आवश्यकतानुसार)",
      "safety_caution": "सावधानी (खाली पेट न लें, लीवर/किडनी समस्या में डॉक्टर से पूछें)"
    }
  ],
  "red_flag_symptoms": [
    "Red-flag symptom 1 in Hindi",
    "Red-flag symptom 2 in Hindi"
  ],
  "recommended_tests": [
    "Test 1 to ask the doctor for (e.g., अल्ट्रासाउंड / Blood Test)",
    "Test 2"
  ],
  "home_care_and_precautions": [
    "Safe comfort measure or precaution (e.g., पानी की पर्याप्त मात्रा लें)"
  ],
  "spoken_explanation": "A natural, conversational 3-4 sentence spoken summary by the doctor in Hindi explaining the situation calmly, what might be happening, safe mild relief measures, and whether they need to go to the hospital immediately."
}
"""


def diagnose_symptoms(
    user_symptoms: str,
    language: str = "Hindi",
    conversation_history: List[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Evaluates patient symptoms, generates structured differential diagnosis,
    and synthesizes doctor audio explanation in Bulbul v3.
    """
    client = _get_client()

    messages = [{"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": f"Language: {language}\nPatient Reported Problem / Symptoms:\n\"{user_symptoms}\"\n\nProvide the clinical diagnostic assessment in strict JSON."
    })

    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
    )

    raw_json = response.choices[0].message.content.strip()
    assessment = json_repair.loads(raw_json)

    # Synthesize spoken voice explanation via Bulbul v3
    spoken_text = assessment.get("spoken_explanation", "")
    audio_base64 = None
    if spoken_text:
        try:
            audio_bytes = speak_turn(
                spoken_text,
                language=language,
                speaker="ritu",
                pace=0.92,
            )
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            print(f"[diagnoser] Audio synthesis warning: {e}")

    assessment["audio_base64"] = audio_base64
    return assessment


FOLLOWUP_SYSTEM_PROMPT = """You are Dr. AI, an empathetic, highly qualified clinical physician in India in an interactive consultation chat with your patient.
You already performed the initial symptom evaluation and formulated differential diagnoses and safe care plans.
The patient is now asking follow-up questions to understand their diagnosis, recovery steps, medications, home remedies, dietary precautions, or any new symptoms.

CLINICAL CONSULTATION PRINCIPLES:
1. Speak warmly, respectfully, and conversationally in empathetic Hindi (or the patient's preferred language).
2. Answer the specific question directly, giving actionable and medically accurate advice.
3. If they describe new red-flag warning signs (e.g., chest pain, shortness of breath, blood, fainting), alert them clearly to seek emergency care.
4. Keep each response concise and easy to understand (2 to 4 sentences). Do not output JSON; output natural doctor dialogue.
"""


def diagnose_followup(
    history: List[Dict[str, str]],
    user_message: str,
    patient_context: Dict[str, Any] = None,
    language: str = "Hindi"
) -> Dict[str, Any]:
    """
    Continues conversational consultation between patient and Dr. AI.
    """
    client = _get_client()

    context_str = ""
    if patient_context:
        name = patient_context.get("name", "Patient")
        age = patient_context.get("age", "")
        gender = patient_context.get("gender", "")
        initial_diag = patient_context.get("initial_diagnosis", "")
        initial_symptoms = patient_context.get("initial_symptoms", "")
        context_str = (
            f"Patient Profile: {name}, {age} years, {gender}.\n"
            f"Initial Symptoms Reported: {initial_symptoms}\n"
            f"Initial AI Diagnosis & Triage: {initial_diag}\n"
        )

    system_content = FOLLOWUP_SYSTEM_PROMPT
    if context_str:
        system_content += f"\nPATIENT CLINICAL CONTEXT:\n{context_str}"
    system_content += f"\nConsultation Language: {language}"

    messages = [{"role": "system", "content": system_content}]
    if history:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=messages,
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[diagnoser-followup] Chat completion error: {e}")
        reply_text = (
            "हाँ, आप अपनी सेहत के अनुसार हल्का और सुपाच्य भोजन ले सकते हैं। "
            "कृपया पर्याप्त आराम करें, पर्याप्त पानी पिएं और अगर कोई नया गंभीर लक्षण दिखाई दे तो तुरंत डॉक्टर से संपर्क करें।"
        )

    # Synthesize doctor speech via Bulbul v3
    audio_base64 = None
    try:
        audio_bytes = speak_turn(
            reply_text,
            language=language,
            speaker="ritu",
            pace=0.92,
        )
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        print(f"[diagnoser-followup] Audio synthesis warning: {e}")

    updated_history = list(history or [])
    updated_history.append({"role": "user", "content": user_message})
    updated_history.append({"role": "assistant", "content": reply_text})

    return {
        "reply": reply_text,
        "audio_base64": audio_base64,
        "history": updated_history
    }
