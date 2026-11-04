import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
LOG_PATH = REPO_ROOT / "logs" / "mediroute.log"


def wait_for_server(url: str, timeout_seconds: int = 30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Server did not start before {timeout_seconds} seconds: {url}")


process = subprocess.Popen(
    [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "mediroute.backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8129",
    ],
    cwd=str(REPO_ROOT),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

try:
    wait_for_server("http://127.0.0.1:8129/api/health")

    payload = json.dumps({
        "requirement": "my knee is paining",
        "location": "Bengaluru",
        "language": "English",
        "additionalPreference": "",
        "reportName": []
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:8129/api/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8")
        print(f"HTTP {response.status}")
        print(body)

    print("\n--- LOG TAIL ---")
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        for line in lines[-30:]:
            print(line)
    else:
        print("No log file found yet")
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
