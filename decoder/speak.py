"""
decoder/speak.py
────────────────
Converts patient discharge explanations into spoken audio using Sarvam Bulbul v3 TTS.
Saves audio output to .wav / .mp3 for playback to patients.
"""

import os
import sys
import json
import base64
import requests
from pathlib import Path

# Fix Windows console encoding if run directly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://api.sarvam.ai/text-to-speech"

LANGUAGE_CODE_MAP = {
    "telugu": "te-IN",
    "hindi": "hi-IN",
    "tamil": "ta-IN",
    "bengali": "bn-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "punjabi": "pa-IN",
    "odia": "od-IN",
    "english": "en-IN",
}


def _headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set in environment or .env.")
    return {
        "api-subscription-key": key,
        "Content-Type": "application/json",
    }


def synthesize_speech(
    text: str,
    language_code: str = "te-IN",
    speaker: str = "ritu",
    pace: float = 0.9,
    model: str = "bulbul:v3",
) -> bytes:
    """
    Calls Sarvam Bulbul v3 TTS API and returns raw audio bytes (WAV format).
    """
    payload = {
        "text": text,
        "language_code": language_code,
        "model": model,
        "speaker": speaker,
        "pace": pace,
    }

    resp = requests.post(API_URL, headers=_headers(), json=payload, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Bulbul TTS failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    audios = data.get("audios", [])
    if not audios:
        raise RuntimeError(f"No audio returned from Bulbul API: {data}")

    # Audios is a list of base64 encoded audio strings
    return base64.b64decode(audios[0])


def compile_spoken_script(explanation_data: dict) -> str:
    """
    Assembles a coherent, natural spoken narrative from the structured explanation JSON.
    """
    parts = []

    # 1. Greeting
    greeting = explanation_data.get("greeting")
    if greeting:
        parts.append(greeting.strip())

    # 2. Main Explanation
    explanation = explanation_data.get("explanation")
    if explanation:
        parts.append(explanation.strip())

    # 3. Medications
    meds = explanation_data.get("medications", [])
    if meds:
        med_lines = []
        for m in meds:
            name = m.get("name", "")
            what = m.get("what_it_does", "")
            when = m.get("when_to_take", "")
            note = m.get("important_note", "")
            details = f"{name}. {what} {when}."
            if note:
                details += f" {note}"
            med_lines.append(details)
        parts.append(" ".join(med_lines))

    # 4. Red Flags
    red_flags = explanation_data.get("red_flags", [])
    if red_flags:
        rf_text = " ".join([f"{rf}." for rf in red_flags])
        parts.append(rf_text)

    # 5. Reminder
    reminder = explanation_data.get("reminder")
    if reminder:
        parts.append(reminder.strip())

    return "\n\n".join(parts)


def text_to_speech_pipeline(
    explanation_data: dict,
    language_name: str = "Telugu",
    output_path: Path = Path("mock/patient_explanation.wav"),
    speaker: str = "ritu",
) -> Path:
    """
    Full Phase 2 Pipeline:
    Constructs spoken text -> synthesizes via Bulbul v3 -> writes .wav file.
    """
    lang_key = language_name.lower().strip()
    lang_code = LANGUAGE_CODE_MAP.get(lang_key, "te-IN")

    script_text = compile_spoken_script(explanation_data)
    print(f"[speak] Compiling spoken narrative ({len(script_text)} characters, {lang_code})...")

    # If script exceeds 2400 chars, we chunk it to stay well within 2500 limit
    chunks = []
    paragraphs = script_text.split("\n\n")
    current_chunk = ""
    for p in paragraphs:
        if len(current_chunk) + len(p) + 2 < 2400:
            current_chunk = (current_chunk + " " + p).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = p
    if current_chunk:
        chunks.append(current_chunk)

    print(f"[speak] Synthesizing {len(chunks)} audio segment(s) using Bulbul v3 (speaker: {speaker})...")
    audio_segments = []
    for idx, chunk in enumerate(chunks, 1):
        print(f"[speak]   Calling Bulbul v3 for segment {idx}/{len(chunks)} ({len(chunk)} chars)...")
        audio_bytes = synthesize_speech(chunk, language_code=lang_code, speaker=speaker, pace=0.9)
        audio_segments.append(audio_bytes)

    # If single segment, write directly
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(audio_segments) == 1:
        output_path.write_bytes(audio_segments[0])
    else:
        # Concatenate audio segments: strip WAV header for subsequent segments if raw wav
        # Bulbul returns standard 44-byte WAV headers
        combined = audio_segments[0]
        for seg in audio_segments[1:]:
            if seg.startswith(b"RIFF") and len(seg) > 44:
                combined += seg[44:]
            else:
                combined += seg
        output_path.write_bytes(combined)

    print(f"[speak] Saved synthesized audio to: {output_path} ({len(output_path.read_bytes()) / 1024:.1f} KB)")
    return output_path


if __name__ == "__main__":
    # Load .env
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    explain_file = Path(__file__).parent.parent / "mock" / "explain_result.json"
    if not explain_file.exists():
        sys.exit("explain_result.json not found. Run phase1 first.")

    exp_data = json.loads(explain_file.read_text(encoding="utf-8"))
    out_audio = Path(__file__).parent.parent / "mock" / "patient_explanation.wav"
    text_to_speech_pipeline(exp_data, language_name="Telugu", output_path=out_audio)
