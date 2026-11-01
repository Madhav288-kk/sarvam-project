"""
companion/tts.py
────────────────
Text-to-Speech synthesis for outbound conversational voice agents via Bulbul v3.
Produces low-latency spoken audio for individual call dialogue turns.
"""

import os
import sys
import base64
import requests
from pathlib import Path
from typing import Optional, Union

API_URL = "https://api.sarvam.ai/text-to-speech"

LANGUAGE_CODE_MAP = {
    "hindi": "hi-IN",
    "bengali": "bn-IN",
    "telugu": "te-IN",
    "tamil": "ta-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "punjabi": "pa-IN",
    "odia": "od-IN",
    "english": "en-IN",
    # Extended Indic languages mapped to compatible high-accuracy voices:
    "assamese": "bn-IN",
    "urdu": "hi-IN",
    "maithili": "hi-IN",
    "nepali": "hi-IN",
    "konkani": "mr-IN",
    "kashmiri": "hi-IN",
    "sindhi": "hi-IN",
    "sanskrit": "hi-IN",
    "santali": "od-IN",
    "manipuri": "bn-IN",
    "bodo": "bn-IN",
    "dogri": "pa-IN",
}


def _headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set.")
    return {"api-subscription-key": key, "Content-Type": "application/json"}


def speak_turn(
    text: str,
    language: str = "Telugu",
    speaker: str = "ritu",
    pace: float = 0.95,
    save_to: Optional[Union[str, Path]] = None,
) -> bytes:
    """
    Synthesizes a single dialogue turn using Bulbul v3.
    Optionally saves the resulting WAV to save_to.
    """
    lang_key = language.lower().strip()
    lang_code = LANGUAGE_CODE_MAP.get(lang_key, "te-IN")

    payload = {
        "text": text,
        "language_code": lang_code,
        "model": "bulbul:v3",
        "speaker": speaker,
        "pace": pace,
    }

    resp = requests.post(API_URL, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Bulbul TTS failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    audios = data.get("audios", [])
    if not audios:
        raise RuntimeError("No audio received from Bulbul TTS")

    audio_bytes = base64.b64decode(audios[0])
    if save_to:
        target = Path(save_to)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio_bytes)

    return audio_bytes
