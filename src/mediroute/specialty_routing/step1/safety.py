"""Stage 2, emergency check: fixed rules, never an LLM.

A match adds an emergency notice to the response, shown first. For the red-flag rules the suggested
speciality is Emergency Medicine (pipeline.py, decision "emergency_rule"); for suicidal intent
routing continues (Psychiatry) with the crisis message, because the hospital search should still
find mental-health care.
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
_CHEST = (r"chest\s*(pains?|tightness|tight|pressure|hurts?|hurting|ache)|crushing\s+chest|severe\s+chest|"
          r"chest\s+(is|has\s+been|feels?)\s+(hurting|tight|painful|heavy)")
_BREATHLESS = (r"can'?t\s+(catch\s+my\s+)?breath|cannot\s+(catch\s+my\s+)?breath|short(ness)?\s+of\s+breath|"
               r"breathless|trouble\s+breathing|hard\s+to\s+breathe|difficulty\s+(in\s+)?breathing|"
               r"can'?t\s+breathe|cannot\s+breathe")
_RACING = r"heart\s+(is\s+)?(racing|pounding)|racing\s+heart|pounding\s+heart|palpitation"

# (rule name, patterns that must ALL match somewhere in the text)
_RULES: list[tuple[str, list[str]]] = [
    # 14 Nov: "my chest hurts" / "chest pains" and racing heart, dizziness or light-headedness added
    # (portal test: G004, G010, G042, G091, G102, G124 were not caught). Chest pain alone, e.g. with
    # heartburn when lying down, does not match.
    ("chest_pain_with_breathlessness_or_sweating",
     [_CHEST,
      r"breath|breathless|sweat|sweating|arm\s+pain|jaw|" + _RACING + r"|dizz\w*|light-?\s?headed|faint"]),
    ("breathless_with_racing_heart", [_BREATHLESS, _RACING]),
    ("sudden_loss_of_sight",
     [r"lost\s+(my\s+)?(sight|vision|eyesight)|sudden(ly)?\s+(loss\s+of\s+(sight|vision)|blind|can'?t\s+see|"
      r"cannot\s+see)|went\s+blind|sudden\s+(blindness|vision\s+loss)"]),
    ("new_confusion",
     [r"\bdisorient(ed|ation)\b|\bsudden(ly)?\s+confus\w*|"
      r"\b(feel|feels|feeling|felt|am|is|been|getting|become|became)\s+(\w+\s+){0,3}confused\b"
      r"(?!\s+(about|which|whether|if|what|between|on|by|with))"]),
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


NOT_ROUTED_TO_EMERGENCY = {"suicidal_intent"}  # keeps normal routing (Psychiatry) + the crisis message


def routes_to_emergency(emergency: dict) -> bool:
    """True when a red-flag rule (not only suicidal intent) matched."""
    return any(rule not in NOT_ROUTED_TO_EMERGENCY for rule in emergency.get("matched_rules") or [])


def check_emergency(text: str) -> dict:
    matched = [name for name, patterns in _COMPILED if all(p.search(text or "") for p in patterns)]
    if not matched:
        return {"is_emergency": False, "matched_rules": [], "message": None}
    message = CRISIS_MESSAGE if matched == ["suicidal_intent"] else EMERGENCY_MESSAGE
    if "suicidal_intent" in matched and len(matched) > 1:
        message = EMERGENCY_MESSAGE + " " + CRISIS_MESSAGE
    return {"is_emergency": True, "matched_rules": matched, "message": message}
