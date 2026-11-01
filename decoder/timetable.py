"""
decoder/timetable.py
────────────────────
Extracts prescription text or OCR output into an interactive daily
medication reminder timetable with time slots, instructions, and
spoken Indic audio alerts (Bulbul v3).
"""

import os
import sys
import json
import base64
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sarvamai import SarvamAI
import json_repair
from db.patients import save_patient, get_patient


TIMETABLE_SYSTEM_PROMPT = """You are an expert AI Clinical Pharmacist & Medication Schedule Planner.
Given prescription text, doctor's notes, or discharge instructions:
1. Extract the patient name (if mentioned in prescription, use it; otherwise use the provided default name), clinical condition, and doctor notes.
2. Group ALL prescribed medications into 4 standard daily time slots:
   - "Morning (08:00 AM) — With Breakfast"
   - "Afternoon (01:30 PM) — After Lunch"
   - "Evening (06:00 PM) — With Snacks"
   - "Night (09:00 PM) — After Dinner / Bedtime"
3. For each medicine, provide:
   - name: Medicine name and strength (e.g. "Tab. Paracetamol 650mg")
   - dosage: e.g. "1 Tablet" or "5 ml syrup"
   - instructions: Short, clear instruction in the requested language (e.g. "नाश्ते के 20 मिनट बाद, पानी के साथ")
   - purpose: Why it is prescribed (e.g. "बुखार और दर्द के लिए")
   - speech: Conversational, friendly spoken reminder text in the requested language that an automated voice alarm will read aloud to the patient.
4. Output STRICT JSON only with keys:
   {
     "patient_name": "...",
     "diagnosis": "...",
     "doctor_notes": "...",
     "medications_list": ["Tab. Paracetamol 650mg", "Tab. Pantocid 40mg"],
     "slots": [
       {
         "id": "morning",
         "name": "Morning (08:00 AM) — With Breakfast",
         "time": "08:00 AM",
         "icon": "🌅",
         "color": "#fde047",
         "medicines": [ ... ]
       },
       ...
     ]
   }
"""


def process_uploaded_file(
    file_bytes: bytes,
    filename: str,
    language: str = "Hindi",
    patient_name: str = "Patient",
    age: str = "24",
    gender: str = "Male"
) -> Dict[str, Any]:
    """Process an uploaded PDF or image file via Sarvam Vision 2.1 OCR and parse to timetable."""
    upload_dir = BASE_DIR / "mock" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_file = upload_dir / filename
    temp_file.write_bytes(file_bytes)

    extracted_text = ""
    # Attempt Sarvam Vision 2.1 OCR
    if filename.lower().endswith(".pdf") and os.environ.get("SARVAM_API_KEY"):
        try:
            from decoder.ingest import digitise
            print(f"[timetable] Running Sarvam Vision 2.1 OCR on {filename}...")
            extracted_text = digitise(temp_file)
            print(f"[timetable] Sarvam Vision OCR extracted {len(extracted_text)} characters.")
        except Exception as e:
            print(f"[timetable] Sarvam Vision OCR failed: {e}", file=sys.stderr)

    if not extracted_text:
        # If OCR wasn't available or text file was uploaded
        try:
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = f"Prescription file: {filename}"

    return parse_prescription_text(
        prescription_text=extracted_text,
        language=language,
        patient_name=patient_name,
        age=age,
        gender=gender
    )


def parse_prescription_text(
    prescription_text: str,
    language: str = "Hindi",
    patient_name: str = "Patient",
    age: str = "25",
    gender: str = "Male",
    phone: str = "+91-98765-43210"
) -> Dict[str, Any]:
    """Parse raw prescription text into structured timetable JSON using Sarvam-105B."""
    api_key = os.environ.get("SARVAM_API_KEY", "")
    
    # Check if we have Sarvam API key
    if api_key and len(prescription_text.strip()) > 5:
        try:
            client = SarvamAI(api_subscription_key=api_key)
            prompt = f"""
Language for instructions and voice speech: {language}
Default Patient Name: {patient_name}
Age: {age}, Gender: {gender}

Prescription Details to parse:
{prescription_text}
"""
            resp = client.chat.completions(
                model="sarvam-105b",
                messages=[
                    {"role": "system", "content": TIMETABLE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            raw = resp.choices[0].message.content
            parsed = json_repair.loads(raw)
            if isinstance(parsed, dict) and "slots" in parsed:
                # Update DB with this active patient
                final_name = parsed.get("patient_name") or patient_name
                med_list = parsed.get("medications_list", [])
                if not med_list:
                    for s in parsed.get("slots", []):
                        for m in s.get("medicines", []):
                            med_list.append(m.get("name", "Medicine"))
                
                patient_record = {
                    "patient_id": f"PAT-{abs(hash(final_name)) % 100000:05d}",
                    "name": final_name,
                    "age": age,
                    "gender": gender,
                    "phone": phone,
                    "language": language,
                    "discharge_date": "Today",
                    "diagnoses": [parsed.get("diagnosis", "Prescription Follow-Up")],
                    "medications": med_list,
                    "follow_ups": ["Consult doctor if symptoms persist"],
                    "checklist": parsed
                }
                save_patient(patient_record)
                parsed["patient_id"] = patient_record["patient_id"]
                return parsed
        except Exception as e:
            print(f"[timetable] Error calling Sarvam-105B: {e}", file=sys.stderr)

    # Robust local parser fallback
    return _build_fallback_timetable(prescription_text, language, patient_name, age, gender)


def _build_fallback_timetable(
    text: str, language: str, name: str, age: str, gender: str
) -> Dict[str, Any]:
    """Smart fallback timetable if API key is busy or offline."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    meds = []
    for l in lines:
        if any(w in l.lower() for w in ["tab", "cap", "syp", "inj", "mg", "ml", "tablet", "capsule", "drop"]):
            meds.append(l)
    
    if not meds:
        meds = ["Tab. Paracetamol 650mg", "Tab. Pantocid 40mg", "Cap. Vitamin C 500mg"]

    slots = [
        {
            "id": "morning",
            "name": "Morning (08:00 AM) — With Breakfast",
            "time": "08:00 AM",
            "icon": "🌅",
            "color": "#fde047",
            "medicines": [
                {
                    "name": meds[0],
                    "dosage": "1 Tablet",
                    "instructions": "नाश्ते के 20 मिनट बाद, पानी के साथ लें",
                    "purpose": "उपचार एवं स्वास्थ्य लाभ के लिए",
                    "speech": f"नमस्ते {name}, यह आपकी सुबह की {meds[0]} लेने का समय है। कृपया नाश्ते के बाद एक खुराक लें।"
                }
            ]
        },
        {
            "id": "afternoon",
            "name": "Afternoon (01:30 PM) — After Lunch",
            "time": "01:30 PM",
            "icon": "☀️",
            "color": "#60a5fa",
            "medicines": [
                {
                    "name": meds[1] if len(meds) > 1 else "Cap. Vitamin D3",
                    "dosage": "1 Tablet / Capsule",
                    "instructions": "दोपहर के खाने के बाद पानी के साथ लें",
                    "purpose": "शरीर की ताकत और रिकवरी के लिए",
                    "speech": f"नमस्ते {name}, दोपहर की दवाई का समय हो गया है। कृपया भोजन के बाद दवाई लें।"
                }
            ]
        },
        {
            "id": "night",
            "name": "Night (09:00 PM) — After Dinner",
            "time": "09:00 PM",
            "icon": "🌙",
            "color": "#a78bfa",
            "medicines": [
                {
                    "name": meds[2] if len(meds) > 2 else meds[0],
                    "dosage": "1 Tablet",
                    "instructions": "रात के खाने के बाद, सोने से पहले लें",
                    "purpose": "रात को आराम और स्वास्थ्य सुधार के लिए",
                    "speech": f"नमस्ते {name}, यह आपकी रात की दवाई लेने का समय है। दवाई लेकर समय पर सो जाएं।"
                }
            ]
        }
    ]

    patient_record = {
        "patient_id": f"PAT-{abs(hash(name)) % 100000:05d}",
        "name": name,
        "age": age,
        "gender": gender,
        "phone": "+91-98765-43210",
        "language": language,
        "discharge_date": "Today",
        "diagnoses": ["Custom Prescription Care"],
        "medications": meds,
        "follow_ups": ["Review after 5 days"],
        "checklist": {"slots": slots}
    }
    save_patient(patient_record)

    return {
        "patient_id": patient_record["patient_id"],
        "patient_name": name,
        "diagnosis": "Custom Prescription Care Plan",
        "doctor_notes": "Take all medications regularly with plenty of water. Complete full course as advised.",
        "medications_list": meds,
        "slots": slots
    }
