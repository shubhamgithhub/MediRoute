# MediRoute API Test Playground

Use this file as a quick manual test guide for the Patient-to-Specialty API.

## 1) Start the backend

From the project root:

```powershell
cd "C:\Users\pravi\PG IITB\AI ML in practice\captsone project\pravin\MediRoute"
.\.venv\Scripts\python.exe -m uvicorn mediroute.backend.main:app --host 127.0.0.1 --port 8000
```

If you are using the newer verified server instance we tested earlier, it was running on:

- http://127.0.0.1:8123

Use the port that is active in your terminal session. The app is the same backend code, only the port may differ.

## 2) Start the frontend

From the project root:

```powershell
cd "C:\Users\pravi\PG IITB\AI ML in practice\captsone project\pravin\MediRoute"
.\.venv\Scripts\python.exe -m http.server 5500
```

Then open:

- http://127.0.0.1:5500

## 3) Swagger documentation

FastAPI automatically exposes Swagger UI once the backend is running:

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

If your backend is running on port 8123, use that port instead:

- Swagger UI: http://127.0.0.1:8123/docs
- OpenAPI JSON: http://127.0.0.1:8123/openapi.json

## Base API

- Local backend: http://127.0.0.1:8000
- Analyze endpoint: http://127.0.0.1:8000/api/analyze

## Example request body

```json
{
  "requirement": "My vision is blurry",
  "location": "Bengaluru",
  "language": "English",
  "additionalPreference": "",
  "reportName": []
}
```

## Expected specialty for this example

- `Ophthalmology`
- `Eye Care`

## More test cases

### 1. Blurry vision

```json
{
  "requirement": "My vision is blurry and I have eye pain",
  "location": "Bengaluru",
  "language": "English",
  "additionalPreference": "",
  "reportName": []
}
```

Expected: Ophthalmology / Eye Care

### 2. Chest pain

```json
{
  "requirement": "I have chest pain and shortness of breath",
  "location": "Mumbai",
  "language": "English",
  "additionalPreference": "",
  "reportName": []
}
```

Expected: Cardiology or Pulmonology depending on wording

### 3. Knee pain

```json
{
  "requirement": "I have severe knee pain and joint stiffness",
  "location": "Delhi",
  "language": "English",
  "additionalPreference": "",
  "reportName": []
}
```

Expected: Orthopaedics / Musculoskeletal Care

### 4. Skin rash

```json
{
  "requirement": "I have a rash and itching on my skin",
  "location": "Chennai",
  "language": "English",
  "additionalPreference": "",
  "reportName": []
}
```

Expected: Dermatology / Skin Care

## 4) Run a request manually

You can test from a terminal with Python:

```powershell
"C:\Users\pravi\PG IITB\AI ML in practice\captsone project\pravin\MediRoute\.venv\Scripts\python.exe" -c "import json, urllib.request; payload = json.dumps({'requirement':'My vision is blurry','location':'Bengaluru','language':'English','additionalPreference':'','reportName':[]}).encode(); req = urllib.request.Request('http://127.0.0.1:8000/api/analyze', data=payload, headers={'Content-Type':'application/json'}, method='POST'); r = urllib.request.urlopen(req, timeout=20); print(r.status); print(r.read().decode())"
```

If your backend is on port 8123, replace the URL with `http://127.0.0.1:8123/api/analyze`.

## 5) Logger setup and retrieval

The project uses Python logging so backend actions can be inspected while the service is running.

### Logger configuration

The FastAPI app can be configured to emit logs at INFO or DEBUG level. In practice, the service prints important events such as:

- startup messages
- request handling
- medical-context inference
- hospital retrieval activity
- report parsing activity

Typical Python logging setup:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
```

### How logs are retrieved

1. Start the backend in a terminal.
2. Watch the terminal output while requests are made.
3. Logs appear in real time from the app process.
4. For more detailed debugging, set the log level to DEBUG:

```python
logging.basicConfig(level=logging.DEBUG)
```

### Useful places to log

- before/after `infer_medical_context_from_query()`
- when `POST /api/analyze` is called
- when specialty match is selected
- when hospital retrieval begins and returns results
- when report parsing starts and finishes

Example:

```python
logger.info("Analyzing patient request: %s", request.requirement)
logger.info("Recommended specialty: %s", medical_context.get("relevantSpecialty"))
```

## Notes

- Use `reportName: []` for no uploaded reports.
- If the request is a free-form clinical symptom, the system will route based on keyword matching and local specialty taxonomy.
- If you want to test your own custom prompt, replace the `requirement` text only and keep the rest of the payload the same.
- Swagger is the easiest place to test request/response payloads visually without writing Python manually.
