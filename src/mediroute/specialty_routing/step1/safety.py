"""Stage 2, emergency check: fixed rules, never an LLM.

A match adds an emergency notice to the response. Routing still continues, so the patient also
gets a speciality, but the notice is shown first.
"""

from __future__ import annotations

import re

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please contact local emergency services or go to the nearest "
    "emergency department now. MediRoute is a hospital discovery tool, not an emergency service."
)
CRISIS_MESSAGE = (
    "If you are thinking about ending your life, please reach out now to local emergency services "
    "or a crisis helpline (in India: Tele-MANAS 14416). You are not alone."
)

# (rule name, patterns that must ALL match somewhere in the text)
_RULES: list[tuple[str, list[str]]] = [
    ("chest_pain_with_breathlessness_or_sweating",
     [r"chest\s*(pain|tightness|pressure)|crushing\s+chest|severe\s+chest",
      r"breath|breathless|sweat|sweating|arm\s+pain|jaw"]),
    ("stroke_signs",
     [r"face\s+(is\s+)?droop|drooping\s+face|droop\w*\s+on\s+one\s+side|slurred\s+speech|"
      r"(can'?t|cannot|unable\s+to)\s+speak|sudden\s+(weakness|numbness)|one\s+side\s+of\s+(the\s+)?body"]),
    ("unconscious_or_not_breathing",
     [r"unconscious|not\s+breathing|stopped\s+breathing|collapsed|passed\s+out|unresponsive"]),
    ("heavy_bleeding",
     [r"heavy\s+bleeding|bleeding\s+heavily|vomiting\s+blood|coughing\s+(up\s+)?blood|"
      r"bleeding\s+(that\s+)?(won'?t|will\s+not)\s+stop"]),
    ("suicidal_intent",
     [r"suicid|end(ing)?\s+my\s+life|kill\s+myself|want\s+to\s+die|take\s+my\s+(own\s+)?life"]),
    ("seizure_not_stopping",
     [r"seizure\w*\s+(not|won'?t)\s+stop|continuous\s+(fits|seizures)|status\s+epilepticus"]),
]
_COMPILED = [(name, [re.compile(p, re.I) for p in patterns]) for name, patterns in _RULES]


def check_emergency(text: str) -> dict:
    matched = [name for name, patterns in _COMPILED if all(p.search(text or "") for p in patterns)]
    if not matched:
        return {"is_emergency": False, "matched_rules": [], "message": None}
    message = CRISIS_MESSAGE if matched == ["suicidal_intent"] else EMERGENCY_MESSAGE
    if "suicidal_intent" in matched and len(matched) > 1:
        message = EMERGENCY_MESSAGE + " " + CRISIS_MESSAGE
    return {"is_emergency": True, "matched_rules": matched, "message": message}
