"""
decoder/explain.py
──────────────────
Takes the extracted fields from ingest.py and uses sarvam-105b-conversations
to produce a plain-language patient explanation in their native language.

Output:
  { explanation: str, red_flags: [str], reminder: str }
"""

import os
import sys
import json
from pathlib import Path
from sarvamai import SarvamAI
import json_repair


LANGUAGE_NAMES = {
    "Telugu": "Telugu",
    "Hindi": "Hindi",
    "Tamil": "Tamil",
    "Bengali": "Bengali",
    "Marathi": "Marathi",
    "Gujarati": "Gujarati",
    "Kannada": "Kannada",
    "Malayalam": "Malayalam",
    "Punjabi": "Punjabi",
    "Odia": "Odia",
    "English": "English",
}

SYSTEM_PROMPT = """\
You are a compassionate health literacy assistant working with rural patients \
in India who have just been discharged from hospital. Many of them are not \
medically literate. Your job is to make their discharge summary understandable.

Rules:
1. Use simple, warm language. No medical jargon.
2. Do NOT diagnose, modify, or second-guess the doctor's instructions.
3. Do NOT alarm the patient unnecessarily.
4. Output ONLY valid JSON — no markdown, no extra text.
5. Write all content in the language specified in the request.

Output schema (strict JSON):
{
  "greeting": "Warm 2-sentence opening addressing the patient by first name",
  "explanation": "Plain-language summary of what happened and why they were admitted (3-5 sentences)",
  "medications": [
    {
      "name": "simple drug name",
      "what_it_does": "one sentence in plain language",
      "when_to_take": "simple instruction",
      "important_note": "key warning or tip"
    }
  ],
  "red_flags": [
    "Short plain sentence describing one symptom that needs immediate doctor visit"
  ],
  "reminder": "Friendly reminder about next appointment — date, doctor, what to bring"
}
"""


def explain(fields: dict, language: str = None) -> dict:
    """
    fields   : extracted fields dict from ingest.py
    language : override language (defaults to fields["language"])
    """
    lang = language or fields.get("language", "Telugu")
    lang_name = LANGUAGE_NAMES.get(lang, lang)

    user_message = f"""\
Language to use for all output: {lang_name}

Here is the extracted discharge summary data:
{json.dumps(fields, indent=2, ensure_ascii=False)}

Please generate the patient-friendly explanation in {lang_name} following \
the JSON schema exactly.
"""

    client = _client()
    print(f"[explain] Calling sarvam-105b-conversations (language: {lang_name}) ...")

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
    # Load .env
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    # Load ingest result
    ingest_file = Path(__file__).parent.parent / "mock" / "ingest_result.json"
    if not ingest_file.exists():
        sys.exit("Run decoder/ingest.py first to generate ingest_result.json")

    data = json.loads(ingest_file.read_text(encoding="utf-8"))
    fields = data.get("fields", data)

    result = explain(fields)

    out = Path(__file__).parent.parent / "mock" / "explain_result.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[explain] Done. Saved to {out}")
    print("\n── EXPLANATION (preview) ──────────────────────────")
    print(json.dumps(result, indent=2, ensure_ascii=False))
