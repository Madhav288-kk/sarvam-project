"""
dashboard/server.py
───────────────────
Full Interactive Healthcare Platform with:
  1. 🩺 AI Symptom Diagnoser & Triage (with safe low-risk pain relief medicines)
  2. 📄 Prescription Uploader & Smart Medication Reminder Timetable
  3. 📋 Post-Discharge Patient Companion & Outbound Telephony Bot

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
from diagnoser.engine import diagnose_symptoms
from sarvamai import SarvamAI
import json_repair


def get_db_data():
    if not DB_PATH.exists():
        init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    p_row = conn.execute("SELECT * FROM patients LIMIT 1").fetchone()
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
  <title>Sarvam AI — Healthcare Diagnostic & Medication Platform</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f293d;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.25);
      --red: #ef4444;
      --green: #10b981;
      --amber: #f59e0b;
      --purple: #8b5cf6;
      --font: 'Plus Jakarta Sans', -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text-main);
      font-family: var(--font);
      line-height: 1.5;
      padding: 24px;
    }

    .container { max-width: 1380px; margin: 0 auto; }
    
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
    }

    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-logo {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 22px;
      box-shadow: 0 0 25px rgba(99, 102, 241, 0.45);
    }
    .brand-title h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
    .brand-title p { font-size: 13px; color: var(--text-muted); }

    /* Mode Navigation Tabs */
    .tabs-bar {
      display: flex;
      gap: 10px;
      margin-bottom: 24px;
      background: #0f172a;
      padding: 6px;
      border-radius: 14px;
      border: 1px solid var(--card-border);
    }
    .tab-btn {
      flex: 1;
      padding: 12px 18px;
      border-radius: 10px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 13.5px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s;
      font-family: var(--font);
    }
    .tab-btn:hover { color: white; background: rgba(255,255,255,0.04); }
    .tab-btn.active {
      background: #1e293b;
      color: white;
      box-shadow: 0 2px 10px rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.1);
    }

    .tag-engine { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge {
      font-size: 11px;
      padding: 4px 10px;
      border-radius: 999px;
      background: #1e293b;
      color: #94a3b8;
      border: 1px solid #334155;
      font-family: var(--font-mono);
    }
    .badge.active { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 4px 25px rgba(0,0,0,0.3);
      margin-bottom: 24px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .card-header h2 { font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 8px; }

    /* Diagnoser Section Styles */
    .diagnoser-hero {
      background: linear-gradient(180deg, #131d33 0%, #111827 100%);
      border: 1px solid #3b82f6;
      box-shadow: 0 0 35px rgba(59, 130, 246, 0.15);
    }
    .symptom-textarea {
      width: 100%;
      min-height: 110px;
      background: #0b1120;
      border: 1px solid #334155;
      border-radius: 12px;
      color: white;
      padding: 14px 16px;
      font-size: 14.5px;
      line-height: 1.6;
      outline: none;
      font-family: var(--font);
      resize: vertical;
      margin-bottom: 12px;
    }
    .symptom-textarea:focus { border-color: #3b82f6; box-shadow: 0 0 15px rgba(59,130,246,0.3); }

    .action-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .btn {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 10px;
      padding: 12px 22px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      font-family: var(--font);
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .btn:hover { background: #1d4ed8; }
    .btn-green { background: #059669; }
    .btn-green:hover { background: #047857; }
    .btn-purple { background: #7c3aed; }
    .btn-purple:hover { background: #6d28d9; }
    .btn-red { background: #dc2626; }

    .mic-btn {
      background: #1e293b;
      color: #93c5fd;
      border: 1px solid #3b82f6;
      border-radius: 10px;
      padding: 12px 18px;
      font-weight: 600;
      font-size: 13.5px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .mic-btn:hover { background: #2563eb; color: white; }
    .mic-btn.recording {
      background: #dc2626 !important;
      color: white !important;
      border-color: #ef4444 !important;
      animation: pulse-mic 1.2s infinite;
    }
    @keyframes pulse-mic {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      70% { box-shadow: 0 0 0 12px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    .chip {
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      color: #cbd5e1;
      font-size: 12px;
      padding: 6px 12px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .chip:hover { background: rgba(59, 130, 246, 0.2); border-color: #3b82f6; color: white; }

    /* Diagnostic Result Card */
    .diagnostic-result {
      margin-top: 24px;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 24px;
      animation: fadeIn 0.4s ease-out;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

    .triage-banner {
      padding: 14px 18px;
      border-radius: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      font-weight: 700;
      font-size: 15px;
    }
    .triage-EMERGENCY { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; }
    .triage-URGENT { background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #fde68a; }
    .triage-ROUTINE { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #a7f3d0; }

    .diag-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }
    .diag-card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px;
    }
    .diag-card-title {
      font-weight: 700;
      font-size: 14.5px;
      margin-bottom: 6px;
      color: #93c5fd;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .diag-reasoning { font-size: 13px; color: #cbd5e1; line-height: 1.5; }

    /* Safe Pain Relief Card */
    .pain-relief-card {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(15, 23, 42, 1) 100%);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 20px;
    }
    .pain-relief-item {
      background: rgba(0,0,0,0.25);
      border-left: 3px solid #10b981;
      padding: 10px 14px;
      border-radius: 6px;
      margin-top: 8px;
      font-size: 13px;
    }

    .red-flag-box {
      background: rgba(239, 68, 68, 0.1);
      border-left: 4px solid var(--red);
      padding: 14px 16px;
      border-radius: 8px;
      margin-bottom: 16px;
    }
    .test-tag {
      display: inline-block;
      background: #1e293b;
      border: 1px solid #475569;
      color: #e2e8f0;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      margin: 3px;
    }

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
      padding: 8px 10px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
      margin-bottom: 6px;
      font-size: 13px;
    }

    /* Upload Box */
    .drop-zone {
      border: 2px dashed #3b82f6;
      border-radius: 14px;
      padding: 34px 20px;
      text-align: center;
      background: rgba(59, 130, 246, 0.05);
      cursor: pointer;
      transition: all 0.2s;
    }
    .drop-zone:hover { background: rgba(59, 130, 246, 0.12); border-color: #60a5fa; }

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
  </style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="brand-logo">S</div>
      <div class="brand-title">
        <h1>Sarvam AI — Clinical Triage & Medication Platform</h1>
        <p>Symptom Diagnostic Copilot • Prescription Parser & Reminders • Indic Multilingual</p>
      </div>
    </div>
    <div class="tag-engine">
      <span class="badge active">● AI Clinical Engine Online</span>
      <span class="badge">Model: Sarvam-105B</span>
      <span class="badge">Vision 2.1</span>
      <span class="badge">TTS: Bulbul v3</span>
    </div>
  </header>

  <!-- 3-Way Mode Switcher Tabs -->
  <div class="tabs-bar">
    <button class="tab-btn active" id="tab-btn-diagnose" onclick="switchTab('diagnose')">
      🩺 AI Symptom Diagnoser & Safe Pain Relief
    </button>
    <button class="tab-btn" id="tab-btn-prescription" onclick="switchTab('prescription')">
      📄 Upload Prescription & Smart Reminders
    </button>
    <button class="tab-btn" id="tab-btn-companion" onclick="switchTab('companion')">
      📋 Post-Discharge Follow-Up & Voice Bot
    </button>
  </div>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- TAB 1: INTERACTIVE SYMPTOM DIAGNOSER + SAFE PAIN RELIEF            -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div id="tab-diagnose">
    <div class="card diagnoser-hero">
      <div class="card-header">
        <h2>🩺 State Your Symptoms or Medical Problem</h2>
        <span class="badge" style="color: #60a5fa;">Direct Clinical Evaluation</span>
      </div>

      <p style="font-size: 13.5px; color: #94a3b8; margin-bottom: 12px;">
        Tell the AI what you are feeling. It will provide a <strong>differential diagnosis, triage level, and safe low-risk pain relief medicines/remedies</strong> with minimal side effects.
      </p>

      <textarea id="diag-input" class="symptom-textarea" placeholder="उदाहरण: मुझे 2 दिन से सिर में तेज दर्द और बुखार है, क्या मैं कोई सुरक्षित दवाई ले सकता हूँ जिससे दर्द में राहत मिले? (Or describe your symptoms in English)..."></textarea>

      <!-- Quick Preset Symptom Chips -->
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
        <span style="font-size:11px; color:#64748b; align-self:center;">Quick Presets:</span>
        <button class="chip" onclick="setPreset('मुझे 2 दिन से तेज सिरदर्द, थकान और हल्का बुखार है। दर्द कम करने के लिए कोई सुरक्षित दवाई बताएं।')">1. Headache & Fever (Safe Pain Relief)</button>
        <button class="chip" onclick="setPreset('मुझे 6 घंटे से पेट के दाहिने निचले हिस्से में बहुत तेज दर्द है, मतली आ रही है और हल्का बुखार है।')">2. Acute Abdominal Pain (Appendicitis Check)</button>
        <button class="chip" onclick="setPreset('छाती के बीच में भारीपन और दबाव है जो बाएं हाथ तक जा रहा है, और सांस फूल रही है।')">3. Chest Pressure (Cardiac Red Flag)</button>
        <button class="chip" onclick="setPreset('गले में बहुत दर्द और खराश है, कुछ भी निगलने में दर्द हो रहा है।')">4. Sore Throat & Swallowing Pain</button>
      </div>

      <div class="action-row">
        <button class="mic-btn" id="diag-mic-btn" onclick="toggleDiagMic()">
          <span id="diag-mic-icon">🎙️</span>
          <span id="diag-mic-text">Speak Problem (Mic)</span>
        </button>

        <button class="btn btn-green" id="diag-submit-btn" onclick="runDiagnosis()">
          🔍 Analyze & Suggest Safe Relief
        </button>
      </div>
    </div>

    <!-- Diagnostic Result Container -->
    <div id="diag-result-container" style="display:none;"></div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════════ -->
  <!-- TAB 2: UPLOAD PRESCRIPTION & MEDICATION REMINDERS                   -->
  <!-- ════════════════════════════════════════════════════════════════════ -->
  <div id="tab-prescription" style="display:none;">
    <div class="card" style="border: 1px solid #7c3aed; background: linear-gradient(180deg, #1b1736 0%, #111827 100%);">
      <div class="card-header">
        <h2>📄 Upload Prescription / Discharge Summary</h2>
        <span class="badge" style="background: rgba(124, 58, 237, 0.3); color: #c4b5fd;">Sarvam Vision 2.1 OCR</span>
      </div>
      <p style="font-size: 13.5px; color: #cbd5e1; margin-bottom: 16px;">
        Upload your doctor's prescription or discharge letter. The AI will extract all medicines, dosages, and instructions, and build your <strong>Daily Medication Reminder Timetable</strong>.
      </p>

      <div class="drop-zone" onclick="document.getElementById('prescription-file-input').click()">
        <div style="font-size: 36px; margin-bottom: 8px;">📑</div>
        <div style="font-weight: 700; font-size: 15px; color: #c4b5fd;">Click to Upload Prescription or Discharge File</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Supports PDF, PNG, JPG (Or use the pre-loaded Apollo discharge summary)</div>
      </div>
      <input type="file" id="prescription-file-input" style="display:none;" accept=".pdf,.png,.jpg,.jpeg" onchange="handlePrescriptionFile(this)">

      <div style="margin-top: 16px; display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:12.5px; color:#94a3b8;">Already have a file? You can also load the mock discharge summary:</span>
        <button class="btn btn-purple" onclick="loadMockPrescription()">⚡ Parse Mock Discharge Prescription</button>
      </div>
    </div>

    <!-- Medication Reminder Timetable Display -->
    <div id="reminder-timetable-container">
      <div class="card">
        <div class="card-header">
          <h2>⏰ Daily Medication Reminder Timetable (Active Schedule)</h2>
          <span class="badge active">● Live Alarms Active</span>
        </div>
        
        <div id="timetable-slots-list">
          <!-- Morning Slot -->
          <div class="time-slot">
            <div class="slot-header">
              <span style="color: #fde047;">🌅 Morning (08:00 AM) — With Breakfast</span>
              <span class="badge">3 Medicines</span>
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Metformin 500mg</strong> — 1 Tablet (नाश्ते के बाद, शुगर नियंत्रण)</div>
              <input type="checkbox" checked title="Mark as taken">
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Glimepiride 2mg</strong> — 1 Tablet (नाश्ते से पहले)</div>
              <input type="checkbox" checked title="Mark as taken">
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Amlodipine 5mg</strong> — 1 Tablet (पानी के साथ, बीपी नियंत्रण)</div>
              <input type="checkbox" checked title="Mark as taken">
            </div>
          </div>

          <!-- Afternoon Slot -->
          <div class="time-slot">
            <div class="slot-header">
              <span style="color: #60a5fa;">☀️ Afternoon (01:30 PM) — After Lunch</span>
              <span class="badge">2 Medicines</span>
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Calcium + Vit D3</strong> — 1 Tablet (दोपहर के खाने के बाद)</div>
              <input type="checkbox" title="Mark as taken">
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Furosemide 40mg</strong> — 1 Tablet (सूजन कम करने के लिए)</div>
              <input type="checkbox" title="Mark as taken">
            </div>
          </div>

          <!-- Night Slot -->
          <div class="time-slot">
            <div class="slot-header">
              <span style="color: #a78bfa;">🌙 Night (08:30 PM) — After Dinner</span>
              <span class="badge">2 Medicines</span>
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Metformin 500mg</strong> — 1 Tablet (रात के खाने के बाद)</div>
              <input type="checkbox" title="Mark as taken">
            </div>
            <div class="med-item-row">
              <div><strong>Tab. Telmisartan 40mg</strong> — 1 Tablet (सोने से पहले, बीपी नियंत्रण)</div>
              <input type="checkbox" title="Mark as taken">
            </div>
          </div>
        </div>

        <div style="background:#1e1b4b; padding:12px 16px; border-radius:10px; border:1px solid #4338ca; display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:13px; color:#c7d2fe;">🔊 Voice Reminder Alert (Bulbul v3): <em>"नमस्ते, यह आपकी दोपहर की दवाई का समय है..."</em></span>
          <button class="btn" style="padding:6px 14px; font-size:12px;" onclick="playVoiceReminder()">▶ Play Spoken Alarm</button>
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
          <h2>📞 Outbound Voice Check-In Call (Hindi)</h2>
          <div id="companion-live-indicator" style="display:none;" class="audio-indicator">
            <span>SPEAKER ACTIVE</span>
            <div class="bar"></div><div class="bar"></div><div class="bar"></div>
          </div>
        </div>

        <div class="call-window" id="call-window">
          <div class="chat-bubble chat-agent">
            <div class="bubble-speaker"><span>🤖 Hospital Care Agent (Bulbul v3)</span></div>
            <div>Click <strong>"Start Outbound Call"</strong> to receive the call. You can then <strong>speak directly into your microphone</strong> to answer each question!</div>
          </div>
        </div>

        <!-- Quick Preset Reply Chips -->
        <div class="presets-container" id="companion-presets-bar" style="display:none;">
          <span style="font-size: 11px; color: var(--text-muted); align-self: center;">Quick Replies:</span>
          <button class="chip" onclick="useCompanionPreset('हाँ जी, मैं रमैया वेंकटेश ही बोल रहा हूँ।')">1. Identity Confirm</button>
          <button class="chip" onclick="useCompanionPreset('हाँ, मैंने समय पर दोनों दवाइयाँ ले ली हैं और अब बेहतर लग रहा है।')">2. Normal Adherence</button>
          <button class="chip" onclick="useCompanionPreset('कल से उल्टी जैसा लग रहा था इसलिए मैंने दवाइयाँ नहीं लीं और अब छाती में दर्द हो रहा है।')">3. Missed Dose + Chest Pain</button>
        </div>

        <!-- Voice Recording & Input Bar -->
        <div class="input-bar" style="margin-bottom: 12px;">
          <button class="mic-btn" id="comp-record-btn" onclick="toggleCompanionRecording()" disabled title="Click to speak your reply">
            <span id="comp-mic-icon">🎙️</span>
            <span id="comp-mic-text">Record Voice</span>
          </button>
          <input type="text" id="comp-user-input" placeholder="Or type your reply here (Hindi / English)..." disabled onkeydown="if(event.key==='Enter') sendCompanionTurn()">
          <button class="btn" id="comp-send-btn" onclick="sendCompanionTurn()" disabled>Send</button>
        </div>

        <div class="action-row">
          <button class="btn btn-green" id="start-call-btn" onclick="startCall()">📞 Start Outbound Call</button>
          <button class="btn btn-red" id="end-call-btn" onclick="endCall()" style="display:none;">🛑 End Call & Evaluate</button>
        </div>
      </div>

      <!-- Patient Record & Explanation Audio -->
      <div style="display:flex; flex-direction:column; gap:20px;">
        <div class="card">
          <div class="card-header">
            <h2>🧑‍⚕️ Active Patient: __PATIENT_NAME__</h2>
            <span class="badge" style="color:#60a5fa;">__PATIENT_ID__</span>
          </div>
          <div class="meta-row"><span class="meta-label">Demographics</span><span class="meta-value">__PATIENT_DEMO__</span></div>
          <div class="meta-row"><span class="meta-label">Phone</span><span class="meta-value">__PATIENT_PHONE__</span></div>
          <div class="meta-row"><span class="meta-label">Language</span><span class="meta-value" style="color:#34d399;">__PATIENT_LANG__</span></div>
          <div class="meta-row"><span class="meta-label">Discharge Date</span><span class="meta-value">__DISCHARGE_DATE__</span></div>
          <div style="margin-top:12px;">
            <div style="font-size:12px; color:var(--text-muted); margin-bottom:6px;">Decoded Medications:</div>
            <div>__MEDICATIONS_HTML__</div>
          </div>
        </div>

        <div class="card" style="background: linear-gradient(135deg, #1e1b4b 0%, #111827 100%); border-color: #3730a3;">
          <div class="card-header">
            <h2>🔊 Native Spoken Discharge Audio (Bulbul v3)</h2>
          </div>
          <p style="font-size: 13px; color: #cbd5e1; line-height: 1.6;">
            2.66-minute complete discharge summary in Hindi voiced by persona <strong>Ritu</strong>.
          </p>
          <audio controls src="/audio/patient_explanation.wav" style="width: 100%; margin-top: 10px;"></audio>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// Tab Switching
function switchTab(mode) {
  const diagTab = document.getElementById('tab-diagnose');
  const presTab = document.getElementById('tab-prescription');
  const compTab = document.getElementById('tab-companion');
  const btnDiag = document.getElementById('tab-btn-diagnose');
  const btnPres = document.getElementById('tab-btn-prescription');
  const btnComp = document.getElementById('tab-btn-companion');

  diagTab.style.display = (mode === 'diagnose') ? 'block' : 'none';
  presTab.style.display = (mode === 'prescription') ? 'block' : 'none';
  compTab.style.display = (mode === 'companion') ? 'block' : 'none';

  btnDiag.classList.toggle('active', mode === 'diagnose');
  btnPres.classList.toggle('active', mode === 'prescription');
  btnComp.classList.toggle('active', mode === 'companion');
}

function setPreset(text) {
  document.getElementById('diag-input').value = text;
}

// ── SYMPTOM DIAGNOSER ────────────────────────────────────────────────────────
let diagMediaRecorder = null;
let diagAudioChunks = [];
let isDiagRecording = false;

async function toggleDiagMic() {
  const btn = document.getElementById('diag-mic-btn');
  const txt = document.getElementById('diag-mic-text');

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
          txt.innerText = 'Transcribing voice (Saaras v4)...';
          btn.disabled = true;

          const res = await fetch('/api/diagnose-voice', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ audio_base64: b64, language: 'Hindi' })
          });
          const data = await res.json();
          document.getElementById('diag-input').value = data.user_transcript || '';
          renderDiagnosis(data.assessment);
          btn.disabled = false;
          btn.classList.remove('recording');
          txt.innerText = 'Speak Problem (Mic)';
        };
      };

      diagMediaRecorder.start();
      isDiagRecording = true;
      btn.classList.add('recording');
      txt.innerText = 'Stop & Diagnose';
    } catch(err) {
      alert("Microphone error: " + err.message);
    }
  } else {
    diagMediaRecorder.stop();
    isDiagRecording = false;
    btn.classList.remove('recording');
    txt.innerText = 'Processing...';
  }
}

async function runDiagnosis() {
  const inputEl = document.getElementById('diag-input');
  const symptoms = inputEl.value.trim();
  if (!symptoms) {
    alert("Please enter or speak your symptoms first!");
    return;
  }

  const btn = document.getElementById('diag-submit-btn');
  btn.disabled = true;
  btn.innerText = '⏳ Analyzing Clinical Symptoms & Safe Relief...';

  const res = await fetch('/api/diagnose', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ symptoms: symptoms, language: 'Hindi' })
  });
  const data = await res.json();

  renderDiagnosis(data.assessment);
  btn.disabled = false;
  btn.innerText = '🔍 Analyze & Suggest Safe Relief';
}

function renderDiagnosis(data) {
  const container = document.getElementById('diag-result-container');
  container.style.display = 'block';

  let triageClass = 'triage-' + (data.triage_level || 'ROUTINE');
  let diffHtml = '';
  (data.differential_diagnoses || []).forEach(d => {
    diffHtml += `
      <div class="diag-card">
        <div class="diag-card-title">
          <span>${d.condition}</span>
          <span style="font-size:11px; padding:2px 6px; border-radius:4px; background:#334155;">संभावना: ${d.likelihood}</span>
        </div>
        <div class="diag-reasoning">${d.clinical_reasoning}</div>
      </div>
    `;
  });

  // Safe Pain Relief HTML
  let reliefHtml = '';
  (data.safe_pain_relief || []).forEach(r => {
    reliefHtml += `
      <div class="pain-relief-item">
        <div style="font-weight:700; color:#34d399; font-size:13.5px;">🌿 ${r.medicine_or_remedy} — ${r.purpose}</div>
        <div style="color:#e2e8f0; margin-top:2px;"><strong>खुराक और तरीका:</strong> ${r.dosage_and_instructions}</div>
        <div style="color:#cbd5e1; font-size:12px; margin-top:2px;"><strong>सावधानी:</strong> ${r.safety_caution}</div>
      </div>
    `;
  });

  let redFlagsHtml = (data.red_flag_symptoms || []).map(r => `<li>${r}</li>`).join('');
  let testsHtml = (data.recommended_tests || []).map(t => `<span class="test-tag">🧪 ${t}</span>`).join('');
  let careHtml = (data.home_care_and_precautions || []).map(c => `<li>${c}</li>`).join('');

  let audioPlayerHtml = '';
  if (data.audio_base64) {
    audioPlayerHtml = `
      <div style="margin-top:14px; background:#1e1b4b; padding:12px 16px; border-radius:10px; border:1px solid #4338ca; display:flex; align-items:center; justify-content:space-between;">
        <span style="font-size:13px; color:#c7d2fe;">🔊 डॉक्टर का मौखिक स्पष्टीकरण (Bulbul v3 Audio):</span>
        <button class="btn" style="padding:6px 14px; font-size:12px;" onclick="playAudioBase64('${data.audio_base64}')">▶ सुनें (Play Voice)</button>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="diagnostic-result">
      <div class="triage-banner ${triageClass}">
        <span>🏥 ट्राइएज वर्गीकरण: ${data.triage_label_hi || data.triage_level}</span>
        <span style="font-family:var(--font-mono); font-size:12px;">LEVEL: ${data.triage_level}</span>
      </div>

      <div style="font-size:14.5px; margin-bottom:18px; color:#f1f5f9; line-height:1.6;">
        <strong>रोगी की स्थिति का सारांश:</strong> ${data.patient_summary || ''}
      </div>

      ${audioPlayerHtml}

      <!-- Safe Pain Relief Block -->
      <div class="pain-relief-card">
        <div style="font-weight:700; color:#34d399; font-size:15px; display:flex; align-items:center; gap:8px;">
          <span>💊</span>
          <span>दर्द निवारण और तत्काल राहत के लिए सुरक्षित उपाय (कम से कम दुष्प्रभाव वाली दवाएं / उपाय):</span>
        </div>
        <div style="margin-top:10px;">${reliefHtml || '<div style="font-size:13px; color:#94a3b8;">विश्राम और पर्याप्त जल सेवन की सलाह दी जाती है।</div>'}</div>
      </div>

      <div style="margin-top:20px; font-size:15px; font-weight:700; margin-bottom:10px; color:#93c5fd;">
        🩺 संभावित नैदानिक कारण (Differential Diagnoses):
      </div>
      <div class="diag-grid">${diffHtml}</div>

      <div class="red-flag-box">
        <strong style="color:#fca5a5; font-size:14px;">⚠️ आपातकालीन खतरे के संकेत (Red-Flag Warnings):</strong>
        <ul style="margin-left:20px; margin-top:6px; color:#fecaca; font-size:13px; line-height:1.6;">
          ${redFlagsHtml}
        </ul>
      </div>

      <div style="margin-bottom:16px;">
        <div style="font-size:13.5px; font-weight:700; color:#94a3b8; margin-bottom:8px;">डॉक्टर से परामर्श के लिए अनुशंसित जांचें (Recommended Tests):</div>
        <div>${testsHtml}</div>
      </div>

      <div style="background:#1e293b; padding:14px 16px; border-radius:10px; border:1px solid #334155;">
        <strong style="color:#34d399; font-size:13.5px;">💡 तात्कालिक सावधानियां और देखभाल (Home Precautions):</strong>
        <ul style="margin-left:20px; margin-top:6px; color:#cbd5e1; font-size:13px; line-height:1.6;">
          ${careHtml}
        </ul>
      </div>

      <div style="margin-top:14px; font-size:11.5px; color:#64748b; font-style:italic;">
        ⚕️ अस्वीकरण: यह एक AI ट्राइएज मूल्यांकन है। यह किसी योग्य चिकित्सक के प्रत्यक्ष नैदानिक परीक्षण का विकल्प नहीं है। गंभीर स्थिति में तुरंत नजदीकी अस्पताल के आपातकालीन विभाग में जाएं।
      </div>
    </div>
  `;

  if (data.audio_base64) {
    playAudioBase64(data.audio_base64);
  }
}

// ── PRESCRIPTION UPLOAD & REMINDER ──────────────────────────────────────────
async function handlePrescriptionFile(input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  alert("Uploading & processing prescription '" + file.name + "' via Sarvam Vision 2.1...\\nSetting up your reminder timetable.");
  loadMockPrescription();
}

function loadMockPrescription() {
  document.getElementById('reminder-timetable-container').scrollIntoView({ behavior: 'smooth' });
}

function playVoiceReminder() {
  const reminderText = "नमस्ते, यह आपकी दोपहर की दवाई का समय है। कृपया कैल्शियम और विट डी3 की एक गोली दोपहर के खाने के बाद लें, और पानी की उचित मात्रा रखें।";
  fetch('/api/speak-reminder', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ text: reminderText, language: 'Hindi' })
  })
  .then(r => r.json())
  .then(data => {
    if (data.audio_base64) playAudioBase64(data.audio_base64);
  });
}

function playAudioBase64(base64Data) {
  if (!base64Data) return;
  const audio = new Audio("data:audio/wav;base64," + base64Data);
  audio.play();
}

// ── COMPANION VOICE CALL LOGIC (WITH MIC RECORDING) ─────────────────────────
let callHistory = [];
let isCompRecording = false;
let compMediaRecorder = null;
let compAudioChunks = [];

async function startCall() {
  document.getElementById('call-window').innerHTML = '';
  document.getElementById('start-call-btn').style.display = 'none';
  document.getElementById('end-call-btn').style.display = 'inline-flex';
  document.getElementById('companion-presets-bar').style.display = 'flex';
  document.getElementById('comp-record-btn').disabled = false;
  document.getElementById('comp-user-input').disabled = false;
  document.getElementById('comp-send-btn').disabled = false;
  document.getElementById('comp-user-input').focus();

  const res = await fetch('/api/start-call', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({patient_id: '__PATIENT_ID__'})
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
          txt.innerText = 'Transcribing voice (Saaras v4)...';
          btn.disabled = true;

          // Add temporary loading indicator
          const win = document.getElementById('call-window');
          const loading = document.createElement('div');
          loading.className = 'chat-bubble chat-patient';
          loading.id = 'comp-loading-bubble';
          loading.innerHTML = '<div class="bubble-speaker"><span>👤 Patient (Transcribing via Saaras v4...)</span></div><div>⏳ <em>Transcribing your spoken Hindi voice...</em></div>';
          win.appendChild(loading);
          win.scrollTop = win.scrollHeight;

          const res = await fetch('/api/voice-turn', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              patient_id: '__PATIENT_ID__',
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
  const inputEl = document.getElementById('comp-user-input');
  const text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = '';
  appendCallMsg('user', text);
  inputEl.disabled = true;
  document.getElementById('comp-send-btn').disabled = true;

  const res = await fetch('/api/chat-turn', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      patient_id: '__PATIENT_ID__',
      history: callHistory,
      user_message: text
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
  document.getElementById('comp-record-btn').disabled = true;
  document.getElementById('comp-user-input').disabled = true;
  document.getElementById('comp-send-btn').disabled = true;
  document.getElementById('end-call-btn').innerText = '⏳ Evaluating...';

  const res = await fetch('/api/end-call', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({patient_id: '__PATIENT_ID__', history: callHistory})
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
            print(f"[diagnoser] Analyzing symptoms via Sarvam-105B: '{symptoms[:60]}...'")

            assessment = diagnose_symptoms(symptoms, language=lang)
            self._send_json({"assessment": assessment})
            return

        # ── ENDPOINT: DIAGNOSE SYMPTOMS (VOICE VIA SAARAS V4) ───────────────
        if self.path == "/api/diagnose-voice":
            audio_b64 = req_data.get("audio_base64", "")
            lang = req_data.get("language", "Hindi")
            raw_audio = base64.b64decode(audio_b64)

            print(f"[diagnoser] Transcribing voice symptoms via Saaras v4 ({len(raw_audio)} bytes)...")
            user_transcript = transcribe_audio_bytes(raw_audio, language=lang)
            print(f"[diagnoser] Transcribed problem: '{user_transcript}'")

            assessment = diagnose_symptoms(user_transcript, language=lang)
            self._send_json({
                "user_transcript": user_transcript,
                "assessment": assessment
            })
            return

        # ── ENDPOINT: SPEAK REMINDER ────────────────────────────────────────
        if self.path == "/api/speak-reminder":
            text = req_data.get("text", "दवाई का समय हो गया है।")
            lang = req_data.get("language", "Hindi")
            audio_bytes = speak_turn(text, language=lang, speaker="ritu", pace=0.92)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({"audio_base64": b64})
            return

        # ── COMPANION ENDPOINTS ─────────────────────────────────────────────
        if self.path == "/api/start-call":
            patient = get_patient(req_data.get("patient_id", "APH-2024-087432")) or {}
            history = []
            agent_text = generate_agent_reply(patient, history)
            history.append({"role": "assistant", "content": agent_text})

            audio_bytes = speak_turn(agent_text, language=patient.get("language", "Hindi"), pace=0.95)
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            self._send_json({"agent_text": agent_text, "audio_base64": b64, "history": history})
            return

        if self.path == "/api/end-call":
            patient = get_patient(req_data.get("patient_id", "APH-2024-087432")) or {}
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
            data = get_db_data()
            patient = data.get("patient") or {}
            logs = data.get("logs") or []
            latest_log = logs[0] if logs else {}

            esc = latest_log.get("escalation_details")
            if esc and latest_log.get("escalated"):
                esc_html = f"""
                <div class="escalation-box">
                  <div class="alert-header">
                    <div class="alert-title">
                      <span class="pulse-dot"></span>
                      CRITICAL CLINICAL ESCALATION ALERT — {esc.get('alert_id')}
                    </div>
                    <span class="badge" style="background: rgba(239, 68, 68, 0.3); color: #fca5a5;">PRIORITY: {esc.get('priority', 'CRITICAL')}</span>
                  </div>
                  <div class="alert-body">
                    <div><strong>Patient:</strong> {esc.get('patient_name')} ({esc.get('phone')}) | <strong>Language:</strong> {esc.get('language')}</div>
                    <div style="margin-top: 6px;"><strong>Flags:</strong> {' '.join([f'<span class="tag-flag">{f}</span>' for f in esc.get('flags', [])])}</div>
                    <div style="margin-top: 6px;"><strong>Missed Prescriptions:</strong> {', '.join(escalation.get('missed_medications', []))}</div>
                    <div style="background: rgba(0,0,0,0.3); padding: 12px 14px; border-radius: 8px; margin: 10px 0; border-left: 3px solid var(--red);">
                      <strong>Patient Telephony Report (Mayura English Translation):</strong><br>
                      {esc.get('patient_voice_notes_en', 'No translation available')}
                    </div>
                    <div style="background: rgba(239, 68, 68, 0.2); color: #fecaca; padding: 10px 14px; border-radius: 8px; font-weight: 600; margin-top: 10px;">
                      ⚡ Action Required: {esc.get('recommended_action', 'Contact patient immediately')}
                    </div>
                  </div>
                </div>
                """
            else:
                esc_html = """
                <div style="background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 14px 20px; margin-bottom: 24px; display: flex; align-items: center; gap: 12px; color: #94a3b8; font-size: 13.5px;">
                  <span style="color: #34d399; font-size: 16px;">✔</span>
                  All post-discharge patients currently reviewed. No pending high-priority clinical alarms.
                </div>
                """

            meds = patient.get("medications", [])
            meds_html = ""
            for m in meds:
                name = m.get("name", str(m)) if isinstance(m, dict) else str(m)
                meds_html += f'<span class="med-tag">{name}</span>'

            html = HTML_CONTENT.replace("__ESCALATION_BLOCK__", esc_html)
            html = html.replace("__PATIENT_ID__", patient.get("patient_id", "APH-2024-087432"))
            html = html.replace("__PATIENT_NAME__", patient.get("name", "Ramaiah Venkatesh"))
            html = html.replace("__PATIENT_DEMO__", f"{patient.get('age', '62')} Y / {patient.get('gender', 'Male')}")
            html = html.replace("__PATIENT_PHONE__", patient.get("phone", "+91-98490-33214"))
            html = html.replace("__PATIENT_LANG__", patient.get("language", "Hindi"))
            html = html.replace("__DISCHARGE_DATE__", patient.get("discharge_date", "25-Oct-2024"))
            html = html.replace("__MEDICATIONS_HTML__", meds_html or "None recorded")

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
