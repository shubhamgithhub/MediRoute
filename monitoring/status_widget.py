"""CloudWatch custom widget for live, read-only MediRoute HTTPS checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from http.client import HTTPException, HTTPSConnection
import json

HOST = "mediroute-demo.duckdns.org"
TIMEOUT = 3

API_ROUTES = {
    "Status and discovery": (
        ("GET", "/api/health"),
        ("GET", "/api/cities"),
        ("GET", "/api/hospitals"),
        ("GET", "/api/hospitals/search"),
        ("GET", "/api/hospitals/keyword-search"),
    ),
    "Routing and reports": (
        ("POST", "/api/patient-routing"),
        ("POST", "/api/analyze"),
        ("POST", "/api/reports/parse"),
        ("POST", "/api/hospitals/recommend"),
        ("POST", "/api/hospitals/semantic-recommendations"),
    ),
    "Accounts and history": (
        ("POST", "/api/auth/signup"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/auth/me"),
        ("DELETE", "/api/auth/me"),
        ("POST", "/api/history"),
        ("GET", "/api/history"),
        ("GET", "/api/history/{entry_id}"),
        ("DELETE", "/api/history/{entry_id}"),
        ("DELETE", "/api/history/{entry_id}/hospitals/{hospital_id}"),
    ),
    "Admin": (
        ("GET", "/api/admin/requests"),
        ("GET", "/api/admin/requests/{request_id}"),
    ),
}

# These checks neither run paid inference nor read any admin request history.
# An expected 401/422 confirms the endpoint reached its auth/validation guard.
DIRECT = {
    "/api/cities": ("/api/cities", 200, "Read check"),
    "/api/hospitals": ("/api/hospitals", 200, "Read check"),
    "/api/hospitals/search": ("/api/hospitals/search?location=MediRouteStatusProbe", 200, "Read check"),
    "/api/hospitals/keyword-search": ("/api/hospitals/keyword-search", 422, "Validation check"),
    "/api/auth/me": ("/api/auth/me", 401, "Unauthenticated request"),
    "/api/history": ("/api/history", 401, "Unauthenticated request"),
    "/api/history/{entry_id}": ("/api/history/0", 401, "Unauthenticated request"),
    "/api/admin/requests": ("/api/admin/requests?limit=0", 422, "Validation check"),
}


def fetch(method, path, limit=0):
    connection = HTTPSConnection(HOST, timeout=TIMEOUT)
    try:
        connection.request(method, path, headers={"User-Agent": "MediRoute-CloudWatch-Status/1"})
        response = connection.getresponse()
        return response.status, response.read(limit) if limit else b""
    except (HTTPException, OSError):
        return 0, b""
    finally:
        connection.close()


def json_object(response):
    status, body = response
    if status != 200:
        return {}
    try:
        value = json.loads(body)
    except (UnicodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def check_key(method, path):
    if method == "GET" and path in DIRECT:
        return ("GET", DIRECT[path][0], 0)
    url = (path.replace("{entry_id}", "0").replace("{hospital_id}", "0")
           .replace("{request_id}", "mediroute-status-probe"))
    return ("OPTIONS", url, 0)


def snapshot(fetch_url=fetch):
    routes = [entry for group in API_ROUTES.values() for entry in group]
    health_key = ("GET", "/api/health", 4096)
    page_key = ("GET", "/patient.html", 8192)
    keys = [health_key, page_key]
    keys.extend(check_key(method, path) for method, path in routes if path != "/api/health")
    keys = list(dict.fromkeys(keys))
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = dict(zip(keys, pool.map(lambda key: fetch_url(*key), keys)))

    health = json_object(results[health_key])
    api_up = health.get("status") == "healthy" and health.get("service") == "MediRoute API"
    page_status, page = results[page_key]
    app_up = api_up and page_status == 200 and b'<body class="patient-page">' in page

    rows = {}
    for method, path in routes:
        if path == "/api/health":
            rows[(method, path)] = (api_up, "Live liveness check")
            continue
        status, _ = results[check_key(method, path)]
        if method == "GET" and path in DIRECT:
            _, expected, description = DIRECT[path]
            rows[(method, path)] = (status == expected, f"{description} · HTTP {status or '—'}")
        else:
            rows[(method, path)] = (status == 405, f"Path check (OPTIONS) · HTTP {status or '—'}")
    return app_up, rows


def badge(up):
    label = "UP" if up else "DOWN"
    color = "#166534" if up else "#991b1b"
    return (f'<span style="color:white;background-color:{color};font-weight:700;'
            f'padding:3px 8px;border-radius:6px;white-space:nowrap">{label}</span>')


def render(app_up, rows, timestamp):
    groups = []
    for group, entries in API_ROUTES.items():
        cards = []
        for method, path in entries:
            up, description = rows[(method, path)]
            cards.append(
                '<tr><td style="padding:2px 7px 2px 0">' + badge(up) + '</td>'
                f'<td style="padding:2px 0;overflow-wrap:anywhere"><code>{escape(method + " " + path)}</code>'
                f'<div style="font-size:11px;opacity:.85">{escape(description)}</div></td></tr>'
            )
        groups.append(f'<div><h4 style="margin:4px 0 2px">{escape(group)}</h4>'
                      '<table style="width:100%;border-collapse:collapse">' + "".join(cards) + '</table></div>')
    healthy = sum(up for up, _ in rows.values())
    return (
        '<div style="font-family:system-ui,sans-serif;padding:8px;line-height:1.3">'
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:5px">'
        f'<strong>App · latest check</strong> {badge(app_up)} <span>Public patient page and API</span>'
        f'<small>{escape(timestamp)}</small></div>'
        f'<div style="margin:9px 0 4px"><strong>API · latest check</strong> · {healthy}/{len(rows)} UP</div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:4px 18px">'
        + "".join(groups) +
        '</div><p style="font-size:11px;margin:6px 0 0">OPTIONS checks confirm the URL responds as a registered route. '
        'They check path reachability without running inference or writing data. The public app shows DOWN while its demo task is stopped.</p></div>'
    )


def lambda_handler(event, _context):
    if isinstance(event, dict) and event.get("describe"):
        return {"markdown": "Live HTTPS app and API route status for the MediRoute DuckDNS demo. No parameters."}
    app_up, rows = snapshot()
    return render(app_up, rows, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
