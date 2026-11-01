"""
decoder/checklist.py
─────────────────────
Generates a structured 30-day weekly recovery checklist from extracted fields.

Output:
  {
    "week_1": [...daily tasks...],
    "week_2": [...],
    "week_3": [...],
    "week_4": [...],
    "ongoing": [...]
  }
"""

import os
import sys
import json
from pathlib import Path
from sarvamai import SarvamAI
import json_repair


SYSTEM_PROMPT = """\
You are a post-discharge recovery planner helping a rural patient in India \
manage their recovery at home. The patient may be illiterate or have limited \
health knowledge — keep every instruction short, specific, and actionable.

Rules:
1. Use simple language appropriate for the patient's specified language.
2. Each task must be concrete (what to do, when, and briefly why).
3. Group tasks by week. Week 1 is most critical — be most detailed there.
4. Include medication reminders, monitoring tasks, diet notes, and warning signs.
5. Output ONLY valid JSON — no markdown, no extra text.

Output schema (strict JSON):
{
  "patient_name": "first name only",
  "language": "language used",
  "week_1": {
    "focus": "One sentence describing the main goal this week",
    "daily_tasks": [
      {
        "time": "Morning / Afternoon / Evening / Night",
        "task": "Specific instruction",
        "why": "One very short reason (optional, skip if obvious)"
      }
    ],
    "watch_for": ["Short red-flag symptom to watch this week"]
  },
  "week_2": { "focus": "...", "daily_tasks": [...], "watch_for": [...] },
  "week_3": { "focus": "...", "daily_tasks": [...], "watch_for": [...] },
  "week_4": { "focus": "...", "daily_tasks": [...], "watch_for": [...] },
  "ongoing": [
    "Long-term habit or monitoring task to continue after 30 days"
  ]
}
"""


def generate_checklist(fields: dict, language: str = None) -> dict:
    lang = language or fields.get("language", "Telugu")

    user_message = f"""\
Language for all output: {lang}

Extracted discharge data:
{json.dumps(fields, indent=2, ensure_ascii=False)}

Generate a 4-week daily recovery checklist in {lang} for this patient.
"""

    client = _client()
    print(f"[checklist] Calling sarvam-105b-conversations (language: {lang}) ...")

    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content.strip()
    return json_repair.loads(raw)


def _client():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set.")
    return SarvamAI(api_subscription_key=key)


if __name__ == "__main__":
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    ingest_file = Path(__file__).parent.parent / "mock" / "ingest_result.json"
    if not ingest_file.exists():
        sys.exit("Run decoder/ingest.py first to generate ingest_result.json")

    data = json.loads(ingest_file.read_text(encoding="utf-8"))
    fields = data.get("fields", data)

    result = generate_checklist(fields)

    out = Path(__file__).parent.parent / "mock" / "checklist_result.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[checklist] Done. Saved to {out}")
    print("\n── WEEK 1 TASKS (preview) ──────────────────────────")
    w1 = result.get("week_1", {})
    print(f"Focus: {w1.get('focus', '')}")
    for t in w1.get("daily_tasks", [])[:5]:
        print(f"  [{t.get('time','')}] {t.get('task','')}")
