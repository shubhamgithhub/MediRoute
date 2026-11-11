import json
import urllib.request

payload = json.dumps({
    'requirement': 'my knee is paining',
    'location': 'Bengaluru',
    'language': 'English',
    'additionalPreference': '',
    'reportName': []
}).encode('utf-8')

req = urllib.request.Request(
    'http://127.0.0.1:8124/api/analyze',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

with urllib.request.urlopen(req, timeout=20) as response:
    body = response.read().decode('utf-8')
    print(response.status)
    print(body)
