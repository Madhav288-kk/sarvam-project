"""
dashboard/server.py
───────────────────
Full Interactive Healthcare Platform with:
  1. 🩺 AI Symptom Diagnoser & Triage (with safe low-risk pain relief medicines)
  2. 📄 Interactive Prescription Uploader & Smart Medication Reminder Timetable (Sarvam Vision 2.1 + Sarvam-105B)
  3. 📋 Post-Discharge Patient Companion & Outbound Telephony Bot (Saaras v4 + Bulbul v3 + Mayura Translate)

Usage:
    python dashboard/server.py [port]  (default: 8080)
"""

import os
import sys
import json
import base64
import sqlite3
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8080))
BASE_DIR = Path(__file__).parent.parent
MOCK_DIR = BASE_DIR / "mock"
DB_PATH = MOCK_DIR / "patients.db"

# Ensure project root is in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load .env
_env = BASE_DIR / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from db.patients import get_patient, log_checkin, init_db, save_patient
from companion.checkin import generate_agent_reply, evaluate_call_outcome
from companion.tts import speak_turn
from companion.stt import transcribe_audio_bytes
from companion.escalate import create_escalation_alert
from diagnoser.engine import diagnose_symptoms, diagnose_followup
from decoder.timetable import parse_prescription_text, process_uploaded_file
from sarvamai import SarvamAI
import json_repair


def get_db_data():
    if not DB_PATH.exists():
        init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    p_row = conn.execute("SELECT * FROM patients ORDER BY created_at DESC LIMIT 1").fetchone()
    patient = dict(p_row) if p_row else None
    if patient:
        for k in ["diagnoses", "medications", "follow_ups", "checklist"]:
            if patient.get(k):
                try:
                    patient[k] = json.loads(patient[k])
                except Exception:
                    pass

    logs = []
    for row in conn.execute("SELECT * FROM checkin_logs ORDER BY id DESC").fetchall():
        d = dict(row)
        for k in ["transcript", "adherence", "symptoms", "flags", "escalation_details"]:
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
        logs.append(d)

    conn.close()
    return {"patient": patient, "logs": logs}


HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sarvam AI — Healthcare Diagnostic & Medication Platform</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --purple: #8b5cf6;
      --purple-hover: #7c3aed;
      --green: #10b981;
      --red: #ef4444;
      --amber: #f59e0b;
      --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
      padding: 24px;
      min-height: 100vh;
    }

    .container { max-width: 1200px; margin: 0 auto; }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .header-left h1 {
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(90deg, #60a5fa, #a78bfa, #34d399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .header-left p { color: var(--text-muted); font-size: 13.5px; margin-top: 4px; }

    /* Patient Intake Card */
    .patient-intake-card {
      background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
      border: 1px solid #4338ca;
      border-radius: 14px;
      padding: 16px 20px;
      margin-bottom: 22px;
      box-shadow: 0 4px 16px rgba(67, 56, 202, 0.15);
    }
    .intake-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .intake-grid {
      display: grid;
      grid-template-columns: 2fr 1fr 1.2fr 1.5fr;
      gap: 12px;
    }
    .form-group label {
      display: block;
      font-size: 11.5px;
      font-weight: 600;
      color: #cbd5e1;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 5px;
    }
    .form-input {
      width: 100%;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid #334155;
      border-radius: 8px;
      color: #fff;
      font-family: var(--font);
      font-size: 13.5px;
      padding: 9px 12px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .form-input:focus {
      border-color: #818cf8;
      box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.2);
    }

    /* 3-Way Tabs */
    .tabs-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }
    .tab-btn {
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 10px 18px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tab-btn:hover { background: rgba(255,255,255,0.08); color: #fff; }
    .tab-btn.active {
      background: linear-gradient(135deg, #1d4ed8, #2563eb);
      color: #fff;
      border-color: #3b82f6;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    }

    /* Cards */
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .card-header h2 { font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 8px; }

    .badge {
      font-size: 11px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 20px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
    }
    .badge.active { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }

    /* Inputs & Buttons */
    .symptom-textarea {
      width: 100%;
      height: 110px;
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: #fff;
      font-family: var(--font);
      font-size: 14px;
      padding: 14px;
      resize: vertical;
      margin-bottom: 14px;
      outline: none;
      transition: border 0.2s;
    }
    .symptom-textarea:focus { border-color: var(--primary); }

    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 10px;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .btn-green { background: var(--green); }
    .btn-green:hover { background: #059669; }
    .btn-purple { background: var(--purple); }
    .btn-purple:hover { background: var(--purple-hover); }
    .btn-red { background: var(--red); }
    .btn-red:hover { background: #dc2626; }

    .mic-btn {
      background: #1f2937;
      color: #cbd5e1;
      border: 1px solid #374151;
      padding: 10px 18px;
      border-radius: 10px;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .mic-btn:hover { background: #374151; color: white; }
    .mic-btn.recording {
      background: #dc2626;
      border-color: #ef4444;
      color: white;
      animation: pulse 1.5s infinite;
    }

    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    .chip {
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 5px 12px;
      border-radius: 16px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .chip:hover { background: rgba(59, 130, 246, 0.2); border-color: var(--primary); color: #fff; }

    /* Diagnostic Cards */
    .triage-card {
      border-radius: 14px;
      padding: 18px 22px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .triage-card.routine { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; }
    .triage-card.urgent { background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); color: #fbbf24; }
    .triage-card.emergency { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; }

    .relief-box {
      background: linear-gradient(180deg, rgba(16, 185, 129, 0.08) 0%, rgba(17, 24, 39, 0.9) 100%);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 14px;
      padding: 20px;
      margin-top: 18px;
    }
    .medicine-card {
      background: rgba(0,0,0,0.3);
      border: 1px solid #1f2937;
      border-radius: 10px;
      padding: 14px 16px;
      margin-top: 10px;
    }
    .med-header {
      display: flex;
      justify-content: space-between;
      font-weight: 700;
      color: #34d399;
      font-size: 14px;
    }
    .med-dose { font-size: 13px; color: #e2e8f0; margin-top: 4px; }
    .med-note { font-size: 12px; color: #94a3b8; margin-top: 4px; }

    /* Timetable Reminder Card */
    .time-slot {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 14px;
    }
    .slot-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      font-weight: 700;
      font-size: 14px;
    }
    .med-item-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: rgba(0,0,0,0.25);
      border-radius: 8px;
      margin-bottom: 8px;
      font-size: 13px;
      transition: background 0.2s;
    }

    /* Upload Box */
    .drop-zone {
      border: 2px dashed #7c3aed;
      border-radius: 14px;
      padding: 30px 20px;
      text-align: center;
      background: rgba(124, 58, 237, 0.05);
      cursor: pointer;
      transition: all 0.2s;
    }
    .drop-zone:hover { background: rgba(124, 58, 237, 0.12); border-color: #a78bfa; }

    /* Companion Layout */
    .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
    .meta-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; border-bottom: 1px dashed rgba(255,255,255,0.04); }
    .meta-label { color: var(--text-muted); }
    .meta-value { font-weight: 500; font-family: var(--font-mono); }
    .call-window { height: 360px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 14px; background: rgba(0,0,0,0.3); border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); margin-bottom: 14px; }
    .chat-bubble { padding: 12px 16px; border-radius: 14px; font-size: 13.5px; line-height: 1.5; max-width: 85%; }
    .chat-agent { align-self: flex-start; background: #1e293b; border: 1px solid #334155; border-bottom-left-radius: 2px; }
    .chat-patient { align-self: flex-end; background: linear-gradient(135deg, #1d4ed8, #2563eb); color: white; border-bottom-right-radius: 2px; }
    .escalation-box { background: linear-gradient(180deg, rgba(239, 68, 68, 0.12) 0%, rgba(17, 24, 39, 1) 100%); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 14px; padding: 20px; margin-bottom: 24px; }
    .tag-flag { background: #991b1b; color: #fee2e2; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; margin-right: 4px; }
    .play-turn-btn { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 3px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; margin-left: 6px; }
    .bubble-speaker { display: flex; justify-content: space-between; align-items: center; font-size: 11px; opacity: 0.8; margin-bottom: 4px; font-weight: 600; }
    .input-bar { display: flex; gap: 8px; }
    .input-bar input { flex: 1; background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 10px; color: white; padding: 10px 14px; font-size: 13.5px; outline: none; }
    .presets-container { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
    .med-tag { display: inline-block; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); color: #93c5fd; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin: 3px; }

    @media (max-width: 768px) {
      body { padding: 12px; }
      .main-grid { grid-template-columns: 1fr; }
      .tabs-bar { flex-direction: column; }
      .intake-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

<div class="container">
  <header>
    <div class="header-left">
      <h1>🩺 Sarvam AI Healthcare Platform</h1>
      <p>AI Clinical Diagnoser • Prescription Digitizer & Reminders • Sovereign Multilingual</p>
    </div>
  </header>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- MANDATORY PATIENT INTAKE FORM (DEVICE-SPECIFIC & USER INTERACTIVE)   -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div class="patient-intake-card">
    <div class="intake-header">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:22px;">👤</span>
        <div>
          <h3 style="font-size:15px; font-weight:700; color:#fff;">Patient Details (Required for Clinical Evaluation & Timetables)</h3>
          <p style="font-size:12px; color:#a5b4fc;">Please enter your details below. Each visitor's profile and timetable are personalized on their own device.</p>
        </div>
      </div>
      <span class="badge" id="profile-status-badge" style="background:rgba(245,158,11,0.2); color:#fbbf24; border-color:rgba(245,158,11,0.3);">
        ⚠️ Please Enter Your Details
      </span>
    </div>

    <div class="intake-grid">
      <div class="form-group">
        <label>Full Name *</label>
        <input type="text" id="patient-name-input" class="form-input" placeholder="Enter Full Name (e.g. Priya Sharma)" oninput="onProfileInputChanged()">
      </div>
      <div class="form-group">
        <label>Age *</label>
        <input type="number" id="patient-age-input" class="form-input" placeholder="Age (e.g. 24)" min="1" max="120" oninput="onProfileInputChanged()">
      </div>
      <div class="form-group">
        <label>Gender *</label>
        <select id="patient-gender-input" class="form-input" onchange="onProfileInputChanged()">
          <option value="" disabled selected>Select Gender</option>
          <option value="Male">Male</option>
          <option value="Female">Female</option>
          <option value="Other">Other</option>
        </select>
      </div>
      <div class="form-group">
        <label>Preferred Language</label>
        <select id="patient-lang-input" class="form-input" onchange="onProfileInputChanged()">
          <option value="Hindi" selected>🇮🇳 Hindi (हिन्दी)</option>
          <option value="Telugu">🇮🇳 Telugu (తెలుగు)</option>
          <option value="Tamil">🇮🇳 Tamil (தமிழ்)</option>
          <option value="Bengali">🇮🇳 Bengali (বাংলা)</option>
          <option value="Marathi">🇮🇳 Marathi (मराठी)</option>
          <option value="Gujarati">🇮🇳 Gujarati (ગુજરાતી)</option>
          <option value="Kannada">🇮🇳 Kannada (ಕನ್ನಡ)</option>
          <option value="English">🌐 English</option>
        </select>
      </div>
    </div>
  </div>

  <!-- 3-Way Mode Switcher Tabs -->
  <div class="tabs-bar">
    <button class="tab-btn active" id="tab-btn-diagnose" onclick="switchTab('diagnose')">
      🩺 AI Symptom Diagnoser & Safe Pain Relief
    </button>
    <button class="tab-btn" id="tab-btn-prescription" onclick="switchTab('prescription')">
      📄 Upload Prescription & Smart Reminders
    </button>
    <button class="tab-btn" id="tab-btn-companion" onclick="switchTab('companion')">
      📋 Outbound Voice Follow-Up Companion
    </button>
  </div>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- TAB 1: INTERACTIVE SYMPTOM DIAGNOSER + SAFE PAIN RELIEF            -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div id="tab-diagnose">
    <div class="card">
      <div class="card-header">
        <h2>🩺 State Your Symptoms or Medical Problem</h2>
        <span class="badge" style="color: #60a5fa;">Sarvam-105B Clinical Engine</span>
      </div>

      <p style="font-size: 13.5px; color: #94a3b8; margin-bottom: 12px;">
        Tell the AI what you are feeling. It will formulate a <strong>differential diagnosis, triage level, and safe low-risk pain relief guidance</strong> tailored to your age and gender.
      </p>

      <textarea id="diag-input" class="symptom-textarea" placeholder="उदाहरण: मुझे 2 दिन से सिर में तेज दर्द और बुखार है, क्या मैं कोई सुरक्षित दवाई ले सकता हूँ जिससे दर्द में राहत मिले? (Or describe in English)..."></textarea>

      <!-- Quick Preset Symptom Chips -->
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
        <span style="font-size:11px; color:#64748b; align-self:center;">Quick Presets:</span>
        <button class="chip" onclick="setPreset('मुझे 2 दिन से तेज सिरदर्द, थकान और हल्का बुखार है। दर्द कम करने के लिए कोई सुरक्षित दवाई बताएं।')">1. Headache & Fever (Safe Pain Relief)</button>
        <button class="chip" onclick="setPreset('मुझे 6 घंटे से पेट के दाहिने निचले हिस्से में बहुत तेज दर्द है, मतली आ रही है और हल्का बुखार है।')">2. Acute Abdominal Pain (Appendicitis Check)</button>
        <button class="chip" onclick="setPreset('छाती के बीच में भारीपन और दबाव है जो बाएं हाथ तक जा रहा है, और सांस फूल रही है।')">3. Chest Pressure (Cardiac Red Flag)</button>
        <button class="chip" onclick="setPreset('गले में बहुत दर्द और खराश है, कुछ भी निगलने में दर्द हो रहा है।')">4. Sore Throat & Swallowing Pain</button>
      </div>

      <div style="display:flex; gap:12px; justify-content:space-between; align-items:center;">
        <button class="mic-btn" id="diag-mic-btn" onclick="toggleDiagMic()">
          <span id="diag-mic-icon">🎙️</span>
          <span id="diag-mic-text">Speak Problem (Saaras v4 Mic)</span>
        </button>

        <button class="btn btn-green" id="diag-submit-btn" onclick="runDiagnosis()">
          🔍 Analyze Symptoms & Suggest Safe Relief
        </button>
      </div>
    </div>

    <!-- Diagnostic Result Container -->
    <div id="diag-result-container" style="display:none;"></div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- TAB 2: INTERACTIVE PRESCRIPTION UPLOADER & TIMETABLE                -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div id="tab-prescription" style="display:none;">
    <!-- Upload & Input Card -->
    <div class="card" style="border: 1px solid #7c3aed; background: linear-gradient(180deg, #1b1736 0%, #111827 100%);">
      <div class="card-header">
        <h2>📄 Upload Prescription / Doctor Notes</h2>
        <span class="badge" style="background: rgba(124, 58, 237, 0.3); color: #c4b5fd;">Sarvam Vision 2.1 OCR + Sarvam-105B</span>
      </div>
      <p style="font-size: 13.5px; color: #cbd5e1; margin-bottom: 16px;">
        Upload any prescription file (PDF/Image) <strong>OR</strong> type/paste doctor instructions. The AI extracts all medicines, dosages, and schedules, building your <strong>Personalized Daily Medication Timetable with Spoken Hindi/Indic Alarms</strong>.
      </p>

      <!-- Drag & Drop Zone -->
      <div class="drop-zone" onclick="document.getElementById('prescription-file-input').click()">
        <div style="font-size: 34px; margin-bottom: 6px;">📑</div>
        <div style="font-weight: 700; font-size: 15px; color: #c4b5fd;" id="drop-zone-text">Click to Select Prescription File (PDF, PNG, JPG)</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Supports hospital discharge summaries, prescription slips, and clinic notes</div>
      </div>
      <input type="file" id="prescription-file-input" style="display:none;" accept=".pdf,.png,.jpg,.jpeg" onchange="onFileSelected(this)">

      <!-- OR Direct Text Input -->
      <div style="margin-top: 18px;">
        <label style="font-size: 13px; font-weight: 600; color: #cbd5e1; display: block; margin-bottom: 6px;">
          ✍️ Or Type / Paste Prescription Details Directly:
        </label>
        <textarea id="prescription-text-input" class="symptom-textarea" style="height: 100px;" placeholder="उदाहरण: Tab Paracetamol 650mg morning & night after food for fever, Tab Pantocid 40mg once in morning before breakfast, Cap Azithromycin 500mg afternoon after lunch for 3 days..."></textarea>
      </div>

      <!-- Quick 1-Click Interactive Prescriptions -->
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin: 12px 0;">
        <span style="font-size:11px; color:#94a3b8; align-self:center;">Quick 1-Click Samples:</span>
        <button class="chip" onclick="setPrescriptionPreset('Tab. Paracetamol 650mg — 1 tablet morning & night after food for fever & body ache.\nTab. Pantocid 40mg — 1 tablet in morning before breakfast (empty stomach).\nCap. Azithromycin 500mg — 1 capsule once daily after lunch for 3 days.\nTab. Cetirizine 10mg — 1 tablet at bedtime for cold & sneezing.')">1. Fever, Cold & Antibiotic</button>
        <button class="chip" onclick="setPrescriptionPreset('Tab. Metformin 500mg — 1 tablet twice daily after morning breakfast and dinner for blood sugar.\nTab. Telmisartan 40mg — 1 tablet every morning after breakfast for blood pressure.\nTab. Atorvastatin 10mg — 1 tablet at night before bedtime for cholesterol.')">2. Diabetes & Hypertension</button>
        <button class="chip" onclick="setPrescriptionPreset('Tab. Cefixime 200mg — 1 tablet twice daily after meals for 5 days post-surgery.\nTab. Aceclofenac + Paracetamol — 1 tablet morning & evening after meals for surgical pain relief.\nCap. Pan-D — 1 capsule morning before breakfast.\nTab. Chymoral Forte — 1 tablet 3 times daily 30 minutes before food for wound swelling.')">3. Post-Surgery Recovery Regimen</button>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:16px;">
        <button class="btn btn-purple" id="process-prescription-btn" onclick="processPrescription()">
          ⚡ Process Prescription & Generate Timetable
        </button>
      </div>
    </div>

    <!-- Dynamic Timetable Container -->
    <div id="reminder-timetable-container" style="display:none; margin-top:20px;">
      <div class="card">
        <div class="card-header">
          <h2 id="timetable-title">⏰ Daily Medication Reminder Timetable</h2>
          <span class="badge active" id="timetable-status-badge">● Personalized Alarms Active</span>
        </div>

        <!-- Master Timetable Audio Player Bar (Bulbul v3) -->
        <div id="timetable-audio-bar" style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; background: rgba(124, 58, 237, 0.15); border: 1px solid rgba(124, 58, 237, 0.35); padding: 12px 16px; border-radius: 10px; margin-bottom: 16px;">
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:22px;">🎧</span>
            <div>
              <div style="font-weight:700; font-size:14px; color:#fff;">Spoken Medication Schedule (Sarvam Bulbul v3)</div>
              <div style="font-size:12px; color:#cbd5e1;" id="timetable-audio-status">Click to listen to complete daily schedule in your selected language</div>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <button class="btn btn-purple" id="btn-play-all-timetable" style="padding: 7px 14px; font-size: 12px; display:inline-flex; align-items:center; gap:6px;" onclick="toggleAllTimetableAudio()">
              <span id="all-tt-icon">▶️</span> <span id="all-tt-text">Play Full Audio Schedule</span>
            </button>
            <button class="btn btn-secondary" id="btn-stop-all-timetable" style="padding: 7px 12px; font-size: 12px; display:none;" onclick="stopAllTimetableAudio()">
              ⏹️ Stop
            </button>
          </div>
        </div>
        
        <div id="timetable-meta-box" style="background: rgba(0,0,0,0.25); padding: 12px 16px; border-radius: 10px; margin-bottom: 16px; border-left: 3px solid #7c3aed; font-size: 13px;">
          <!-- Populated dynamically -->
        </div>

        <div id="timetable-slots-list">
          <!-- Populated dynamically -->
        </div>
      </div>
    </div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- TAB 3: POST-DISCHARGE COMPANION (VOICE RECORDING + INTERACTIVE)     -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div id="tab-companion" style="display:none;">
    <div id="escalation-container">__ESCALATION_BLOCK__</div>

    <div class="main-grid">
      <!-- Live Call Simulator with Voice Recording -->
      <div class="card live-call-card" style="border: 1px solid #3b82f6;">
        <div class="card-header">
          <h2>📞 Outbound Voice Check-In Call</h2>
          <span class="badge active">● AI Bot Ready</span>
        </div>

        <div class="call-window" id="call-window">
          <div class="chat-bubble chat-agent">
            <div class="bubble-speaker"><span>🤖 Hospital Care Agent (Bulbul v3)</span></div>
            <div>Click <strong>"Start Outbound Call"</strong> to receive the call. The agent will greet you by your name, review your prescribed medicines, and you can <strong>speak directly into your microphone</strong> to answer each question!</div>
          </div>
        </div>

        <!-- Quick Preset Reply Chips -->
        <div class="presets-container" id="companion-presets-bar" style="display:none;">
          <span style="font-size: 11px; color: var(--text-muted); align-self: center;">Quick Replies:</span>
          <button class="chip" id="preset-reply-confirm" onclick="useCompanionPreset(this.innerText)">1. हाँ जी, मैं ही बात कर रहा हूँ।</button>
          <button class="chip" onclick="useCompanionPreset('हाँ, मैंने समय पर अपनी दवाइयाँ ले ली हैं और अब बेहतर लग रहा है।')">2. Normal Adherence</button>
          <button class="chip" onclick="useCompanionPreset('कल से उल्टी जैसा लग रहा था इसलिए मैंने दवाई नहीं ली और अब छाती में दर्द हो रहा है।')">3. Missed Dose + Chest Pain</button>
        </div>

        <!-- Voice Recording & Input Bar -->
        <div class="input-bar" style="margin-bottom: 12px;">
          <button class="mic-btn" id="comp-record-btn" onclick="toggleCompanionRecording()" disabled title="Click to speak your reply">
            <span id="comp-mic-icon">🎙️</span>
            <span id="comp-mic-text">Record Voice</span>
          </button>
          <input type="text" id="comp-user-input" placeholder="Or type your reply here..." disabled onkeydown="if(event.key==='Enter') sendCompanionTurn()">
          <button class="btn" id="comp-send-btn" onclick="sendCompanionTurn()" disabled>Send</button>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center;">
          <button class="btn btn-green" id="start-call-btn" onclick="startCall()">📞 Start Outbound Call</button>
          <button class="btn btn-red" id="end-call-btn" onclick="endCall()" style="display:none;">🛑 End Call & Evaluate</button>
        </div>
      </div>

      <!-- Patient Record Summary -->
      <div style="display:flex; flex-direction:column; gap:20px;">
        <div class="card">
          <div class="card-header">
            <h2 id="tab3-patient-header">🧑‍⚕️ Active Patient: <span id="tab3-patient-name" style="color:#60a5fa;">Awaiting Name Input</span></h2>
            <span class="badge" style="color:#60a5fa;" id="tab3-patient-id">PATIENT</span>
          </div>
          <div class="meta-row"><span class="meta-label">Demographics</span><span class="meta-value" id="tab3-patient-demo">Awaiting Input</span></div>
          <div class="meta-row"><span class="meta-label">Clinic / Hospital</span><span class="meta-value" id="tab3-hospital" style="color:#a5b4fc;">Awaiting Prescription Upload</span></div>
          <div class="meta-row"><span class="meta-label">Treating Doctor</span><span class="meta-value" id="tab3-doctor" style="color:#a5b4fc;">Awaiting Prescription Upload</span></div>
          <div class="meta-row"><span class="meta-label">Diagnosis</span><span class="meta-value" id="tab3-diagnosis" style="color:#fbbf24;">Awaiting Prescription Upload</span></div>
          <div class="meta-row"><span class="meta-label">Active Prescriptions</span><span class="meta-value" id="tab3-meds-list">None recorded (Upload in Tab 2)</span></div>
        </div>

        <div class="card">
          <div class="card-header">
            <h2>🛡️ Clinical Triage & Sovereign Intelligence</h2>
          </div>
          <p style="font-size:13px; color:#94a3b8; line-height:1.6;">
            If the patient reports missed doses or dangerous symptoms (e.g., chest pain, severe shortness of breath), the system flags the patient, runs <strong>Sarvam Mayura</strong> to translate the alert into English, and notifies the hospital emergency team immediately.
          </p>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// ── CLIENT-SIDE STORAGE & PROFILE MANAGEMENT ────────────────────────────────
function getStoredProfile() {
  try {
    const raw = localStorage.getItem('sarvam_patient_profile');
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return { name: '', age: '', gender: '', language: 'Hindi' };
}

function saveStoredProfile(p) {
  try {
    localStorage.setItem('sarvam_patient_profile', JSON.stringify(p));
  } catch (e) {}
}

function getStoredTimetable() {
  try {
    const raw = localStorage.getItem('sarvam_patient_timetable');
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return null;
}

function saveStoredTimetable(tt) {
  try {
    localStorage.setItem('sarvam_patient_timetable', JSON.stringify(tt));
  } catch (e) {}
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  const profile = getStoredProfile();
  if (profile.name) document.getElementById('patient-name-input').value = profile.name;
  if (profile.age) document.getElementById('patient-age-input').value = profile.age;
  if (profile.gender) document.getElementById('patient-gender-input').value = profile.gender;
  if (profile.language) {
    document.getElementById('patient-lang-input').value = profile.language;
  }
  updateProfileBadge();

  // Load stored timetable if any exists on this device
  const tt = getStoredTimetable();
  if (tt) {
    renderTimetable(tt);
  }
});

function onProfileInputChanged() {
  const name = document.getElementById('patient-name-input').value.trim();
  const age = document.getElementById('patient-age-input').value.trim();
  const gender = document.getElementById('patient-gender-input').value;
  const lang = document.getElementById('patient-lang-input').value;

  const profile = { name, age, gender, language: lang };
  saveStoredProfile(profile);
  updateProfileBadge();

  // Also update backend session
  if (name && age && gender) {
    fetch('/api/update-patient', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ patient_name: name, age: age, gender: gender, language: lang })
    }).catch(() => {});
  }
}

function updateProfileBadge() {
  const name = document.getElementById('patient-name-input').value.trim();
  const age = document.getElementById('patient-age-input').value.trim();
  const gender = document.getElementById('patient-gender-input').value;
  const lang = document.getElementById('patient-lang-input').value;
  const badge = document.getElementById('profile-status-badge');

  if (name && age && gender) {
    badge.className = 'badge active';
    badge.style.background = 'rgba(16, 185, 129, 0.2)';
    badge.style.color = '#34d399';
    badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
    badge.innerText = `✅ Active: ${name} (${age} Y / ${gender})`;

    document.getElementById('tab3-patient-name').innerText = name;
    document.getElementById('tab3-patient-demo').innerText = `${age} Y / ${gender}`;
    document.getElementById('tab3-patient-lang').innerText = lang;

    const confirmChip = document.getElementById('preset-reply-confirm');
    if (confirmChip) confirmChip.innerText = `1. हाँ जी, मैं ${name} ही बात कर रहा हूँ।`;
  } else {
    badge.className = 'badge';
    badge.style.background = 'rgba(245, 158, 11, 0.2)';
    badge.style.color = '#fbbf24';
    badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
    badge.innerText = '⚠️ Please Enter Name, Age & Gender Above';

    document.getElementById('tab3-patient-name').innerText = name || 'Awaiting Name Input';
    document.getElementById('tab3-patient-demo').innerText = (age && gender) ? `${age} Y / ${gender}` : 'Awaiting Input';
  }
}

function requireProfileValidation() {
  const name = document.getElementById('patient-name-input').value.trim();
  const age = document.getElementById('patient-age-input').value.trim();
  const gender = document.getElementById('patient-gender-input').value;

  if (!name || !age || !gender) {
    alert("⚠️ Please fill in your Full Name, Age, and Gender in the Patient Details form at the top first!");
    const nameInput = document.getElementById('patient-name-input');
    nameInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    nameInput.focus();
    return null;
  }
  return { name, age, gender, language: document.getElementById('patient-lang-input').value };
}

// ── TAB SWITCHING ──────────────────────────────────────────────────────────
function switchTab(tabId) {
  ['diagnose', 'prescription', 'companion'].forEach(t => {
    document.getElementById('tab-' + t).style.display = (t === tabId ? 'block' : 'none');
    document.getElementById('tab-btn-' + t).classList.toggle('active', t === tabId);
  });
}

function setPreset(txt) {
  document.getElementById('diag-input').value = txt;
}

// ── TAB 1: DIAGNOSER LOGIC ──────────────────────────────────────────────────
let isDiagRecording = false;
let diagMediaRecorder = null;
let diagAudioChunks = [];

async function toggleDiagMic() {
  const profile = requireProfileValidation();
  if (!profile) return;

  const btn = document.getElementById('diag-mic-btn');
  const txt = document.getElementById('diag-mic-text');
  const lang = profile.language;

  if (!isDiagRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      diagAudioChunks = [];
      diagMediaRecorder = new MediaRecorder(stream);
      diagMediaRecorder.ondataavailable = e => { if (e.data.size > 0) diagAudioChunks.push(e.data); };
      diagMediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(diagAudioChunks, { type: 'audio/webm' });
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const b64 = reader.result.split(',')[1];
          txt.innerText = 'Transcribing voice via Saaras v4...';
          btn.disabled = true;

          const res = await fetch('/api/diagnose-voice', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ audio_base64: b64, language: lang, age: profile.age, gender: profile.gender })
          });
          const data = await res.json();
          btn.disabled = false;
          btn.classList.remove('recording');
          txt.innerText = 'Speak Problem (Saaras v4 Mic)';

          if (data.user_transcript) {
            document.getElementById('diag-input').value = data.user_transcript;
          }
          if (data.assessment) {
            renderDiagnosis(data.assessment);
          }
        };
      };

      diagMediaRecorder.start();
      isDiagRecording = true;
      btn.classList.add('recording');
      txt.innerText = 'Recording... Click to Stop';
    } catch (err) {
      alert("Microphone access error: " + err.message + "\\nYou can type your symptoms in the box!");
    }
  } else {
    diagMediaRecorder.stop();
    isDiagRecording = false;
    btn.classList.remove('recording');
    txt.innerText = 'Processing via Saaras v4...';
  }
}

async function runDiagnosis() {
  const profile = requireProfileValidation();
  if (!profile) return;

  const text = document.getElementById('diag-input').value.trim();
  const btn = document.getElementById('diag-submit-btn');

  if (!text) {
    alert("Please enter or speak your symptoms!");
    return;
  }

  btn.disabled = true;
  btn.innerText = '🧠 Analyzing with Sarvam-105B...';

  try {
    const res = await fetch('/api/diagnose', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        symptoms: text,
        language: profile.language,
        patient_name: profile.name,
        age: profile.age,
        gender: profile.gender
      })
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerText = '🔍 Analyze Symptoms & Suggest Safe Relief';

    if (data.assessment) {
      renderDiagnosis(data.assessment);
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerText = '🔍 Analyze Symptoms & Suggest Safe Relief';
    alert("Error: " + err.message);
  }
}

// ── TAB 1: DIAGNOSIS RESULT & AUDIO CONTROLLER ────────────────────────────
let diagAudioInstance = null;
let currentDiagAudioB64 = null;
let currentDiagSpokenText = "";

function renderDiagnosis(data) {
  const container = document.getElementById('diag-result-container');
  container.style.display = 'block';

  currentDiagAudioB64 = data.audio_base64 || null;
  currentDiagSpokenText = data.spoken_explanation || data.patient_summary || '';

  let triageClass = 'routine';
  let triageLabel = data.triage_label_hi || 'ROUTINE (सामान्य परामर्श)';
  if (data.triage_level === 'EMERGENCY') {
    triageClass = 'emergency';
    triageLabel = data.triage_label_hi || '🚨 EMERGENCY (तत्काल आपातकालीन चिकित्सा आवश्यक)';
  } else if (data.triage_level === 'URGENT') {
    triageClass = 'urgent';
    triageLabel = data.triage_label_hi || '⚠️ URGENT (24-48 घंटे में डॉक्टर को दिखाएं)';
  }

  const initialSummaryText = data.spoken_explanation || data.patient_summary || (
    `नमस्ते! मैंने आपके लक्षणों का नैदानिक मूल्यांकन कर लिया है। प्राथमिकता स्तर: ${triageLabel}। आप ऊपर दी गई विस्तृत रिपोर्ट देख सकते हैं। क्या आप इस बारे में कोई सवाल पूछना चाहते हैं?`
  );

  const causesList = data.differential_diagnoses || data.likely_causes || [];
  let causesHtml = '';
  causesList.forEach(c => {
    causesHtml += `
      <div style="background:rgba(0,0,0,0.25); padding:10px 14px; border-radius:8px; margin-bottom:8px;">
        <div style="font-weight:700; color:#93c5fd;">${c.condition} <span class="badge" style="font-size:10px;">संभावना: ${c.likelihood || 'संभावित'}</span></div>
        <div style="font-size:12.5px; color:#cbd5e1; margin-top:3px;">${c.clinical_reasoning || ''}</div>
      </div>
    `;
  });

  let reliefHtml = '';
  const safeRelief = data.safe_pain_relief || [];
  if (Array.isArray(safeRelief) && safeRelief.length > 0) {
    reliefHtml += `<h3 style="font-size:15px; color:#34d399; margin-top:6px;">💊 अनुशंसित सुरक्षित दर्द निवारण व देखभाल (Safe Pain Relief Guidance):</h3>`;
    safeRelief.forEach(m => {
      reliefHtml += `
        <div class="medicine-card" style="background:rgba(16,185,129,0.08); border-left:3px solid #34d399; padding:10px 14px; border-radius:8px; margin-bottom:8px;">
          <div class="med-header" style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; color:#6ee7b7;">${m.medicine_or_remedy || m.name}</span>
            <span class="badge" style="color:#34d399;">${m.purpose || 'प्राथमिक राहत'}</span>
          </div>
          <div style="font-size:12.5px; color:#e2e8f0; margin-top:4px;"><strong>निर्देश व खुराक:</strong> ${m.dosage_and_instructions || m.dosage || 'आवश्यकतानुसार सुरक्षित मात्रा में लें'}</div>
          ${m.safety_caution ? `<div style="font-size:11.5px; color:#fca5a5; margin-top:2px;">⚠️ <strong>सावधानी:</strong> ${m.safety_caution}</div>` : ''}
        </div>
      `;
    });
  } else if (data.pain_relief) {
    const pain = data.pain_relief;
    if (pain.recommended_medicines && pain.recommended_medicines.length > 0) {
      reliefHtml += `<h3 style="font-size:15px; color:#34d399; margin-top:6px;">💊 अनुशंसित सुरक्षित दवाइयाँ (Safe Minimal-Side-Effect Medications):</h3>`;
      pain.recommended_medicines.forEach(m => {
        reliefHtml += `
          <div class="medicine-card" style="background:rgba(16,185,129,0.08); border-left:3px solid #34d399; padding:10px 14px; border-radius:8px; margin-bottom:8px;">
            <div class="med-header" style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:700; color:#6ee7b7;">${m.name}</span>
              <span class="badge" style="color:#34d399;">${m.risk_level || 'Safe'}</span>
            </div>
            <div style="font-size:12.5px; color:#e2e8f0; margin-top:4px;"><strong>खुराक:</strong> ${m.dosage}</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:2px;"><strong>निर्देश:</strong> ${m.how_to_take} | <strong>सुरक्षा टिप:</strong> ${m.safety_notes}</div>
          </div>
        `;
      });
    }
  }

  const redFlagsList = data.red_flag_symptoms || data.red_flag_warnings || [];
  let redFlagsHtml = '';
  if (redFlagsList.length > 0) {
    redFlagsHtml = `
      <div style="background:rgba(239, 68, 68, 0.15); border:1px solid rgba(239, 68, 68, 0.4); border-radius:10px; padding:12px 16px; margin-top:14px;">
        <strong style="color:#fca5a5; font-size:13px;">🚩 खतरे के संकेत (तुरंत डॉक्टर या आपातकालीन कक्ष में दिखाएं):</strong>
        <ul style="padding-left:20px; font-size:12.5px; color:#fecaca; margin-top:4px;">
          ${redFlagsList.map(f => `<li>${f}</li>`).join('')}
        </ul>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="card">
      <div class="card-header" style="flex-wrap:wrap; gap:10px;">
        <h2>📋 AI नैदानिक ट्राइएज रिपोर्ट (Clinical Assessment)</h2>
        <button class="btn btn-purple diag-voice-btn" style="padding:6px 14px; font-size:12px; display:inline-flex; align-items:center; gap:6px;" onclick="toggleDiagAudio()">
          <span class="diag-voice-icon">🔊</span> <span class="diag-voice-label">Listen Doctor Audio (Bulbul v3)</span>
        </button>
      </div>

      <!-- Diagnosis Audio Player Bar (Play / Pause / Resume / Stop) -->
      <div id="diag-audio-bar" style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.35); padding: 12px 16px; border-radius: 10px; margin-bottom: 16px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:22px;">🎧</span>
          <div>
            <div style="font-weight:700; font-size:14px; color:#fff;">Spoken Doctor Diagnosis (Sarvam Bulbul v3)</div>
            <div style="font-size:12px; color:#93c5fd;" id="diag-audio-status">Click "Listen Doctor Audio" to hear spoken medical advice</div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <button class="btn btn-purple diag-voice-btn" style="padding: 7px 16px; font-size: 12px; display:inline-flex; align-items:center; gap:6px;" onclick="toggleDiagAudio()">
            <span class="diag-voice-icon">▶️</span> <span class="diag-voice-label">Listen Doctor Audio</span>
          </button>
          <button class="btn btn-secondary" id="diag-audio-stop-btn" style="padding: 7px 12px; font-size: 12px; display:none;" onclick="stopDiagAudio()">
            ⏹️ Stop
          </button>
        </div>
      </div>

      <div class="triage-card ${triageClass}">
        <div>
          <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; font-weight:700;">क्लिनिकल प्राथमिकता (Triage Level)</div>
          <div style="font-size:16px; font-weight:700; margin-top:2px;">${triageLabel}</div>
        </div>
      </div>

      <div style="margin-bottom:16px;">
        <h3 style="font-size:14.5px; color:#cbd5e1; margin-bottom:8px;">🔍 संभावित कारण (Differential Diagnosis):</h3>
        ${causesHtml}
      </div>

      <div class="relief-box">
        ${reliefHtml}
      </div>

      ${redFlagsHtml}

      <!-- ════════════════════════════════════════════════════════════════ -->
      <!-- INTERACTIVE FOLLOW-UP CONSULTATION (CONVERSATION WITH DR. AI)     -->
      <!-- ════════════════════════════════════════════════════════════════ -->
      <div style="margin-top:24px; padding-top:20px; border-top:1px solid rgba(255,255,255,0.12);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <h3 style="font-size:16px; font-weight:700; color:#fff; display:flex; align-items:center; gap:8px;">
            💬 Continue Conversation with Dr. AI (डॉक्टर से आगे बातचीत करें)
          </h3>
          <span class="badge active">● Live Doctor Consultation</span>
        </div>
        <p style="font-size:12.5px; color:#94a3b8; margin-bottom:12px;">
          Have more questions about your diagnosis, medicines, diet, or recovery? Ask Dr. AI below via <strong>voice or text</strong> just like an in-person doctor consultation!
        </p>

        <!-- Consultation Chat Stream -->
        <div class="call-window" id="diag-chat-window" style="min-height:160px; max-height:360px; margin-bottom:14px; background:rgba(0,0,0,0.35); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:14px;">
          <div class="chat-bubble chat-agent">
            <div class="bubble-speaker">
              <span>🩺 Dr. AI (Sarvam-105B)</span>
              ${data.audio_base64 ? `<button class="play-turn-btn" onclick="toggleBubbleAudio(this, '${data.audio_base64}')">🔊 Listen</button>` : ''}
            </div>
            <div>${initialSummaryText}</div>
          </div>
        </div>

        <!-- Quick Follow-up Question Chips -->
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
          <span style="font-size:11px; color:#64748b; align-self:center;">Quick Questions:</span>
          <button class="chip" onclick="useDiagFollowupPreset('क्या मुझे खाने-पीने में कोई खास परहेज (diet precaution) करना चाहिए?')">🥗 क्या परहेज करें?</button>
          <button class="chip" onclick="useDiagFollowupPreset('यह समस्या ठीक होने में सामान्यतः कितने दिन लगते हैं?')">⏱️ ठीक होने में कितने दिन लगेंगे?</button>
          <button class="chip" onclick="useDiagFollowupPreset('क्या मैं इसके साथ कोई अन्य सुरक्षित दर्द निवारक दवाई ले सकता हूँ?')">💊 क्या कोई दूसरी दवाई ले सकते हैं?</button>
          <button class="chip" onclick="useDiagFollowupPreset('अगर लक्षण न सुधरें तो मुझे डॉक्टर या अस्पताल कब जाना चाहिए?')">🏥 डॉक्टर के पास कब जाएं?</button>
        </div>

        <!-- Voice & Text Input Bar -->
        <div class="input-bar" style="margin-bottom:0;">
          <button class="mic-btn" id="diag-chat-mic-btn" onclick="toggleDiagChatMic()" title="Click to speak your follow-up question">
            <span id="diag-chat-mic-icon">🎙️</span>
            <span id="diag-chat-mic-text">Speak Question</span>
          </button>
          <input type="text" id="diag-chat-input" placeholder="Ask Dr. AI any follow-up question (उदा: क्या मैं दूध या फल ले सकता हूँ?)..." onkeydown="if(event.key==='Enter') sendDiagChatTurn()">
          <button class="btn btn-purple" id="diag-chat-send-btn" onclick="sendDiagChatTurn()">Send</button>
        </div>
      </div>

      <div style="margin-top:16px; font-size:11.5px; color:#64748b; font-style:italic;">
        ⚕️ अस्वीकरण: यह एक AI ट्राइएज मूल्यांकन है। यह किसी योग्य चिकित्सक के प्रत्यक्ष नैदानिक परीक्षण का विकल्प नहीं है। गंभीर स्थिति में तुरंत नजदीकी अस्पताल के आपातकालीन विभाग में जाएं।
      </div>
    </div>
  `;

  // Initialize interactive consultation session state
  diagChatHistory = [
    { role: "assistant", content: initialSummaryText }
  ];
  const storedProfile = getStoredProfile();
  diagPatientContext = {
    name: storedProfile.name || "Patient",
    age: storedProfile.age || "",
    gender: storedProfile.gender || "",
    initial_diagnosis: data.triage_label_hi || data.triage_level || "Clinical Evaluation",
    initial_symptoms: document.getElementById('diag-input').value || ""
  };

  container.scrollIntoView({ behavior: 'smooth' });

  // DO NOT autoplay audio! Show the analyzed output first and let the user click to play
  stopDiagAudio();
  updateDiagButtons('ready');
}

function updateDiagButtons(state) {
  const btns = document.querySelectorAll('.diag-voice-btn');
  const stopBtn = document.getElementById('diag-audio-stop-btn');
  const statusEl = document.getElementById('diag-audio-status');

  btns.forEach(btn => {
    const icon = btn.querySelector('.diag-voice-icon');
    const label = btn.querySelector('.diag-voice-label');

    if (state === 'playing') {
      if (icon) icon.innerText = '⏸️';
      if (label) label.innerText = 'Pause Doctor Audio';
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-purple');
    } else if (state === 'paused') {
      if (icon) icon.innerText = '▶️';
      if (label) label.innerText = 'Resume Doctor Audio';
      btn.classList.add('btn-secondary');
      btn.classList.remove('btn-purple');
    } else { // stopped / ready
      if (icon) icon.innerText = '🔊';
      if (label) label.innerText = 'Listen Doctor Audio (Bulbul v3)';
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-purple');
    }
  });

  if (state === 'playing') {
    if (stopBtn) stopBtn.style.display = 'inline-flex';
    if (statusEl) statusEl.innerText = '🔊 Playing AI doctor diagnosis advice (Bulbul v3)...';
  } else if (state === 'paused') {
    if (stopBtn) stopBtn.style.display = 'inline-flex';
    if (statusEl) statusEl.innerText = 'Audio paused. Click Resume to continue listening.';
  } else {
    if (stopBtn) stopBtn.style.display = 'none';
    if (statusEl) statusEl.innerText = 'Click "Listen Doctor Audio" to hear spoken medical advice.';
  }
}

function toggleDiagAudio() {
  // If audio is already active -> toggle pause / play
  if (diagAudioInstance) {
    if (!diagAudioInstance.paused) {
      diagAudioInstance.pause();
      updateDiagButtons('paused');
      return;
    } else {
      if (typeof stopAllActiveAudio === 'function') stopAllActiveAudio();
      diagAudioInstance.play();
      updateDiagButtons('playing');
      return;
    }
  }

  // Audio not yet started
  if (currentDiagAudioB64) {
    startDiagAudioPlayback(currentDiagAudioB64);
    return;
  }

  // If audio wasn't pre-rendered, synthesize on demand
  if (currentDiagSpokenText) {
    const profile = getStoredProfile();
    const lang = profile.language || 'Hindi';
    const statusEl = document.getElementById('diag-audio-status');
    if (statusEl) statusEl.innerText = 'Synthesizing voice via Sarvam Bulbul v3...';

    fetch('/api/speak-reminder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text: currentDiagSpokenText, language: lang })
    })
    .then(r => r.json())
    .then(resData => {
      if (resData.audio_base64) {
        currentDiagAudioB64 = resData.audio_base64;
        startDiagAudioPlayback(resData.audio_base64);
      } else {
        alert("Could not generate audio diagnosis.");
      }
    })
    .catch(err => {
      alert("Audio error: " + err.message);
    });
  }
}

function startDiagAudioPlayback(b64) {
  if (typeof stopAllActiveAudio === 'function') stopAllActiveAudio();
  if (diagAudioInstance) {
    diagAudioInstance.pause();
    diagAudioInstance = null;
  }

  const audio = new Audio("data:audio/wav;base64," + b64);
  diagAudioInstance = audio;

  audio.onplay = () => {
    updateDiagButtons('playing');
  };

  audio.onpause = () => {
    if (!audio.ended) {
      updateDiagButtons('paused');
    }
  };

  audio.onended = () => {
    stopDiagAudio();
    const statusEl = document.getElementById('diag-audio-status');
    if (statusEl) statusEl.innerText = 'Playback finished. Click Listen Doctor Audio to replay.';
  };

  audio.play().catch(e => {
    console.log("Audio autoplay or gesture needed:", e);
    updateDiagButtons('ready');
  });
}

function stopDiagAudio() {
  if (diagAudioInstance) {
    diagAudioInstance.pause();
    diagAudioInstance.currentTime = 0;
    diagAudioInstance = null;
  }
  updateDiagButtons('ready');
}

// ── FOLLOW-UP CONSULTATION INTERACTIVE CHAT LOGIC ─────────────────────────
let diagChatHistory = [];
let diagPatientContext = {};
let isDiagChatRecording = false;
let diagChatMediaRecorder = null;
let diagChatAudioChunks = [];

let currentBubbleAudio = null;
let currentBubbleBtn = null;

function toggleBubbleAudio(btn, audioB64) {
  if (currentBubbleAudio && currentBubbleBtn === btn) {
    if (!currentBubbleAudio.paused) {
      currentBubbleAudio.pause();
      btn.innerText = '▶ Resume';
      return;
    } else {
      if (typeof stopAllActiveAudio === 'function') stopAllActiveAudio();
      currentBubbleAudio.play();
      btn.innerText = '⏸ Pause';
      return;
    }
  }

  // Stop other audio first
  if (typeof stopAllActiveAudio === 'function') stopAllActiveAudio();
  if (currentBubbleAudio) {
    currentBubbleAudio.pause();
    if (currentBubbleBtn) currentBubbleBtn.innerText = '🔊 Listen';
    currentBubbleAudio = null;
    currentBubbleBtn = null;
  }

  if (!audioB64) return;
  const audio = new Audio("data:audio/wav;base64," + audioB64);
  currentBubbleAudio = audio;
  currentBubbleBtn = btn;
  btn.innerText = '⏸ Pause';

  audio.onended = () => {
    btn.innerText = '🔊 Listen';
    currentBubbleAudio = null;
    currentBubbleBtn = null;
  };
  audio.onpause = () => {
    if (!audio.ended) btn.innerText = '▶ Resume';
  };
  audio.onplay = () => {
    btn.innerText = '⏸ Pause';
  };

  audio.play().catch(() => {
    btn.innerText = '🔊 Listen';
  });
}

function appendDiagChatBubble(role, text, audioB64) {
  const win = document.getElementById('diag-chat-window');
  if (!win) return;
  const d = document.createElement('div');
  d.className = 'chat-bubble ' + (role === 'assistant' ? 'chat-agent' : 'chat-patient');

  let speakerLabel = role === 'assistant' ? '🩺 Dr. AI (Sarvam-105B)' : '👤 You';
  let playBtnHtml = '';
  if (audioB64) {
    playBtnHtml = `<button class="play-turn-btn" onclick="toggleBubbleAudio(this, '${audioB64}')">🔊 Listen</button>`;
  }

  d.innerHTML = `
    <div class="bubble-speaker">
      <span>${speakerLabel}</span>
      ${playBtnHtml}
    </div>
    <div>${text}</div>
  `;
  win.appendChild(d);
  win.scrollTop = win.scrollHeight;
}

async function sendDiagChatTurn() {
  const inputEl = document.getElementById('diag-chat-input');
  const text = inputEl.value.trim();
  if (!text) return;

  const profile = getStoredProfile();
  const lang = profile.language || 'Hindi';

  inputEl.value = '';
  inputEl.disabled = true;
  document.getElementById('diag-chat-send-btn').disabled = true;

  appendDiagChatBubble('user', text);

  const win = document.getElementById('diag-chat-window');
  const loading = document.createElement('div');
  loading.className = 'chat-bubble chat-agent';
  loading.id = 'diag-chat-loading';
  loading.innerHTML = '<div style="color:#a5b4fc; font-style:italic;">🩺 Dr. AI is evaluating your question with Sarvam-105B...</div>';
  win.appendChild(loading);
  win.scrollTop = win.scrollHeight;

  try {
    const res = await fetch('/api/diagnose-followup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_text: text,
        history: diagChatHistory,
        patient_context: diagPatientContext,
        language: lang
      })
    });
    const data = await res.json();
    const loadEl = document.getElementById('diag-chat-loading');
    if (loadEl) loadEl.remove();

    if (data.history) diagChatHistory = data.history;
    appendDiagChatBubble('assistant', data.reply, data.audio_base64);
  } catch (err) {
    const loadEl = document.getElementById('diag-chat-loading');
    if (loadEl) loadEl.remove();
    appendDiagChatBubble('assistant', "माफ़ कीजिए, परामर्श में समस्या आई: " + err.message);
  } finally {
    inputEl.disabled = false;
    document.getElementById('diag-chat-send-btn').disabled = false;
    inputEl.focus();
  }
}

function useDiagFollowupPreset(text) {
  const inputEl = document.getElementById('diag-chat-input');
  if (inputEl) {
    inputEl.value = text;
    sendDiagChatTurn();
  }
}

async function toggleDiagChatMic() {
  const profile = getStoredProfile();
  const lang = profile.language || 'Hindi';
  const btn = document.getElementById('diag-chat-mic-btn');
  const txt = document.getElementById('diag-chat-mic-text');

  if (!isDiagChatRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      diagChatAudioChunks = [];
      diagChatMediaRecorder = new MediaRecorder(stream);
      diagChatMediaRecorder.ondataavailable = e => { if (e.data.size > 0) diagChatAudioChunks.push(e.data); };
      diagChatMediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(diagChatAudioChunks, { type: 'audio/webm' });
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const b64 = reader.result.split(',')[1];
          txt.innerText = 'Transcribing voice via Saaras v4...';
          btn.disabled = true;

          const win = document.getElementById('diag-chat-window');
          const loading = document.createElement('div');
          loading.className = 'chat-bubble chat-agent';
          loading.id = 'diag-chat-loading';
          loading.innerHTML = '<div style="color:#a5b4fc; font-style:italic;">🩺 Transcribing via Saaras v4 and consulting Dr. AI...</div>';
          win.appendChild(loading);
          win.scrollTop = win.scrollHeight;

          try {
            const res = await fetch('/api/diagnose-followup-voice', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                audio_base64: b64,
                history: diagChatHistory,
                patient_context: diagPatientContext,
                language: lang
              })
            });
            const data = await res.json();
            const loadEl = document.getElementById('diag-chat-loading');
            if (loadEl) loadEl.remove();

            if (data.user_transcript) {
              appendDiagChatBubble('user', data.user_transcript);
            }
            if (data.history) diagChatHistory = data.history;
            appendDiagChatBubble('assistant', data.reply, data.audio_base64);
          } catch (err) {
            const loadEl = document.getElementById('diag-chat-loading');
            if (loadEl) loadEl.remove();
            appendDiagChatBubble('assistant', "वॉइस परामर्श में समस्या आई: " + err.message);
          } finally {
            btn.disabled = false;
            btn.classList.remove('recording');
            txt.innerText = 'Speak Question';
          }
        };
      };

      diagChatMediaRecorder.start();
      isDiagChatRecording = true;
      btn.classList.add('recording');
      txt.innerText = 'Recording... Click to Stop';
    } catch (err) {
      alert("Microphone access error: " + err.message);
    }
  } else {
    diagChatMediaRecorder.stop();
    isDiagChatRecording = false;
    btn.classList.remove('recording');
    txt.innerText = 'Processing...';
  }
}

// ── TAB 2: PRESCRIPTION UPLOAD & DYNAMIC TIMETABLE ──────────────────────────
let uploadedFileBase64 = null;
let uploadedFileName = "";

function onFileSelected(input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  uploadedFileName = file.name;
  document.getElementById('drop-zone-text').innerHTML = `✅ <strong>${file.name}</strong> (${(file.size / 1024).toFixed(1)} KB) selected`;
  const reader = new FileReader();
  reader.readAsDataURL(file);
  reader.onloadend = () => {
    uploadedFileBase64 = reader.result.split(',')[1];
  };
}

function setPrescriptionPreset(text) {
  document.getElementById('prescription-text-input').value = text;
}

async function processPrescription() {
  const profile = requireProfileValidation();
  if (!profile) return;

  const textInput = document.getElementById('prescription-text-input').value.trim();
  const btn = document.getElementById('process-prescription-btn');

  if (!textInput && !uploadedFileBase64) {
    alert("Please select a prescription file or type your prescription details!");
    return;
  }

  btn.disabled = true;
  btn.innerText = '🧠 Analyzing with Sarvam AI...';

  try {
    const res = await fetch('/api/upload-prescription', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        prescription_text: textInput,
        file_base64: uploadedFileBase64,
        file_name: uploadedFileName,
        patient_name: profile.name,
        age: profile.age,
        gender: profile.gender,
        language: profile.language
      })
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerText = '⚡ Process Prescription & Generate Timetable';

    if (data.timetable) {
      saveStoredTimetable(data.timetable);
      renderTimetable(data.timetable);
    } else {
      alert("Could not extract timetable. Please check prescription details.");
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerText = '⚡ Process Prescription & Generate Timetable';
    alert("Error processing prescription: " + err.message);
  }
}

function renderTimetable(tt) {
  currentTimetableData = tt;
  const container = document.getElementById('reminder-timetable-container');
  container.style.display = 'block';

  document.getElementById('timetable-title').innerText = `⏰ Daily Medication Timetable for ${tt.patient_name || 'Patient'}`;
  document.getElementById('timetable-meta-box').innerHTML = `
    <div><strong>Diagnosis / Condition:</strong> ${tt.diagnosis || 'Prescription Care Plan'}</div>
    <div style="margin-top:4px; color:#cbd5e1;"><strong>Doctor's Advice:</strong> ${tt.doctor_notes || 'Take all medicines as directed.'}</div>
  `;

  // Update Tab 3 dynamic patient summary
  const tab3Name = document.getElementById('tab3-patient-name');
  if (tab3Name) tab3Name.innerText = tt.patient_name || 'Patient';

  const tab3Meds = document.getElementById('tab3-meds-list');
  if (tab3Meds && tt.medications_list) {
    tab3Meds.innerHTML = tt.medications_list.map(m => `<span class="med-tag">${m}</span>`).join(' ');
  }

  const tab3Hosp = document.getElementById('tab3-hospital');
  if (tab3Hosp) tab3Hosp.innerText = tt.hospital_name || 'General Hospital / Clinic';

  const tab3Doc = document.getElementById('tab3-doctor');
  if (tab3Doc) tab3Doc.innerText = tt.doctor_name || 'Attending Physician';

  const tab3Diag = document.getElementById('tab3-diagnosis');
  if (tab3Diag) tab3Diag.innerText = tt.diagnosis || 'Prescription Care Plan';

  const list = document.getElementById('timetable-slots-list');
  list.innerHTML = '';

  (tt.slots || []).forEach((slot, sIdx) => {
    const slotDiv = document.createElement('div');
    slotDiv.className = 'time-slot';

    let medsHtml = '';
    (slot.medicines || []).forEach((m, mIdx) => {
      const rowId = `med-row-${sIdx}-${mIdx}`;
      const speechEscaped = (m.speech || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
      medsHtml += `
        <div class="med-item-row" id="${rowId}">
          <div style="display:flex; align-items:flex-start; gap:10px;">
            <input type="checkbox" onchange="toggleMedTaken('${rowId}', this)" title="Mark as taken" style="margin-top:3px; cursor:pointer;">
            <div>
              <div class="med-title" style="font-weight:700; color:#fff;">${m.name} <span class="badge" style="font-size:11px;">${m.dosage || '1 Dose'}</span></div>
              <div style="font-size:12px; color:#a5b4fc; margin-top:2px;">📋 ${m.instructions || 'As advised'}</div>
              <div style="font-size:11.5px; color:#94a3b8; margin-top:2px;">🎯 ${m.purpose || 'Relief'}</div>
            </div>
          </div>
          <button class="btn btn-purple slot-voice-btn" style="padding:5px 12px; font-size:11px; white-space:nowrap; display:inline-flex; align-items:center; gap:5px;" onclick="toggleSlotVoice(this, '${speechEscaped}')">
            <span>🔊</span> <span>Spoken Alarm (Bulbul v3)</span>
          </button>
        </div>
      `;
    });

    slotDiv.innerHTML = `
      <div class="slot-header">
        <span style="color: ${slot.color || '#fde047'}; font-size:14.5px;">${slot.icon || '⏰'} ${slot.name}</span>
        <span class="badge">${(slot.medicines || []).length} Medicines</span>
      </div>
      ${medsHtml}
    `;
    list.appendChild(slotDiv);
  });

  container.scrollIntoView({ behavior: 'smooth' });
}

function toggleMedTaken(rowId, checkbox) {
  const row = document.getElementById(rowId);
  if (!row) return;
  const title = row.querySelector('.med-title');
  if (checkbox.checked) {
    if (title) title.style.textDecoration = 'line-through';
    row.style.background = 'rgba(16, 185, 129, 0.15)';
  } else {
    if (title) title.style.textDecoration = 'none';
    row.style.background = 'rgba(0, 0, 0, 0.25)';
  }
}

// ── PLAY / PAUSE AUDIO CONTROLLERS FOR TIMETABLE ───────────────────────────
let activeSlotAudio = null;
let activeSlotBtn = null;
let allTimetableAudio = null;
let currentTimetableData = null;

function stopAllActiveAudio() {
  if (diagAudioInstance) {
    diagAudioInstance.pause();
    diagAudioInstance.currentTime = 0;
    diagAudioInstance = null;
    const dBtn = document.getElementById('diag-audio-btn');
    const dStop = document.getElementById('diag-audio-stop-btn');
    const dStatus = document.getElementById('diag-audio-status');
    const dIcon = document.getElementById('diag-btn-icon');
    const dText = document.getElementById('diag-btn-text');
    if (dIcon) dIcon.innerText = '▶️';
    if (dText) dText.innerText = 'Play Diagnosis Audio';
    if (dBtn) {
      dBtn.classList.remove('btn-secondary');
      dBtn.classList.add('btn-purple');
    }
    if (dStop) dStop.style.display = 'none';
    if (dStatus) dStatus.innerText = 'Click to listen to empathetic audio explanation of your diagnosis';
  }
  if (activeSlotAudio) {
    activeSlotAudio.pause();
    activeSlotAudio.currentTime = 0;
    if (activeSlotBtn) {
      activeSlotBtn.innerHTML = '<span>🔊</span> <span>Spoken Alarm (Bulbul v3)</span>';
      activeSlotBtn.classList.remove('btn-secondary');
      activeSlotBtn.classList.add('btn-purple');
    }
    activeSlotAudio = null;
    activeSlotBtn = null;
  }
  if (allTimetableAudio) {
    allTimetableAudio.pause();
    allTimetableAudio.currentTime = 0;
    const playBtn = document.getElementById('btn-play-all-timetable');
    const stopBtn = document.getElementById('btn-stop-all-timetable');
    const statusText = document.getElementById('timetable-audio-status');
    if (playBtn) playBtn.innerHTML = '<span id="all-tt-icon">▶️</span> <span id="all-tt-text">Play Full Audio Schedule</span>';
    if (stopBtn) stopBtn.style.display = 'none';
    if (statusText) statusText.innerText = 'Click to listen to complete daily schedule in your selected language';
    allTimetableAudio = null;
  }
  if (currentBubbleAudio) {
    currentBubbleAudio.pause();
    currentBubbleAudio.currentTime = 0;
    if (currentBubbleBtn) currentBubbleBtn.innerText = '🔊 Listen';
    currentBubbleAudio = null;
    currentBubbleBtn = null;
  }
}

async function toggleSlotVoice(btn, speechText) {
  // If clicking on already active slot audio -> toggle pause / play
  if (activeSlotAudio && activeSlotBtn === btn) {
    if (!activeSlotAudio.paused) {
      activeSlotAudio.pause();
      btn.innerHTML = '<span>▶️</span> <span>Resume Alarm</span>';
      btn.classList.add('btn-secondary');
      btn.classList.remove('btn-purple');
      return;
    } else {
      activeSlotAudio.play();
      btn.innerHTML = '<span>⏸️</span> <span>Pause Alarm</span>';
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-purple');
      return;
    }
  }

  // Stop any other playing audio first
  stopAllActiveAudio();

  const profile = getStoredProfile();
  if (!speechText) speechText = "नमस्ते, यह आपकी दवाई लेने का समय है।";
  const lang = profile.language || 'Hindi';

  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> <span>Generating voice...</span>';

  try {
    const r = await fetch('/api/speak-reminder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text: speechText, language: lang })
    });
    const data = await r.json();
    btn.disabled = false;

    if (data.audio_base64) {
      const audio = new Audio("data:audio/wav;base64," + data.audio_base64);
      activeSlotAudio = audio;
      activeSlotBtn = btn;
      btn.innerHTML = '<span>⏸️</span> <span>Pause Alarm</span>';
      btn.classList.remove('btn-purple');
      btn.classList.add('btn-secondary');

      audio.onended = () => {
        btn.innerHTML = '<span>🔊</span> <span>Spoken Alarm (Bulbul v3)</span>';
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-purple');
        activeSlotAudio = null;
        activeSlotBtn = null;
      };

      await audio.play();
    } else {
      btn.innerHTML = '<span>🔊</span> <span>Spoken Alarm (Bulbul v3)</span>';
      alert("Could not generate audio reminder.");
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = '<span>🔊</span> <span>Spoken Alarm (Bulbul v3)</span>';
    alert("Audio error: " + err.message);
  }
}

async function toggleAllTimetableAudio() {
  const playBtn = document.getElementById('btn-play-all-timetable');
  const stopBtn = document.getElementById('btn-stop-all-timetable');
  const statusText = document.getElementById('timetable-audio-status');

  // If already loaded and playing -> Pause it
  if (allTimetableAudio && !allTimetableAudio.paused) {
    allTimetableAudio.pause();
    playBtn.innerHTML = '<span id="all-tt-icon">▶️</span> <span id="all-tt-text">Resume Audio</span>';
    if (statusText) statusText.innerText = 'Audio paused. Click Resume to continue listening.';
    return;
  }

  // If already loaded and paused -> Resume it
  if (allTimetableAudio && allTimetableAudio.paused && allTimetableAudio.currentTime > 0) {
    allTimetableAudio.play();
    playBtn.innerHTML = '<span id="all-tt-icon">⏸️</span> <span id="all-tt-text">Pause Audio</span>';
    if (statusText) statusText.innerText = '🔊 Playing daily medication schedule...';
    return;
  }

  // Otherwise, synthesize full timetable audio
  stopAllActiveAudio();

  const tt = currentTimetableData || getStoredTimetable();
  if (!tt) {
    alert("Please upload or process a prescription first.");
    return;
  }

  const profile = getStoredProfile();
  const lang = profile.language || 'Hindi';
  const name = tt.patient_name || profile.name || 'Patient';

  // Build spoken text for the full schedule
  let scheduleSpeech = `नमस्ते ${name} जी। यह आपका दैनिक दवाई का समय चक्र है। `;
  if (tt.diagnosis) scheduleSpeech += `बीमारी या निदान: ${tt.diagnosis}। `;
  if (tt.slots && tt.slots.length > 0) {
    tt.slots.forEach(s => {
      const medNames = (s.medicines || []).map(m => m.name + ' (' + (m.instructions || '') + ')').join(', ');
      scheduleSpeech += `${s.name}: ${medNames}। `;
    });
  }
  if (tt.doctor_notes) scheduleSpeech += `डॉक्टर की सलाह: ${tt.doctor_notes}। कृपया अपनी दवाइयाँ समय पर लें। धन्यवाद।`;

  playBtn.disabled = true;
  playBtn.innerHTML = '<span id="all-tt-icon">⏳</span> <span id="all-tt-text">Synthesizing Audio...</span>';
  if (statusText) statusText.innerText = 'Synthesizing voice via Sarvam Bulbul v3...';

  try {
    const r = await fetch('/api/speak-reminder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text: scheduleSpeech, language: lang })
    });
    const data = await r.json();
    playBtn.disabled = false;

    if (data.audio_base64) {
      allTimetableAudio = new Audio("data:audio/wav;base64," + data.audio_base64);
      playBtn.innerHTML = '<span id="all-tt-icon">⏸️</span> <span id="all-tt-text">Pause Audio</span>';
      if (stopBtn) stopBtn.style.display = 'inline-flex';
      if (statusText) statusText.innerText = '🔊 Playing daily medication schedule...';

      allTimetableAudio.onended = () => {
        stopAllTimetableAudio();
      };

      await allTimetableAudio.play();
    } else {
      playBtn.innerHTML = '<span id="all-tt-icon">▶️</span> <span id="all-tt-text">Play Full Audio Schedule</span>';
      alert("Could not generate timetable audio.");
    }
  } catch (err) {
    playBtn.disabled = false;
    playBtn.innerHTML = '<span id="all-tt-icon">▶️</span> <span id="all-tt-text">Play Full Audio Schedule</span>';
    alert("Audio error: " + err.message);
  }
}

function stopAllTimetableAudio() {
  stopAllActiveAudio();
}

function playSlotVoice(speechText) {
  toggleSlotVoice(null, speechText);
}

function playAudioBase64(base64Data) {
  if (!base64Data) return;
  const audio = new Audio("data:audio/wav;base64," + base64Data);
  audio.play();
}

// ── TAB 3: COMPANION VOICE CALL LOGIC ───────────────────────────────────────
let callHistory = [];
let isCompRecording = false;
let compMediaRecorder = null;
let compAudioChunks = [];

async function startCall() {
  const profile = requireProfileValidation();
  if (!profile) return;

  document.getElementById('call-window').innerHTML = '';
  document.getElementById('start-call-btn').style.display = 'none';
  document.getElementById('end-call-btn').style.display = 'inline-flex';
  document.getElementById('companion-presets-bar').style.display = 'flex';
  document.getElementById('comp-record-btn').disabled = false;
  document.getElementById('comp-user-input').disabled = false;
  document.getElementById('comp-send-btn').disabled = false;
  document.getElementById('comp-user-input').focus();

  const tt = getStoredTimetable();
  const medsList = tt && tt.medications_list ? tt.medications_list : [];
  const doctorName = tt && tt.doctor_name ? tt.doctor_name : "";
  const hospitalName = tt && tt.hospital_name ? tt.hospital_name : "";
  const diagnosis = tt && tt.diagnosis ? tt.diagnosis : "";

  const res = await fetch('/api/start-call', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      patient_name: profile.name,
      language: profile.language,
      medications: medsList,
      doctor_name: doctorName,
      hospital_name: hospitalName,
      diagnosis: diagnosis
    })
  });
  const data = await res.json();
  callHistory = data.history;
  appendCallMsg('assistant', data.agent_text, data.audio_base64);
}

function appendCallMsg(role, text, audioB64) {
  const win = document.getElementById('call-window');
  const d = document.createElement('div');
  d.className = 'chat-bubble ' + (role === 'assistant' ? 'chat-agent' : 'chat-patient');

  let speakerLabel = role === 'assistant' ? '🤖 Care Agent (Bulbul v3)' : '👤 Patient (You)';
  let playBtnHtml = '';
  if (audioB64) {
    playBtnHtml = `<button class="play-turn-btn" onclick="playAudioBase64('${audioB64}')">▶ Replay</button>`;
  }

  d.innerHTML = `
    <div class="bubble-speaker">
      <span>${speakerLabel}</span>
      ${playBtnHtml}
    </div>
    <div>${text}</div>
  `;
  win.appendChild(d);
  win.scrollTop = win.scrollHeight;
  if (audioB64) playAudioBase64(audioB64);
}

async function toggleCompanionRecording() {
  const profile = getStoredProfile();
  const btn = document.getElementById('comp-record-btn');
  const txt = document.getElementById('comp-mic-text');

  if (!isCompRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      compAudioChunks = [];
      compMediaRecorder = new MediaRecorder(stream);
      compMediaRecorder.ondataavailable = e => { if (e.data.size > 0) compAudioChunks.push(e.data); };
      compMediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(compAudioChunks, { type: 'audio/webm' });
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const b64 = reader.result.split(',')[1];
          txt.innerText = 'Transcribing voice via Saaras v4...';
          btn.disabled = true;

          const win = document.getElementById('call-window');
          const loading = document.createElement('div');
          loading.className = 'chat-bubble chat-patient';
          loading.id = 'comp-loading-bubble';
          loading.innerHTML = '<div class="bubble-speaker"><span>👤 Patient (Transcribing via Saaras v4...)</span></div><div>⏳ <em>Transcribing spoken audio...</em></div>';
          win.appendChild(loading);
          win.scrollTop = win.scrollHeight;

          const tt = getStoredTimetable();
          const res = await fetch('/api/voice-turn', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              patient_name: profile.name,
              language: profile.language,
              medications: tt && tt.medications_list ? tt.medications_list : [],
              doctor_name: tt && tt.doctor_name ? tt.doctor_name : "",
              hospital_name: tt && tt.hospital_name ? tt.hospital_name : "",
              diagnosis: tt && tt.diagnosis ? tt.diagnosis : "",
              history: callHistory,
              audio_base64: b64
            })
          });
          const data = await res.json();
          loading.remove();

          appendCallMsg('user', data.user_transcript || "Spoken response");
          callHistory = data.history;
          appendCallMsg('assistant', data.agent_text, data.audio_base64);

          btn.disabled = false;
          btn.classList.remove('recording');
          txt.innerText = 'Record Voice';
        };
      };

      compMediaRecorder.start();
      isCompRecording = true;
      btn.classList.add('recording');
      txt.innerText = 'Stop & Send';
    } catch (err) {
      alert("Microphone error: " + err.message + "\\nYou can type in the box below!");
    }
  } else {
    compMediaRecorder.stop();
    isCompRecording = false;
    btn.classList.remove('recording');
    txt.innerText = 'Processing...';
  }
}

async function sendCompanionTurn() {
  const profile = getStoredProfile();
  const inputEl = document.getElementById('comp-user-input');
  const text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = '';
  appendCallMsg('user', text);
  inputEl.disabled = true;
  document.getElementById('comp-send-btn').disabled = true;

  const tt = getStoredTimetable();
  const res = await fetch('/api/chat-turn', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      patient_name: profile.name,
      language: profile.language,
      medications: tt && tt.medications_list ? tt.medications_list : [],
      doctor_name: tt && tt.doctor_name ? tt.doctor_name : "",
      hospital_name: tt && tt.hospital_name ? tt.hospital_name : "",
      diagnosis: tt && tt.diagnosis ? tt.diagnosis : "",
      history: callHistory,
      user_text: text
    })
  });
  const data = await res.json();
  callHistory = data.history;
  appendCallMsg('assistant', data.agent_text, data.audio_base64);

  inputEl.disabled = false;
  document.getElementById('comp-send-btn').disabled = false;
  inputEl.focus();
}

function useCompanionPreset(text) {
  document.getElementById('comp-user-input').value = text;
  sendCompanionTurn();
}

async function endCall() {
  const profile = getStoredProfile();
  document.getElementById('comp-record-btn').disabled = true;
  document.getElementById('comp-user-input').disabled = true;
  document.getElementById('comp-send-btn').disabled = true;
  document.getElementById('end-call-btn').innerText = '⏳ Evaluating...';

  const tt = getStoredTimetable();
  const res = await fetch('/api/end-call', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      patient_name: profile.name,
      language: profile.language,
      medications: tt && tt.medications_list ? tt.medications_list : [],
      doctor_name: tt && tt.doctor_name ? tt.doctor_name : "",
      hospital_name: tt && tt.hospital_name ? tt.hospital_name : "",
      diagnosis: tt && tt.diagnosis ? tt.diagnosis : "",
      history: callHistory
    })
  });
  const data = await res.json();
  document.getElementById('start-call-btn').style.display = 'inline-flex';
  document.getElementById('start-call-btn').innerText = '🔄 Start New Call';
  document.getElementById('end-call-btn').style.display = 'none';
  document.getElementById('end-call-btn').innerText = '🛑 End Call & Evaluate';
  document.getElementById('companion-presets-bar').style.display = 'none';

  if (data.escalation_html) {
    document.getElementById('escalation-container').innerHTML = data.escalation_html;
  }
}
</script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        req_data = json.loads(body) if body else {}

        # ── ENDPOINT: DIAGNOSE SYMPTOMS (TEXT) ──────────────────────────────
        if self.path == "/api/diagnose":
            symptoms = req_data.get("symptoms", "")
            lang = req_data.get("language", "Hindi")
            age = req_data.get("age", "")
            gender = req_data.get("gender", "")
            
            full_symptoms = symptoms
            if age or gender:
                full_symptoms = f"Patient Profile: {age} years old, {gender}.\nSymptoms reported: {symptoms}"

            print(f"[diagnoser] Analyzing symptoms via Sarvam-105B: '{full_symptoms[:60]}...'")
            assessment = diagnose_symptoms(full_symptoms, language=lang)
            self._send_json({"assessment": assessment})
            return

        # ── ENDPOINT: DIAGNOSE SYMPTOMS (VOICE VIA SAARAS V4) ───────────────
        if self.path == "/api/diagnose-voice":
            audio_b64 = req_data.get("audio_base64", "")
            lang = req_data.get("language", "Hindi")
            age = req_data.get("age", "")
            gender = req_data.get("gender", "")
            raw_audio = base64.b64decode(audio_b64)

            print(f"[diagnoser] Transcribing voice symptoms via Saaras v4 ({len(raw_audio)} bytes)...")
            user_transcript = transcribe_audio_bytes(raw_audio, language=lang)
            print(f"[diagnoser] Transcribed problem: '{user_transcript}'")

            full_symptoms = user_transcript
            if age or gender:
                full_symptoms = f"Patient Profile: {age} years old, {gender}.\nSymptoms reported: {user_transcript}"

            assessment = diagnose_symptoms(full_symptoms, language=lang)
            self._send_json({
                "user_transcript": user_transcript,
                "assessment": assessment
            })
            return

        # ── ENDPOINT: DIAGNOSE FOLLOW-UP CONSULTATION CHAT (TEXT) ───────────
        if self.path == "/api/diagnose-followup":
            user_text = req_data.get("user_text", "")
            history = req_data.get("history", [])
            patient_context = req_data.get("patient_context", {})
            lang = req_data.get("language", "Hindi")

            print(f"[diagnoser-chat] Follow-up question: '{user_text}'")
            res = diagnose_followup(
                history=history,
                user_message=user_text,
                patient_context=patient_context,
                language=lang
            )
            self._send_json(res)
            return

        # ── ENDPOINT: DIAGNOSE FOLLOW-UP CONSULTATION CHAT (VOICE) ──────────
        if self.path == "/api/diagnose-followup-voice":
            audio_b64 = req_data.get("audio_base64", "")
            history = req_data.get("history", [])
            patient_context = req_data.get("patient_context", {})
            lang = req_data.get("language", "Hindi")
            raw_audio = base64.b64decode(audio_b64)

            print(f"[diagnoser-chat] Transcribing follow-up voice ({len(raw_audio)} bytes)...")
            user_transcript = transcribe_audio_bytes(raw_audio, language=lang)
            print(f"[diagnoser-chat] Transcribed follow-up: '{user_transcript}'")

            res = diagnose_followup(
                history=history,
                user_message=user_transcript,
                patient_context=patient_context,
                language=lang
            )
            res["user_transcript"] = user_transcript
            self._send_json(res)
            return

        # ── ENDPOINT: SPEAK REMINDER (BULBUL V3) ────────────────────────────
        if self.path == "/api/speak-reminder":
            text = req_data.get("text", "दवाई का समय हो गया है।")
            lang = req_data.get("language", "Hindi")
            audio_bytes = speak_turn(text, language=lang, speaker="ritu", pace=0.92)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({"audio_base64": b64})
            return

        # ── ENDPOINT: PARSE & UPLOAD PRESCRIPTION (SARVAM VISION + 105B) ─────
        if self.path == "/api/upload-prescription":
            presc_text = req_data.get("prescription_text", "")
            file_b64 = req_data.get("file_base64", "")
            file_name = req_data.get("file_name", "")
            patient_name = req_data.get("patient_name", "Patient")
            age = req_data.get("age", "25")
            gender = req_data.get("gender", "Male")
            lang = req_data.get("language", "Hindi")

            if file_b64:
                file_bytes = base64.b64decode(file_b64)
                print(f"[prescription] Processing uploaded file: {file_name} ({len(file_bytes)} bytes)")
                timetable = process_uploaded_file(
                    file_bytes=file_bytes,
                    filename=file_name or "prescription.pdf",
                    language=lang,
                    patient_name=patient_name,
                    age=age,
                    gender=gender
                )
            else:
                print(f"[prescription] Parsing prescription text for {patient_name}...")
                timetable = parse_prescription_text(
                    prescription_text=presc_text,
                    language=lang,
                    patient_name=patient_name,
                    age=age,
                    gender=gender
                )

            self._send_json({"status": "success", "timetable": timetable})
            return

        # ── ENDPOINT: UPDATE PATIENT PROFILE ────────────────────────────────
        if self.path == "/api/update-patient":
            patient_name = req_data.get("patient_name", "Patient")
            age = req_data.get("age", "")
            gender = req_data.get("gender", "")
            lang = req_data.get("language", "Hindi")

            patient_id = f"PAT-{abs(hash(patient_name)) % 100000:05d}"
            updated = {
                "patient_id": patient_id,
                "name": patient_name,
                "age": age,
                "gender": gender,
                "phone": "+91-98765-43210",
                "language": lang,
                "discharge_date": "Today",
                "diagnoses": ["General Outpatient Care"],
                "medications": [],
                "follow_ups": [],
                "checklist": {}
            }
            save_patient(updated)
            self._send_json({"status": "success", "patient": updated})
            return

        # ── ENDPOINT: START COMPANION OUTBOUND CALL ─────────────────────────
        if self.path == "/api/start-call":
            p_name = req_data.get("patient_name", "Patient")
            lang = req_data.get("language", "Hindi")
            meds = req_data.get("medications", ["Prescribed Medicines"])
            doc_name = req_data.get("doctor_name", "")
            hosp_name = req_data.get("hospital_name", "")
            diag = req_data.get("diagnosis", "")

            patient = {
                "patient_id": f"PAT-{abs(hash(p_name)) % 100000:05d}",
                "name": p_name,
                "language": lang,
                "medications": meds,
                "doctor_name": doc_name,
                "hospital_name": hosp_name,
                "diagnoses": [diag] if diag else []
            }
            history = []
            agent_text = generate_agent_reply(patient, history)
            history.append({"role": "assistant", "content": agent_text})

            audio_bytes = speak_turn(agent_text, language=lang, pace=0.95)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({"agent_text": agent_text, "audio_base64": b64, "history": history})
            return

        # ── ENDPOINT: CHAT TURN (COMPANION BOT) ─────────────────────────────
        if self.path == "/api/chat-turn":
            p_name = req_data.get("patient_name", "Patient")
            lang = req_data.get("language", "Hindi")
            meds = req_data.get("medications", ["Prescribed Medicines"])
            doc_name = req_data.get("doctor_name", "")
            hosp_name = req_data.get("hospital_name", "")
            diag = req_data.get("diagnosis", "")

            patient = {
                "patient_id": f"PAT-{abs(hash(p_name)) % 100000:05d}",
                "name": p_name,
                "language": lang,
                "medications": meds,
                "doctor_name": doc_name,
                "hospital_name": hosp_name,
                "diagnoses": [diag] if diag else []
            }
            history = req_data.get("history", [])
            user_text = req_data.get("user_text", "")
            if user_text:
                history.append({"role": "user", "content": user_text})

            agent_text = generate_agent_reply(patient, history)
            history.append({"role": "assistant", "content": agent_text})

            audio_bytes = speak_turn(agent_text, language=lang, pace=0.95)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({"agent_text": agent_text, "audio_base64": b64, "history": history})
            return

        # ── ENDPOINT: VOICE TURN (COMPANION BOT MIC RECORDING) ──────────────
        if self.path == "/api/voice-turn":
            p_name = req_data.get("patient_name", "Patient")
            lang = req_data.get("language", "Hindi")
            meds = req_data.get("medications", ["Prescribed Medicines"])
            doc_name = req_data.get("doctor_name", "")
            hosp_name = req_data.get("hospital_name", "")
            diag = req_data.get("diagnosis", "")

            patient = {
                "patient_id": f"PAT-{abs(hash(p_name)) % 100000:05d}",
                "name": p_name,
                "language": lang,
                "medications": meds,
                "doctor_name": doc_name,
                "hospital_name": hosp_name,
                "diagnoses": [diag] if diag else []
            }
            history = req_data.get("history", [])
            audio_b64 = req_data.get("audio_base64", "")
            raw_audio = base64.b64decode(audio_b64)

            user_transcript = transcribe_audio_bytes(raw_audio, language=lang)
            history.append({"role": "user", "content": user_transcript})

            agent_text = generate_agent_reply(patient, history)
            history.append({"role": "assistant", "content": agent_text})

            audio_bytes = speak_turn(agent_text, language=lang, pace=0.95)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({
                "user_transcript": user_transcript,
                "agent_text": agent_text,
                "audio_base64": b64,
                "history": history
            })
            return

        # ── ENDPOINT: END CALL & CLINICAL EVALUATION ─────────────────────────
        if self.path == "/api/end-call":
            p_name = req_data.get("patient_name", "Patient")
            lang = req_data.get("language", "Hindi")
            meds = req_data.get("medications", ["Prescribed Medicines"])
            doc_name = req_data.get("doctor_name", "")
            hosp_name = req_data.get("hospital_name", "")
            diag = req_data.get("diagnosis", "")

            patient = {
                "patient_id": f"PAT-{abs(hash(p_name)) % 100000:05d}",
                "name": p_name,
                "language": lang,
                "phone": "+91-98765-43210",
                "medications": meds,
                "doctor_name": doc_name,
                "hospital_name": hosp_name,
                "diagnoses": [diag] if diag else []
            }
            history = req_data.get("history", [])

            evaluation = evaluate_call_outcome(patient, history)
            flags = evaluation.get("flags", [])
            escalation = None
            esc_html = ""

            if flags:
                escalation = create_escalation_alert(
                    patient=patient,
                    flags=flags,
                    patient_notes=evaluation.get("patient_summary_notes", ""),
                    adherence_issues=evaluation.get("missed_medications", []),
                    symptoms_reported=evaluation.get("symptoms_reported", []),
                )
                esc_html = f"""
                <div class="escalation-box">
                  <div class="alert-header">
                    <div class="alert-title">
                      <span class="pulse-dot"></span>
                      CRITICAL CLINICAL ESCALATION ALERT — {escalation.get('alert_id')}
                    </div>
                    <span class="badge" style="background: rgba(239, 68, 68, 0.3); color: #fca5a5;">PRIORITY: {escalation.get('priority', 'CRITICAL')}</span>
                  </div>
                  <div class="alert-body">
                    <div><strong>Patient:</strong> {escalation.get('patient_name')} ({escalation.get('phone')}) | <strong>Language:</strong> {escalation.get('language')}</div>
                    <div style="margin-top: 6px;"><strong>Flags:</strong> {' '.join([f'<span class="tag-flag">{f}</span>' for f in escalation.get('flags', [])])}</div>
                    <div style="margin-top: 6px;"><strong>Missed Prescriptions:</strong> {', '.join(escalation.get('missed_medications', []))}</div>
                    <div style="background: rgba(0,0,0,0.3); padding: 12px 14px; border-radius: 8px; margin: 10px 0; border-left: 3px solid var(--red);">
                      <strong>Patient Telephony Report (Mayura English Translation):</strong><br>
                      {escalation.get('patient_voice_notes_en', 'No translation available')}
                    </div>
                    <div style="background: rgba(239, 68, 68, 0.2); color: #fecaca; padding: 10px 14px; border-radius: 8px; font-weight: 600; margin-top: 10px;">
                      ⚡ Action Required: {escalation.get('recommended_action', 'Contact patient immediately')}
                    </div>
                  </div>
                </div>
                """

            log_id = log_checkin(
                patient_id=patient.get("patient_id", "UNKNOWN"),
                transcript=history,
                adherence=evaluation.get("adherence", {}),
                symptoms=evaluation.get("symptoms_reported", []),
                flags=flags,
                escalated=bool(flags),
                escalation_details=escalation,
            )
            self._send_json({"evaluation": evaluation, "escalation_html": esc_html, "log_id": log_id})
            return

        self.send_error(404, "Endpoint not found")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/audio/patient_explanation.wav":
            target = MOCK_DIR / "patient_explanation.wav"
            if target.exists():
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(target.stat().st_size))
                self.end_headers()
                self.wfile.write(target.read_bytes())
                return
            else:
                self.send_error(404, "Audio file not found")
                return

        if parsed.path == "/" or parsed.path == "/index.html":
            esc_html = """
            <div style="background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 14px 20px; margin-bottom: 24px; display: flex; align-items: center; gap: 12px; color: #94a3b8; font-size: 13.5px;">
              <span style="color: #34d399; font-size: 16px;">✔</span>
              Clinical Monitoring Active. Emergency escalations will appear here if red flags are detected.
            </div>
            """

            html = HTML_CONTENT.replace("__ESCALATION_BLOCK__", esc_html)
            encoded = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        self.send_error(404, "File Not Found")

    def _send_json(self, data: dict):
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def start():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"\n[dashboard] Care Coordinator Interactive Dashboard running on port {PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] Shutting down.", flush=True)


if __name__ == "__main__":
    start()
