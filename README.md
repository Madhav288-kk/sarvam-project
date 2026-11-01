# 🏥 Sarvam AI Healthcare Platform
### AI Symptom Diagnoser, Prescription Decoder & Outbound Voice Companion

An India-first, multilingual healthcare platform powered exclusively by **Sarvam AI** sovereign models:
1. **🩺 AI Symptom Diagnoser & Safe Pain Relief:** Direct voice/text symptom intake, differential diagnosis, triage severity classification, and safe minimal-side-effect pain relief recommendations.
2. **📄 Prescription & Discharge Decoder:** Ingests medical documents via **Sarvam Vision 2.1**, extracts medication schedules, and sets up daily reminder alarm timetables.
3. **📞 Post-Discharge Voice Companion:** Multi-turn outbound voice calls checking on rural patients in native Indian languages (Hindi, Telugu, Tamil, etc.), screening adherence, and escalating acute anomalies to doctors via **Mayura Translate**.

---

## 🌟 Sarvam AI Models Used

| Capability | Model | Role in Platform |
|---|---|---|
| **Document OCR / Digitisation** | **Sarvam Vision 2.1 (`/doc-ai/v1`)** | Ingests and parses hospital discharge summaries & prescriptions |
| **Clinical Reasoning & Diagnosis** | **`sarvam-105b-conversations`** | Drives differential diagnosis, checklist generation, and triage |
| **Native Voice Synthesis (TTS)** | **Bulbul v3 (`hi-IN`, `te-IN`, `ta-IN`)** | Voices medical explanations, spoken diagnosis, and reminder alarms |
| **Streaming Speech-to-Text (STT)** | **Saaras v4 (`/speech-to-text`)** | Transcribes patient microphone voice in 22 Indic languages |
| **Cross-Lingual Escalation** | **Mayura Translate (`mayura:v1`)** | Translates regional patient emergency reports to English for coordinators |

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/your-username/sarvam-healthcare-platform.git
cd sarvam-healthcare-platform
pip install -r requirements.txt
```

### 2. Configure API Key
Create a `.env` file in the project root:
```env
SARVAM_API_KEY=your_sarvam_api_key_here
```

### 3. Launch Web Dashboard & Diagnoser
```bash
python dashboard/server.py 8080
```
Open **[http://localhost:8080](http://localhost:8080)** in your browser!

---

## 📁 Repository Structure
```
├── dashboard/
│   └── server.py             # Live web dashboard & interactive voice console
├── diagnoser/
│   └── engine.py             # AI symptom diagnoser with safe pain relief
├── decoder/
│   ├── ingest.py             # Sarvam Vision document OCR
│   ├── explain.py            # Plain-language explanation generator (105B)
│   ├── checklist.py          # 30-day recovery checklist generator (105B)
│   └── speak.py              # Bulbul v3 TTS voice generator
├── companion/
│   ├── stt.py                # Saaras v4 STT client
│   ├── tts.py                # Bulbul v3 conversational TTS
│   ├── checkin.py            # Multi-turn conversational check-in engine
│   ├── escalate.py           # Mayura Translate & coordinator alerts
│   └── voice_loop.py         # Bidirectional voice loop manager
├── db/
│   └── patients.py           # SQLite repository for clinical records & logs
├── demo.py                   # Terminal interactive roleplay demo
├── switch_language.py        # Switch platform language (Hindi/Telugu/Tamil...)
├── requirements.txt
└── .gitignore
```
