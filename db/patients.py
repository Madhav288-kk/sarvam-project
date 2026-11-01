"""
db/patients.py
──────────────
Lightweight SQLite repository for post-discharge patient records and check-in call logs.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path(__file__).parent.parent / "mock" / "patients.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            age TEXT,
            gender TEXT,
            phone TEXT,
            language TEXT DEFAULT 'Telugu',
            discharge_date TEXT,
            diagnoses TEXT,
            medications TEXT,
            follow_ups TEXT,
            checklist TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS checkin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            call_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transcript TEXT NOT NULL,
            adherence TEXT,
            symptoms TEXT,
            flags TEXT,
            escalated BOOLEAN DEFAULT 0,
            escalation_details TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        )
        """)
        conn.commit()


def save_patient(patient_data: Dict[str, Any]):
    """Insert or update patient record."""
    init_db()
    with get_connection() as conn:
        conn.execute("""
        INSERT INTO patients (
            patient_id, name, age, gender, phone, language, discharge_date,
            diagnoses, medications, follow_ups, checklist
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET
            name=excluded.name,
            age=excluded.age,
            gender=excluded.gender,
            phone=excluded.phone,
            language=excluded.language,
            discharge_date=excluded.discharge_date,
            diagnoses=excluded.diagnoses,
            medications=excluded.medications,
            follow_ups=excluded.follow_ups,
            checklist=excluded.checklist
        """, (
            patient_data.get("patient_id", "UNKNOWN"),
            patient_data.get("name", "Unknown Patient"),
            str(patient_data.get("age", "")),
            patient_data.get("gender", ""),
            patient_data.get("phone", "+91-98490-33214"),
            patient_data.get("language", "Telugu"),
            patient_data.get("discharge_date", ""),
            json.dumps(patient_data.get("diagnoses", []), ensure_ascii=False),
            json.dumps(patient_data.get("medications", []), ensure_ascii=False),
            json.dumps(patient_data.get("follow_ups", []), ensure_ascii=False),
            json.dumps(patient_data.get("checklist", {}), ensure_ascii=False),
        ))
        conn.commit()


def get_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["diagnoses"] = json.loads(d["diagnoses"]) if d.get("diagnoses") else []
        d["medications"] = json.loads(d["medications"]) if d.get("medications") else []
        d["follow_ups"] = json.loads(d["follow_ups"]) if d.get("follow_ups") else []
        d["checklist"] = json.loads(d["checklist"]) if d.get("checklist") else {}
        return d


def log_checkin(
    patient_id: str,
    transcript: List[Dict[str, str]],
    adherence: Dict[str, bool],
    symptoms: List[str],
    flags: List[str],
    escalated: bool,
    escalation_details: Optional[Dict[str, Any]] = None,
) -> int:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("""
        INSERT INTO checkin_logs (
            patient_id, transcript, adherence, symptoms, flags, escalated, escalation_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            json.dumps(transcript, ensure_ascii=False),
            json.dumps(adherence, ensure_ascii=False),
            json.dumps(symptoms, ensure_ascii=False),
            json.dumps(flags, ensure_ascii=False),
            1 if escalated else 0,
            json.dumps(escalation_details, ensure_ascii=False) if escalation_details else None,
        ))
        conn.commit()
        return cursor.lastrowid
