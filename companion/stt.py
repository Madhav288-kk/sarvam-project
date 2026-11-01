"""
companion/stt.py
────────────────
Speech-to-Text client using Sarvam Saaras v4 model.
Handles audio transcription for telephony and voice agents across 22 Indic languages.
"""

import os
import sys
import requests
from pathlib import Path
from typing import Union, Optional

API_URL = "https://api.sarvam.ai/speech-to-text"

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
        sys.exit("SARVAM_API_KEY not set.")
    return {"api-subscription-key": key}


def transcribe_audio_bytes(
    audio_bytes: bytes,
    language: str = "Telugu",
    model: str = "saaras:v4",
    mode: str = "transcribe",
) -> str:
    """
    Sends raw audio bytes (WAV/MP3) to Sarvam Saaras v4 STT.
    Returns the transcribed text in the native language/script.
    """
    lang_key = language.lower().strip()
    lang_code = LANGUAGE_CODE_MAP.get(lang_key, "te-IN")

    files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
    data = {"model": model, "language_code": lang_code, "mode": mode}

    resp = requests.post(API_URL, headers=_headers(), files=files, data=data, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Saaras STT failed ({resp.status_code}): {resp.text}")

    result = resp.json()
    return result.get("transcript", "").strip()


def transcribe_audio_file(
    audio_path: Union[str, Path],
    language: str = "Telugu",
    model: str = "saaras:v4",
    mode: str = "transcribe",
) -> str:
    """Reads an audio file from disk and transcribes it via Saaras v4."""
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    audio_bytes = path.read_bytes()
    return transcribe_audio_bytes(audio_bytes, language=language, model=model, mode=mode)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    sample_audio = Path(__file__).parent.parent / "mock" / "patient_explanation.wav"
    if sample_audio.exists():
        print(f"Testing Saaras v4 on: {sample_audio.name}...")
        # Test first 100KB chunk
        text = transcribe_audio_bytes(sample_audio.read_bytes()[:150000], language="Telugu")
        print(f"Transcription sample: {text}")
