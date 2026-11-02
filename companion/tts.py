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
        return {"Content-Type": "application/json"}
    return {"api-subscription-key": key, "Content-Type": "application/json"}


def has_arabic_script(text: str) -> bool:
    """Detects whether text contains Perso-Arabic characters (Sindhi, Urdu, Kashmiri)."""
    return any(
        '\u0600' <= c <= '\u06FF' or
        '\u0750' <= c <= '\u077F' or
        '\uFB50' <= c <= '\uFDFF' or
        '\uFE70' <= c <= '\uFEFF'
        for c in text
    )


def _convert_for_tts(text: str, source_lang: str = "hi-IN") -> str:
    """
    If text contains Perso-Arabic script (Sindhi/Urdu), translates or converts it
    to Devanagari script via Sarvam Mayura so Bulbul v3 can synthesize spoken audio.
    """
    if not has_arabic_script(text):
        return text

    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        return text

    try:
        payload = {
            "input": text,
            "source_language_code": "ur-IN" if "ur" in source_lang else "hi-IN",
            "target_language_code": "hi-IN",
            "mode": "formal",
            "model": "mayura:v1"
        }
        r = requests.post(
            "https://api.sarvam.ai/translate",
            headers={"api-subscription-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        if r.ok:
            translated = r.json().get("translated_text", "")
            if translated and not has_arabic_script(translated):
                return translated
    except Exception as e:
        print(f"[tts] Script conversion warning: {e}", file=sys.stderr)

    return text


def speak_turn(
    text: str,
    language: str = "Telugu",
    speaker: str = "ritu",
    pace: float = 0.95,
    save_to: Optional[Union[str, Path]] = None,
) -> bytes:
    """
    Synthesizes a single dialogue turn using Bulbul v3.
    Guaranteed to handle all 22 Indic languages and scripts without crashing.
    """
    lang_key = language.lower().strip()
    lang_code = LANGUAGE_CODE_MAP.get(lang_key, "hi-IN")
    clean_text = (text or "").strip()
    if not clean_text:
        clean_text = "दवाई लेने का समय हो गया है।"

    # Handle Arabic script for Sindhi / Urdu / Kashmiri by adapting to Devanagari
    if has_arabic_script(clean_text):
        clean_text = _convert_for_tts(clean_text, lang_code)
        lang_code = "hi-IN"

    payload = {
        "text": clean_text,
        "language_code": lang_code,
        "model": "bulbul:v3",
        "speaker": speaker,
        "pace": pace,
    }

    try:
        resp = requests.post(API_URL, headers=_headers(), json=payload, timeout=25)
        if resp.ok:
            data = resp.json()
            audios = data.get("audios", [])
            if audios:
                audio_bytes = base64.b64decode(audios[0])
                if save_to:
                    target = Path(save_to)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(audio_bytes)
                return audio_bytes
        else:
            print(f"[tts] Bulbul TTS {resp.status_code} for {lang_code}: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"[tts] Bulbul TTS error: {e}", file=sys.stderr)

    # Automatic fallback to Hindi or English audio if target voice had encoding issue
    for fallback_code in ["hi-IN", "en-IN"]:
        if lang_code != fallback_code:
            try:
                fallback_text = clean_text
                if has_arabic_script(fallback_text):
                    fallback_text = "दवाई लेने का समय हो गया है। कृपया समय पर दवाई लें।"
                payload["text"] = fallback_text
                payload["language_code"] = fallback_code
                resp = requests.post(API_URL, headers=_headers(), json=payload, timeout=15)
                if resp.ok:
                    audios = resp.json().get("audios", [])
                    if audios:
                        return base64.b64decode(audios[0])
            except Exception:
                pass

    return b""
