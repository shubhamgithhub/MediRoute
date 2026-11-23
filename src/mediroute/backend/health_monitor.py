"""Lightweight synthetic probes over the ECS task's shared loopback network."""

from http.client import HTTPConnection, HTTPException
import json
import os

from mediroute.utils.cloudwatch_metrics import emit

INTERVAL_S = 60
FRONTEND_PORT = 8080


def get_local(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read(8192)
    except (HTTPException, OSError):
        return 0, b""
    finally:
        connection.close()


def api_health(result):
    status, body = result
    if status != 200:
        return False
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        return False
    return (isinstance(value, dict) and value.get("status") == "healthy"
            and value.get("service") == "MediRoute API")


def check_health(api_port, get=get_local):
    api_ok = api_health(get(api_port, "/api/health"))
    page_status, page = get(FRONTEND_PORT, "/patient.html")
    page_ok = page_status == 200 and b'<body class="patient-page">' in page
    proxy_ok = api_health(get(FRONTEND_PORT, "/api/health"))
    return {"ApiProbeSuccess": int(api_ok), "AppProbeSuccess": int(api_ok and page_ok and proxy_ok)}


def monitor_health(stop):
    api_port = int(os.getenv("MEDIROUTE_PORT", "8000"))
    # Give the API and its dependent frontend time to start before the first check.
    while not stop.wait(INTERVAL_S):
        observation = check_health(api_port)
        if not stop.is_set():
            emit(observation)
