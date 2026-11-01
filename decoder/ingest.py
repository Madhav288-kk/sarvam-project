"""
decoder/ingest.py
─────────────────
Sends a discharge summary PDF to Sarvam Vision (doc-ai/v1) and returns:
  - raw_text : full markdown layout from /doc-ai/v1/job/digitise
  - fields   : structured field extraction parsed via sarvam-105b from markdown

Vision API flow:
  1. POST /doc-ai/v1/job/digitise  -> { job_id }
  2. GET  /doc-ai/v1/job/{id}/status  (poll until "completed")
  3. GET  /doc-ai/v1/job/{id}/download-url  -> extract markdown file from ZIP
"""

import os
import sys
import json
import time
import zipfile
import io
import requests
from pathlib import Path
from sarvamai import SarvamAI

API_BASE = "https://api.sarvam.ai"


def _headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        sys.exit("SARVAM_API_KEY not set. Add it to .env.")
    return {"api-subscription-key": key}


# ── DIGITISE ─────────────────────────────────────────────────────────────────

def digitise(pdf_path: Path) -> str:
    """Full-page text extraction — returns markdown string."""
    print(f"[ingest] Submitting digitise job: {pdf_path.name} ...")
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/doc-ai/v1/job/digitise",
            headers=_headers(),
            files={"file": (pdf_path.name, f, "application/pdf")},
            data={"language": "en-IN", "output_format": "md", "content_type": "printed"},
            timeout=60,
        )
    _raise(resp, "digitise submit")
    job_id = resp.json()["job_id"]
    print(f"[ingest] Digitise job_id: {job_id}")

    _wait_for_job(job_id)
    return _fetch_markdown_from_zip(job_id)


def _fetch_markdown_from_zip(job_id: str) -> str:
    """Download ZIP from download-url and extract markdown content."""
    resp = requests.get(
        f"{API_BASE}/doc-ai/v1/job/{job_id}/download-url",
        headers=_headers(),
        timeout=30,
    )
    _raise(resp, "download-url")
    download_url = resp.json().get("url")
    if not download_url:
        raise RuntimeError("No URL in download-url response")

    zip_resp = requests.get(download_url, timeout=60)
    zip_resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
        md_files = [n for n in z.namelist() if n.endswith(".md")]
        if md_files:
            return z.read(md_files[0]).decode("utf-8")
        # Fallback to text files
        for n in z.namelist():
            if not n.endswith(".json"):
                return z.read(n).decode("utf-8", errors="replace")
    return ""


# ── EXTRACT ──────────────────────────────────────────────────────────────────

def extract_from_markdown(raw_text: str) -> dict:
    """Extracts structured clinical fields from the digitised markdown using Sarvam LLM."""
    print("[ingest] Extracting structured fields using sarvam-105b-conversations ...")
    key = os.environ.get("SARVAM_API_KEY", "")
    client = SarvamAI(api_subscription_key=key)

    prompt = f"""You are an expert clinical data parser. Extract the following fields from this hospital discharge summary markdown into strict JSON format:
- patient_name (string)
- patient_id (string)
- age (string or number)
- gender (string)
- language (preferred language, default 'Telugu' or as stated)
- admission_date (string)
- discharge_date (string)
- diagnoses (list of strings)
- medications (list of objects with keys: name, dose, frequency, duration, instructions)
- lab_results (list of objects with keys: test, value, status)
- follow_up_dates (list of strings with doctor/department and date)
- diet_instructions (list of strings)
- red_flag_symptoms (list of strings)
- home_monitoring (list of strings)
- treating_doctor (string)

Discharge Summary Markdown:
\"\"\"
{raw_text}
\"\"\"

Output ONLY valid JSON matching this schema."""

    response = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    return json.loads(content)


# ── SHARED HELPERS ────────────────────────────────────────────────────────────

def _wait_for_job(job_id: str, max_wait: int = 120):
    """Poll status until job completes or fails."""
    terminal = {"completed", "partially_completed", "failed", "rejected"}
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(3)
        resp = requests.get(
            f"{API_BASE}/doc-ai/v1/job/{job_id}/status",
            headers=_headers(),
            timeout=30,
        )
        _raise(resp, "status poll")
        data = resp.json()
        status = data.get("status", "").lower()
        print(f"[ingest] Job {job_id[:8]}... status: {status}")
        if status in terminal:
            if status in ("failed", "rejected"):
                raise RuntimeError(f"Vision job {job_id} {status}: {data}")
            return
    raise TimeoutError(f"Vision job {job_id} timed out after {max_wait}s")


def _raise(resp, label: str):
    if not resp.ok:
        raise RuntimeError(
            f"[ingest] {label} failed {resp.status_code}: {resp.text[:300]}"
        )


# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────

def ingest(pdf_path: Path) -> dict:
    """Full ingestion: returns { raw_text: str, fields: dict }"""
    raw_text = digitise(pdf_path)
    fields = extract_from_markdown(raw_text)
    return {"raw_text": raw_text, "fields": fields}


if __name__ == "__main__":
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    pdf = Path(__file__).parent.parent / "mock" / "discharge_summary.pdf"
    if not pdf.exists():
        sys.exit("PDF not found. Run: python mock/generate_discharge_pdf.py")

    result = ingest(pdf)
    out = Path(__file__).parent.parent / "mock" / "ingest_result.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[ingest] Done. Saved to {out}")
    print(json.dumps(result["fields"], indent=2, ensure_ascii=False))
