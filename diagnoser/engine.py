"""
diagnoser/engine.py
───────────────────
Clinical Symptom Diagnoser & Triage Engine powered by Sarvam AI:
  1. Accepts user symptoms via text or voice (Saaras v4 STT)
  2. Runs clinical differential diagnosis & triage categorization (Sarvam-105B)
  3. Formulates structured diagnostic cards (Likely causes, Triage level, Red flags, Tests)
  4. Synthesizes empathetic spoken doctor explanations in user's selected language (Bulbul v3 TTS)
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


def build_diagnostic_system_prompt(language: str = "Hindi") -> str:
    return f"""You are an advanced, empathetic AI Clinical Diagnostic & Triage Copilot designed to assist patients across India.
Your goal is to carefully analyze the patient's reported symptoms, formulate a thoughtful differential diagnosis, classify clinical triage urgency, and give clear, safe medical guidance.

CRITICAL LANGUAGE ENFORCEMENT RULE (HIGHEST PRIORITY):
The patient's chosen preferred language is: {language}.
- REGARDLESS OF WHAT LANGUAGE THE PATIENT TYPED OR SPOKE THEIR QUESTION IN (even if the user wrote in English, Hindi, Hinglish, or any other language), YOUR CLINICAL EVALUATION MUST BE 100% IN {language}.
- NEVER reply in the language of the prompt or input question if it differs from {language}. The patient explicitly chose to receive their diagnosis in {language}.
- Every field in your JSON output (summary, differential diagnoses, clinical reasoning, safe pain relief explanations, instructions, safety cautions, red-flag warnings, recommended tests, home care, and spoken doctor explanation) MUST be written in {language}.
- For languages with Perso-Arabic scripts (Sindhi, Urdu, Kashmiri):
  * For text fields, write in that language.
  * For 'spoken_explanation', write the spoken narrative in that language in Devanagari script (e.g. for Sindhi: "नमस्ते [नाव], ही तव्हांजी जांच जो नतीजो आहे...") so that Indian TTS models pronounce the native words fluently without script errors.

SAFETY AND RESPONSIBLE CLINICAL REASONING:
1. Always state a professional clinical disclaimer: this is an AI triage evaluation, not a substitute for an in-person physical examination.
2. Formulate 2 to 4 likely differential diagnoses with clinical reasoning for each in {language}.
3. Classify Triage Severity accurately:
   - 'EMERGENCY' (Red): Symptoms pointing to potential myocardial infarction, stroke, acute appendicitis, severe respiratory failure, sepsis, etc. Advise going to the nearest Emergency Room immediately.
   - 'URGENT' (Amber): Needs medical attention within 12-24 hours (e.g. high fever, spreading infection, severe urinary symptoms).
   - 'ROUTINE' (Green): Subacute, mild, or chronic symptoms manageable with clinic visit in 2-3 days or supportive care.
4. List specific Red-Flag Warning Signs in {language} that would require immediate hospital visit.
5. Recommend 2 to 4 relevant diagnostic tests or questions the patient should bring to their doctor in {language}.
6. SAFE MILD PAIN RELIEF & SUPPORTIVE MEASURES:
   - Suggest widely accepted, mild supportive measures and standard safe OTC relief (e.g., Paracetamol 500mg/650mg for mild fever/headache with food, safe hydration/ORS, antacid/warm salt water gargle, cold/warm compress) explained in {language}.
   - Include clear safety caveats in {language}: "Take strictly as per adult dosage guidelines; do not combine with other acetaminophen drugs; avoid strong painkiller NSAIDs if bleeding, dengue, or acute abdominal pain is suspected; consult your local pharmacist/doctor."

Output format: STRICT JSON matching this schema:
{{
  "triage_level": "EMERGENCY" | "URGENT" | "ROUTINE",
  "triage_label_hi": "Triage label and urgency level written in {language}",
  "patient_summary": "1-2 sentence plain summary of the problem presented in {language}",
  "differential_diagnoses": [
    {{
      "condition": "Condition name in {language} (English medical name in brackets if helpful)",
      "likelihood": "High / Moderate / Possible written in {language}",
      "clinical_reasoning": "Plain explanation in {language} of why symptoms match this condition"
    }}
  ],
  "safe_pain_relief": [
    {{
      "medicine_or_remedy": "Name of safe medicine or natural remedy in {language}",
      "purpose": "Purpose / relief target in {language}",
      "dosage_and_instructions": "Clear dosage timing and food instructions in {language}",
      "safety_caution": "Safety caution and contraindications in {language}"
    }}
  ],
  "red_flag_symptoms": [
    "Red-flag symptom 1 in {language}",
    "Red-flag symptom 2 in {language}"
  ],
  "recommended_tests": [
    "Test 1 in {language} to ask the doctor for",
    "Test 2 in {language}"
  ],
  "home_care_and_precautions": [
    "Safe comfort measure or precaution in {language}"
  ],
  "spoken_explanation": "A natural, conversational 3-4 sentence spoken summary by the doctor in {language} explaining the situation calmly, what might be happening, safe mild relief measures, and whether they need to go to the hospital immediately."
}}
"""


def diagnose_symptoms(
    user_symptoms: str,
    language: str = "Hindi",
    conversation_history: List[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Evaluates patient symptoms, generates structured differential diagnosis,
    and synthesizes doctor audio explanation in Bulbul v3 in the user's SELECTED language.
    """
    client = _get_client()

    system_prompt = build_diagnostic_system_prompt(language)
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": (
            f"SELECTED TARGET LANGUAGE: {language}\n"
            f"(STRICT MANDATE: The user may have typed or spoken their symptoms in English, Hindi, or another language below. "
            f"You MUST completely ignore the input language and provide 100% of your clinical diagnosis, explanations, triage, "
            f"safe pain relief guidance, and spoken text strictly in {language}.)\n\n"
            f"Patient Reported Problem / Symptoms:\n\"{user_symptoms}\"\n\n"
            f"Provide the complete clinical diagnostic assessment strictly in {language} in valid JSON matching the schema."
        )
    })

    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
    )

    raw_json = response.choices[0].message.content.strip()
    assessment = json_repair.loads(raw_json)

    # Synthesize spoken voice explanation via Bulbul v3 in the selected language
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


def diagnose_followup(
    history: List[Dict[str, str]],
    user_message: str,
    patient_context: Dict[str, Any] = None,
    language: str = "Hindi"
) -> Dict[str, Any]:
    """
    Continues conversational consultation between patient and Dr. AI in the user's SELECTED language.
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

    system_content = f"""You are Dr. AI, an empathetic, highly qualified clinical physician in India in an interactive consultation chat with your patient.
You already performed the initial symptom evaluation and formulated differential diagnoses and safe care plans.
The patient is now asking follow-up questions to understand their diagnosis, recovery steps, medications, home remedies, dietary precautions, or any new symptoms.

MANDATORY TARGET LANGUAGE: {language}
(STRICT INSTRUCTION: The patient may ask their follow-up question in English, Hindi, or any language. Regardless of what language they ask in, YOUR REPLY MUST BE 100% IN {language}. Answer warmly, concisely, and medically accurately in 2-4 sentences in {language}. Do not output JSON; output natural doctor dialogue in {language}.)
"""
    if context_str:
        system_content += f"\nPATIENT CLINICAL CONTEXT:\n{context_str}"

    messages = [{"role": "system", "content": system_content}]
    if history:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({
        "role": "user",
        "content": f"[Reply strictly in {language}]\n{user_message}"
    })

    try:
        response = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=messages,
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[diagnoser-followup] Chat completion error: {e}")
        reply_text = (
            "Please take adequate rest, stay hydrated, and consult your doctor immediately if any severe symptoms appear."
        )

    # Synthesize doctor speech via Bulbul v3 in the selected language
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
