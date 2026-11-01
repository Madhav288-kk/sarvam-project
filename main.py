import os
import sys
from pathlib import Path
from sarvamai import SarvamAI

# Load .env manually — no extra dependency needed
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    raise RuntimeError("SARVAM_API_KEY is not set. Paste your key into .env first.")

client = SarvamAI(api_subscription_key=api_key)

response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[
        {"role": "user", "content": "Hello! What can you help me with?"}
    ],
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(response.choices[0].message.content)
