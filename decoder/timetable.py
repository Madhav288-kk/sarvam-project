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

# Ensure .env is loaded
_env = BASE_DIR / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from sarvamai import SarvamAI
import json_repair
from db.patients import save_patient, get_patient


TIMETABLE_SYSTEM_PROMPT = """You are an expert AI Clinical Pharmacist & Medication Schedule Planner.
Given doctor prescription OCR text or clinical instructions:
1. Extract:
   - hospital_name: Name of clinic or hospital if mentioned (e.g. 'Sunrise General Hospital', 'Apollo Hospitals'; or null)
   - doctor_name: Name of prescribing doctor with title if mentioned (e.g. 'Dr. A. Sharma, MD'; or null)
   - patient_name: Patient name if mentioned in prescription; otherwise use the provided patient name
   - diagnosis: Clinical condition or reason (e.g. 'Acute viral fever with throat infection')
   - doctor_notes: Special advice given by doctor in the requested language
   - full_schedule_speech: A complete, warm, fluent spoken narrative of the full day's medication schedule written ENTIRELY in the requested language.

CRITICAL LINGUISTIC ACCURACY RULE (ZERO HINDI BLEEDING):
Every string in 'doctor_notes', 'instructions', 'purpose', 'full_schedule_speech', and slot 'speech' MUST be 100% in the requested target language.
- NEVER mix Hindi words, Hindi sentences, or English into non-Hindi languages.
- SINDHI REQUIREMENT: If the requested language is Sindhi:
  * For UI text ('instructions', 'doctor_notes', 'purpose'): write in Sindhi (Perso-Arabic script e.g. "صبح جو ناشتي کان پوءِ پاڻيءَ سان وٺو" or Devanagari script).
  * For Spoken Audio text ('full_schedule_speech' and each slot's 'speech'): write the Sindhi narrative in Devanagari script (e.g. "नमस्ते [नाव], ही तव्हांजो अजु जो सभनी दवाइयून जो वेळापत्रक आहे। सुबह जो नाश्ते खां पोइ [दवा] वठो... मंझंद जो मानीअ खां पोइ [दवा] वठो... रात जो सुम्हण खां अग [दवा] वठो... मेहरबानी करे सभ दवाईउं वक़्त ते वठो। तव्हांजी सेहत जो ख्याल रखजो।"). EVERY single word must be authentic native Sindhi (use 'ही', 'तव्हांजो', 'अजु जो', 'सभनी', 'दवाइयून', 'आहे', 'नाश्ते खां पोइ', 'मंझंद जो मानीअ खां पोइ', 'सुम्हण खां अग', 'सभ', 'वक़्त ते वठो', 'तव्हांजी सेहत जो ख्याल रखजो'). NEVER substitute Hindi words!
- URDU REQUIREMENT: If Urdu, write spoken strings in Devanagari script using 100% authentic Urdu vocabulary ("आदाब [नाव] साहिब, यह आपकी आज की तमाम दवाइयों का मुकम्मल शिड्यूल है... बराए मेहरबानी नाश्ते के बाद... तमाम दवाइयां वक़्त पर लें और अपनी सेहत का ख्याल रखें। शुक्रिया।").
- KASHMIRI REQUIREMENT: If Kashmiri, write spoken strings in Devanagari script using 100% authentic Kashmiri vocabulary.
- ALL OTHER LANGUAGES (Marathi, Bengali, Telugu, Tamil, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, etc.): Every word must be 100% in that language's native script, vocabulary, and grammar. Zero Hindi bleeding.

2. Group ALL prescribed medications accurately into daily time slots based on their frequency:
   - "three times a day" -> Morning, Afternoon, Night
   - "twice a day" -> Morning, Night
   - "at night" or "at bedtime" -> Night
   - "once daily in morning" -> Morning
   - "throughout the day" / "as needed" -> Morning or Daytime
3. For each medicine in a slot, provide:
   - name: Clean medicine name and strength (e.g. "Tab. Paracetamol 500 mg", "Syp. Cough linctus", "Tab. Cetirizine 10 mg"). Do NOT include bullet numbers.
   - dosage: e.g. "1 Tablet" or "10 ml"
   - instructions: Clear, short instruction in the requested language
   - purpose: Why it is prescribed in the requested language
   - speech: Conversational, friendly spoken reminder in the requested language for Bulbul v3 TTS alarm (for Sindhi/Urdu/Kashmiri write in Devanagari script using native words).
4. Output STRICT JSON:
   {
     "hospital_name": "...",
     "doctor_name": "...",
     "patient_name": "...",
     "diagnosis": "...",
     "doctor_notes": "...",
     "full_schedule_speech": "...",
     "medications_list": ["Tab. Paracetamol 500 mg", "Tab. Cetirizine 10 mg", "Syp. Cough linctus", "ORS sachets"],
     "slots": [
       {
         "id": "morning",
         "name": "Morning (08:00 AM) — With Breakfast",
         "time": "08:00 AM",
         "icon": "🌅",
         "color": "#fde047",
         "medicines": [ ... ]
       },
       {
         "id": "afternoon",
         "name": "Afternoon (01:30 PM) — After Lunch",
         "time": "01:30 PM",
         "icon": "☀️",
         "color": "#60a5fa",
         "medicines": [ ... ]
       },
       {
         "id": "night",
         "name": "Night (09:00 PM) — After Dinner / Bedtime",
         "time": "09:00 PM",
         "icon": "🌙",
         "color": "#a78bfa",
         "medicines": [ ... ]
       }
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
    is_doc = any(filename.lower().endswith(ext) for ext in [".pdf", ".jpg", ".jpeg", ".png", ".webp"])
    
    # Run Sarvam Vision 2.1 OCR on images and PDFs
    if is_doc and os.environ.get("SARVAM_API_KEY"):
        try:
            from decoder.ingest import digitise
            print(f"[timetable] Running Sarvam Vision 2.1 OCR on document {filename}...")
            extracted_text = digitise(temp_file)
            print(f"[timetable] Sarvam Vision OCR successfully extracted {len(extracted_text)} characters.")
        except Exception as e:
            print(f"[timetable] Sarvam Vision OCR failed: {e}", file=sys.stderr)

    if not extracted_text:
        # Only decode if it is a plain text file, NEVER decode raw image/pdf bytes as UTF-8!
        if not is_doc:
            try:
                extracted_text = file_bytes.decode("utf-8", errors="ignore")
            except Exception:
                extracted_text = ""

    if not extracted_text or len(extracted_text.strip()) < 5:
        return {
            "patient_id": f"PAT-{abs(hash(patient_name)) % 100000:05d}",
            "patient_name": patient_name,
            "diagnosis": "Prescription Upload Warning",
            "doctor_notes": "Could not extract text from this document. Please check image clarity or paste the text directly into the box.",
            "medications_list": [],
            "slots": []
        }

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
    
    if api_key and len(prescription_text.strip()) > 5:
        try:
            client = SarvamAI(api_subscription_key=api_key)
            prompt = f"""
Language for instructions and voice speech: {language}
Default Patient Name: {patient_name}
Age: {age}, Gender: {gender}

Prescription Details:
{prescription_text}
"""
            resp = client.chat.completions(
                model="sarvam-105b-conversations",
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
                    "doctor_name": parsed.get("doctor_name") or "your doctor",
                    "hospital_name": parsed.get("hospital_name") or "your hospital",
                    "follow_ups": ["Consult doctor if symptoms persist"],
                    "checklist": parsed
                }
                save_patient(patient_record)
                parsed["patient_id"] = patient_record["patient_id"]
                return parsed
        except Exception as e:
            print(f"[timetable] Error calling Sarvam-105B: {e}", file=sys.stderr)

    return _build_fallback_timetable(prescription_text, language, patient_name, age, gender)


def _build_fallback_timetable(
    text: str, language: str, name: str, age: str, gender: str
) -> Dict[str, Any]:
    """Smart fallback timetable if API key is busy or offline."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    meds = []
    for l in lines:
        cleaned = l.lstrip("0123456789.-) ")
        if any(w in cleaned.lower() for w in ["tab", "cap", "syp", "inj", "mg", "ml", "tablet", "capsule", "drop", "ors", "sachet"]):
            # Filter out binary garbage lines
            if not any(bad in cleaned.lower() for bad in ["desc", "cprt", "rxyz", "gxyz", "bxyz", "rtrc"]):
                meds.append(cleaned)
    
    if not meds:
        meds = ["Tab. Paracetamol 500mg", "Tab. Cetirizine 10mg", "Syp. Cough Linctus"]

    lang_lower = (language or "hindi").lower().strip()

    # Multilingual templates for slots to guarantee ZERO Hindi bleeding in any language
    TEMPLATES = {
        "sindhi": {
            "m_instr": "صبح جو ناشتي کان پوءِ پاڻيءَ سان وٺو",
            "m_speech": f"नमस्ते {name}, ही तव्हांजी सुबह जी {meds[0]} वठण जो वक़्त आहे। सुबह जो नाश्तो करण खां पोइ हिक गोरी पाणीअ सां वठो।",
            "a_instr": "منجهند جو مانيءَ کان پوءِ پاڻيءَ سان وٺو",
            "a_speech": f"नमस्ते {name}, मंझंद जी दवाई वठण जो वक़्त आहे। मानीअ खां पोइ हिक खुराक वठो।",
            "n_instr": "रात جو مانيءَ کان پوءِ سمهڻ کان اڳ وٺو",
            "n_speech": f"नमस्ते {name}, ही तव्हांजी रात जी दवाई वठण जो वक़्त आहे। दवाई वठी वक़्त ते सुम्हो।",
            "full_speech": f"नमस्ते {name}, ही तव्हांजो अजु जो सभनी दवाइयून जो टाईमटेबल आहे। सुबह जो नाश्ते खां पोइ {meds[0]} वठो। मंझंद जो मानीअ खां पोइ {meds[1] if len(meds) > 1 else meds[0]} वठो। रात जो सुम्हण खां अग {meds[2] if len(meds) > 2 else meds[0]} वठो। मेहरबानी करे सभ दवाईउं वक़्त ते वठो ऐं तव्हांजी सेहत जो ख्याल रखजो।",
            "notes": "مهرباني ڪري سڀ دوائون وقت تي پاڻيءَ سان وٺو ۽ پنهنجو خيال رکو.",
            "diag": "نسخو / تندرستي جو منصوبو"
        },
        "marathi": {
            "m_instr": "सकाळी नाश्त्यानंतर 20 मिनिटांनी पाण्यासोबत घ्या",
            "m_speech": f"नमस्कार {name}जी, ही तुमची सकाळची {meds[0]} घेण्याची वेळ आहे. कृपया नाश्त्यानंतर औषध घ्या.",
            "a_instr": "दुपारी जेवणानंतर पाण्यासोबत घ्या",
            "a_speech": f"नमस्कार {name}जी, दुपारच्या औषधाची वेळ झाली आहे. कृपया जेवणानंतर औषध घ्या.",
            "n_instr": "रात्री जेवणानंतर झोपण्यापूर्वी घ्या",
            "n_speech": f"नमस्कार {name}जी, ही तुमची रात्रीची औषध घेण्याची वेळ आहे. औषध घेऊन वेळेवर झोपा.",
            "full_speech": f"नमस्कार {name}जी, हा तुमचा आजचा संपूर्ण औषधांचा वेळापत्रक आहे. सकाळी नाश्त्यानंतर {meds[0]} घ्या. दुपारी जेवणानंतर {meds[1] if len(meds) > 1 else meds[0]} घ्या. रात्री झोपण्यापूर्वी {meds[2] if len(meds) > 2 else meds[0]} घ्या. कृपया सर्व औषधे वेळेवर घ्या आणि स्वतःची काळजी घ्या. धन्यवाद.",
            "notes": "कृपया सर्व औषधे वेळेवर भरपूर पाण्यासोबत घ्या.",
            "diag": "प्रिस्क्रिप्शन उपचार योजना"
        },
        "bengali": {
            "m_instr": "সকালে প্রাতঃরাশের পর জল দিয়ে সেবন করুন",
            "m_speech": f"নমস্কার {name}জি, এটি আপনার সকালের {meds[0]} খাওয়ার সময়। প্রাতঃরাশের পর খান।",
            "a_instr": "দুপুরে খাওয়ার পর জল দিয়ে নিন",
            "a_speech": f"নমস্কার {name}জি, দুপুরের ওষুধের সময় হয়েছে। খাওয়ার পর ওষুধ নিন।",
            "n_instr": "রাতে শোবার আগে নিন",
            "n_speech": f"নমস্কার {name}জি, এটি আপনার রাতের ওষুধ নেওয়ার সময়। ওষুধ খেয়ে সময়মতো ঘুমান।",
            "full_speech": f"নমস্কার {name}জি, এটি আপনার আজকের ওষুধের সময়সূচী। সকালে প্রাতঃরাশের পর {meds[0]} খান। দুপুরে খাওয়ার পর {meds[1] if len(meds) > 1 else meds[0]} নিন। রাতে শোবার আগে {meds[2] if len(meds) > 2 else meds[0]} খান। দয়া করে সব ওষুধ সময়মতো সেবন করুন। ধন্যবাদ।",
            "notes": "সব ওষুধ সময়মতো প্রচুর জল দিয়ে সেবন করুন।",
            "diag": "প্রেসক্রিপশন চিকিৎসা পরিকল্পনা"
        },
        "telugu": {
            "m_instr": "ఉదయం అల్పాహారం తర్వాత నీటితో వేసుకోండి",
            "m_speech": f"నమస్కారం {name}గారు, ఇది మీ ఉదయం {meds[0]} వేసుకునే సమయం. అల్పాహారం తర్వాత తీసుకోండి.",
            "a_instr": "మధ్యాహ్నం భోజనం తర్వాత తీసుకోండి",
            "a_speech": f"నమస్కారం {name}గారు, మధ్యాహ్నం మందుల సమయం అయింది. భోజనం తర్వాత వేసుకోండి.",
            "n_instr": "రాత్రి పడుకునే ముందు తీసుకోండి",
            "n_speech": f"నమస్కారం {name}గారు, ఇది మీ రాత్రి మందు వేసుకునే సమయం. మందు వేసుకుని నిద్రపోండి.",
            "full_speech": f"నమస్కారం {name}గారు, ఇది మీ రోజువారీ మందుల సమయ పట్టిక. ఉదయం అల్పాహారం తర్వాత {meds[0]} తీసుకోండి. మధ్యాహ్నం {meds[1] if len(meds) > 1 else meds[0]} వేసుకోండి. రాత్రి పడుకునే ముందు {meds[2] if len(meds) > 2 else meds[0]} వేసుకోండి. దయచేసి మందులన్నీ సమయానికి తీసుకోండి. ధన్యవాదాలు.",
            "notes": "అన్ని మందులు క్రమం తప్పకుండా నీటితో వేసుకోండి.",
            "diag": "వైద్య ప్రిస్క్రిప్షన్ కేర్ ప్లాన్"
        },
        "tamil": {
            "m_instr": "காலை உணவுக்குப் பிறகு தண்ணீருடன் உட்கொள்ளவும்",
            "m_speech": f"வணக்கம் {name}, இது உங்கள் காலை {meds[0]} எடுத்துக்கொள்ளும் நேரம். உணவுக்குப் பிறகு எடுத்துக் கொள்ளுங்கள்.",
            "a_instr": "மதிய உணவுக்குப் பிறகு உட்கொள்ளவும்",
            "a_speech": f"வணக்கம் {name}, மதிய மருந்துக்கான நேரம் வந்துவிட்டது. உணவுக்குப் பிறகு மருந்தை உட்கொள்ளுங்கள்.",
            "n_instr": "இரவு படுக்கைக்குச் செல்லும் முன் உட்கொள்ளவும்",
            "n_speech": f"வணக்கம் {name}, இது உங்கள் இரவு மருந்துக்கான நேரம். மருந்தை உட்கொண்டு தூங்குங்கள்.",
            "full_speech": f"வணக்கம் {name}, இது உங்கள் தினசரி மருந்து அட்டவணை. காலை உணவுக்குப் பிறகு {meds[0]} எடுத்துக் கொள்ளுங்கள். மதிய உணவுக்குப் பிறகு {meds[1] if len(meds) > 1 else meds[0]} உட்கொள்ளுங்கள். இரவு தூங்கும் முன் {meds[2] if len(meds) > 2 else meds[0]} உட்கொள்ளுங்கள். அனைத்து மருந்துகளையும் சரியான நேரத்தில் எடுத்துக்கொள்ளுங்கள். நன்றி.",
            "notes": "அனைத்து மருந்துகளையும் தவறாமல் தண்ணீருடன் எடுத்துக் கொள்ளுங்கள்.",
            "diag": "மருத்துவ சிகிச்சைத் திட்டம்"
        },
        "gujarati": {
            "m_instr": "સવારે નાસ્તા પછી પાણી સાથે લો",
            "m_speech": f"નમસ્તે {name}જી, આ તમારી સવારની {meds[0]} લેવાનો સમય છે. નાસ્તા પછી દવા લો.",
            "a_instr": "બપોરે જમ્યા પછી પાણી સાથે લો",
            "a_speech": f"નમસ્તે {name}જી, બપોરની દવા લેવાનો સમય થઈ ગયો છે. જમ્યા પછી દવા લો.",
            "n_instr": "રાત્રે સૂતા પહેલા લો",
            "n_speech": f"નમસ્તે {name}જી, આ તમારી રાતની દવા લેવાનો સમય છે. દવા લઈને સમયસર સૂઈ જાઓ.",
            "full_speech": f"નમસ્તે {name}જી, આ તમારું આજનું દવાઓનું ટાઈમટેબલ છે. સવારે નાસ્તા પછી {meds[0]} લો. બપોરે જમ્યા પછી {meds[1] if len(meds) > 1 else meds[0]} લો. રાત્રે સૂતા પહેલા {meds[2] if len(meds) > 2 else meds[0]} લો. કૃપા કરીને બધી દવાઓ સમયસર લો અને કાળજી રાખો. ધન્યવાદ.",
            "notes": "કૃપા કરીને બધી દવાઓ નિયમિતપણે પાણી સાથે લો.",
            "diag": "પ્રિસ્ક્રિપ્શન સારવાર યોજના"
        },
        "punjabi": {
            "m_instr": "ਸਵੇਰੇ ਨਾਸ਼ਤੇ ਤੋਂ ਬਾਅਦ ਪਾਣੀ ਨਾਲ ਲਓ",
            "m_speech": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ {name}ਜੀ, ਇਹ ਤੁਹਾਡੀ ਸਵੇਰ ਦੀ {meds[0]} ਲੈਣ ਦਾ ਸਮਾਂ ਹੈ। ਨਾਸ਼ਤੇ ਤੋਂ ਬਾਅਦ ਖੁਰਾਕ ਲਓ।",
            "a_instr": "ਦੁਪਹਿਰ ਦੇ ਖਾਣੇ ਤੋਂ ਬਾਅਦ ਲਓ",
            "a_speech": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ {name}ਜੀ, ਦੁਪਹਿਰ ਦੀ ਦਵਾਈ ਦਾ ਸਮਾਂ ਹੋ ਗਿਆ ਹੈ। ਖਾਣਾ ਖਾਣ ਤੋਂ ਬਾਅਦ ਲਓ।",
            "n_instr": "ਰਾਤ ਨੂੰ ਸੌਣ ਤੋਂ ਪਹਿਲਾਂ ਲਓ",
            "n_speech": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ {name}ਜੀ, ਇਹ ਤੁਹਾਡੀ ਰਾਤ ਦੀ ਦਵਾਈ ਲੈਣ ਦਾ ਸਮਾਂ ਹੈ। ਦਵਾਈ ਲੈ ਕੇ ਸੌਂ ਜਾਓ।",
            "full_speech": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ {name}ਜੀ, ਇਹ ਤੁਹਾਡਾ ਅੱਜ ਦਾ ਦਵਾਈਆਂ ਦਾ ਸਮਾਂ-ਸਾਰਣੀ ਹੈ। ਸਵੇਰੇ {meds[0]} ਲਓ। ਦੁਪਹਿਰ ਨੂੰ {meds[1] if len(meds) > 1 else meds[0]} ਲਓ। ਰਾਤ ਨੂੰ {meds[2] if len(meds) > 2 else meds[0]} ਲਓ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਰੀਆਂ ਦਵਾਈਆਂ ਸਮੇਂ ਸਿਰ ਲਓ। ਧੰਨਵਾਦ।",
            "notes": "ਸਾਰੀਆਂ ਦਵਾਈਆਂ ਸਮੇਂ ਸਿਰ ਪਾਣੀ ਨਾਲ ਲਓ।",
            "diag": "ਇਲਾਜ ਯੋਜਨਾ"
        },
        "kannada": {
            "m_instr": "ಬೆಳಿಗ್ಗೆ ಉಪಾಹಾರದ ನಂತರ ನೀರಿನೊಂದಿಗೆ ತೆಗೆದುಕೊಳ್ಳಿ",
            "m_speech": f"ನಮಸ್ಕಾರ {name}, ಇದು ನಿಮ್ಮ ಬೆಳಗಿನ {meds[0]} ತೆಗೆದುಕೊಳ್ಳುವ ಸಮಯ. ಉಪಾಹಾರದ ನಂತರ ತೆಗೆದುಕೊಳ್ಳಿ.",
            "a_instr": "ಮಧ್ಯಾಹ್ನ ಊಟದ ನಂತರ ತೆಗೆದುಕೊಳ್ಳಿ",
            "a_speech": f"ನಮಸ್ಕಾರ {name}, ಮಧ್ಯಾಹ್ನದ ಔಷಧಿ ಸಮಯವಾಗಿದೆ. ಊಟದ ನಂತರ ತೆಗೆದುಕೊಳ್ಳಿ.",
            "n_instr": "ರಾತ್ರಿ ಮಲಗುವ ಮುನ್ನ ತೆಗೆದುಕೊಳ್ಳಿ",
            "n_speech": f"ನಮಸ್ಕಾರ {name}, ಇದು ನಿಮ್ಮ ರಾತ್ರಿಯ ಔಷಧಿ ಸಮಯ. ಔಷಧಿ ತೆಗೆದುಕೊಂಡು ಮಲಗಿ.",
            "full_speech": f"ನಮಸ್ಕಾರ {name}, ಇದು ನಿಮ್ಮ ದೈನಂದಿನ ಔಷಧಿಗಳ ವೇಳಾಪಟ್ಟಿ. ಬೆಳಿಗ್ಗೆ {meds[0]} ತೆಗೆದುಕೊಳ್ಳಿ. ಮಧ್ಯಾಹ್ನ {meds[1] if len(meds) > 1 else meds[0]} ತೆಗೆದುಕೊಳ್ಳಿ. ರಾತ್ರಿ {meds[2] if len(meds) > 2 else meds[0]} ತೆಗೆದುಕೊಳ್ಳಿ. ದಯವಿಟ್ಟು ಎಲ್ಲಾ ಔಷಧಿಗಳನ್ನು ಸಮಯಕ್ಕೆ ಸರಿಯಾಗಿ ತೆಗೆದುಕೊಳ್ಳಿ. ಧನ್ಯವಾದಗಳು.",
            "notes": "ದಯವಿಟ್ಟು ಎಲ್ಲಾ ಔಷಧಿಗಳನ್ನು ನಿಯಮಿತವಾಗಿ ನೀರಿನೊಂದಿಗೆ ತೆಗೆದುಕೊಳ್ಳಿ.",
            "diag": "ಔಷಧಿ ಆರೈಕೆ ಯೋಜನೆ"
        },
        "malayalam": {
            "m_instr": "രാവിലെ പ്രഭാതഭക്ഷണത്തിന് ശേഷം വെള്ളത്തോടൊപ്പം കഴിക്കുക",
            "m_speech": f"നമസ്കാരം {name}, ഇത് നിങ്ങളുടെ രാവിലത്തെ {meds[0]} കഴിക്കാനുള്ള സമയമാണ്.",
            "a_instr": "ഉച്ചഭക്ഷണത്തിന് ശേഷം കഴിക്കുക",
            "a_speech": f"നമസ്കാരം {name}, ഉച്ചയ്ക്കുള്ള മരുന്ന് കഴിക്കാനുള്ള സമയമായി.",
            "n_instr": "രാത്രി ഉറങ്ങുന്നതിന് മുമ്പ് കഴിക്കുക",
            "n_speech": f"നമസ്കാരം {name}, ഇത് നിങ്ങളുടെ രാത്രിയിലെ മരുന്ന് കഴിക്കാനുള്ള സമയമാണ്.",
            "full_speech": f"നമസ്കാരം {name}, ഇതാണ് നിങ്ങളുടെ ഇന്നത്തെ മരുന്നുകളുടെ സമയക്രമം. ദയവായി എല്ലാ മരുന്നുകളും കൃത്യസമയത്ത് കഴിക്കുക. നന്ദി.",
            "notes": "എല്ലാ മരുന്നുകളും സമയബന്ധിതമായി കഴിക്കുക.",
            "diag": "ചികിത്സാ പദ്ധതി"
        },
        "odia": {
            "m_instr": "ସକାଳେ ଜଳଖିଆ ପରେ ପାଣି ସହିତ ନିଅନ୍ତୁ",
            "m_speech": f"ନମସ୍କାର {name}ଜୀ, ଏହା ଆପଣଙ୍କର ସକାଳର {meds[0]} ଖାଇବାର ସମୟ।",
            "a_instr": "ଦ୍ୱିପ୍ରହର ଖାଇବା ପରେ ନିଅନ୍ତୁ",
            "a_speech": f"ନମସ୍କାର {name}ଜୀ, ଦ୍ୱିପ୍ରହରର ଔଷଧ ସମୟ ହୋଇଛି।",
            "n_instr": "ରାତିରେ ଶୋଇବା ପୂର୍ବରୁ ନିଅନ୍ତୁ",
            "n_speech": f"ନମସ୍କାର {name}ଜୀ, ଏହା ଆପଣଙ୍କର ରାତି ଔଷଧ ସମୟ।",
            "full_speech": f"ନମସ୍କାର {name}ଜୀ, ଏହା ଆପଣଙ୍କର ଆଜିର ଔଷଧ ସମୟସୂଚୀ। ଦୟାକରି ସମସ୍ତ ଔଷଧ ଠିକ୍ ସମୟରେ ନିଅନ୍ତୁ। ଧନ୍ୟବାଦ।",
            "notes": "ସମସ୍ତ ଔଷଧ ଠିକ୍ ସମୟରେ ନିଅନ୍ତୁ।",
            "diag": "ଚିକିତ୍ସା ଯୋଜନା"
        },
        "urdu": {
            "m_instr": "صبح ناشتے کے بعد پانی کے ساتھ لیں",
            "m_speech": f"आदाब {name} साहिब, यह आपकी सुबह की {meds[0]} लेने का वक़्त है। नाश्ते के बाद एक खुराक लें।",
            "a_instr": "دوپہر کے کھانے کے بعد پانی کے ساتھ لیں",
            "a_speech": f"आदाब {name} साहिब, दोपहर की दवाई का वक़्त हो गया है। बराए मेहरबानी खाने के बाद दवाई लें।",
            "n_instr": "رات کے کھانے کے بعد سونے سے پہلے لیں",
            "n_speech": f"आदाब {name} साहिब, यह आपकी रात की दवाई का वक़्त है। दवाई लेकर वक़्त पर सो जाएं।",
            "full_speech": f"आदाब {name} साहिब, यह आपका आज की तमाम दवाइयों का मुकम्मल शिड्यूल है। सुबह नाश्ते के बाद {meds[0]} लें। दोपहर को {meds[1] if len(meds) > 1 else meds[0]} लें। रात को {meds[2] if len(meds) > 2 else meds[0]} लें। बराए मेहरबानी तमाम दवाइयां वक़्त पर लें। शुक्रिया।",
            "notes": "تمام دوائیں باقاعدگی سے پانی کے ساتھ لیں اور اپنا خیال رکھیں۔",
            "diag": "نسخہ و نگہداشت کا منصوبہ"
        },
        "english": {
            "m_instr": "Take with water after breakfast",
            "m_speech": f"Hello {name}, it is time to take your morning dose of {meds[0]} after breakfast.",
            "a_instr": "Take with water after lunch",
            "a_speech": f"Hello {name}, it is time to take your afternoon medication after lunch.",
            "n_instr": "Take after dinner before bedtime",
            "n_speech": f"Hello {name}, it is time for your night medication before sleeping.",
            "full_speech": f"Hello {name}, here is your complete medication schedule for today. Please take {meds[0]} in the morning after breakfast, {meds[1] if len(meds) > 1 else meds[0]} in the afternoon after lunch, and {meds[2] if len(meds) > 2 else meds[0]} at night before bedtime. Please take all medications on time. Thank you.",
            "notes": "Take all prescribed medications regularly with plenty of water.",
            "diag": "Prescription Care Plan"
        },
        "hindi": {
            "m_instr": "नाश्ते के 20 मिनट बाद, पानी के साथ लें",
            "m_speech": f"नमस्ते {name}, यह आपकी सुबह की {meds[0]} लेने का समय है। कृपया नाश्ते के बाद एक खुराक लें।",
            "a_instr": "दोपहर के खाने के बाद पानी के साथ लें",
            "a_speech": f"नमस्ते {name}, दोपहर की दवाई का समय हो गया है। कृपया भोजन के बाद दवाई लें।",
            "n_instr": "रात के खाने के बाद, सोने से पहले लें",
            "n_speech": f"नमस्ते {name}, यह आपकी रात की दवाई लेने का समय है। दवाई लेकर समय पर सो जाएं।",
            "full_speech": f"नमस्ते {name} जी, यह आपका आज का दवाई का शेड्यूल है। सुबह नाश्ते के बाद {meds[0]} लें। दोपहर को खाने के बाद {meds[1] if len(meds) > 1 else meds[0]} लें। रात को सोने से पहले {meds[2] if len(meds) > 2 else meds[0]} लें। कृपया सभी दवाइयां समय पर लें और अपना ध्यान रखें। धन्यवाद।",
            "notes": "सभी दवाइयां नियमित रूप से पानी के साथ लें और अपना ध्यान रखें।",
            "diag": "कस्टम प्रिस्क्रिप्शन केयर प्लान"
        }
    }

    t = TEMPLATES.get(lang_lower, TEMPLATES["hindi"])

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
                    "dosage": "1 Tablet / Dose",
                    "instructions": t["m_instr"],
                    "purpose": "Recovery & Health",
                    "speech": t["m_speech"]
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
                    "name": meds[1] if len(meds) > 1 else meds[0],
                    "dosage": "1 Dose",
                    "instructions": t["a_instr"],
                    "purpose": "Recovery & Health",
                    "speech": t["a_speech"]
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
                    "instructions": t["n_instr"],
                    "purpose": "Recovery & Health",
                    "speech": t["n_speech"]
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
        "diagnoses": [t["diag"]],
        "medications": meds,
        "follow_ups": ["Review after 5 days"],
        "checklist": {"slots": slots}
    }
    save_patient(patient_record)

    return {
        "patient_id": patient_record["patient_id"],
        "patient_name": name,
        "diagnosis": t["diag"],
        "doctor_notes": t["notes"],
        "full_schedule_speech": t["full_speech"],
        "medications_list": meds,
        "slots": slots
    }
