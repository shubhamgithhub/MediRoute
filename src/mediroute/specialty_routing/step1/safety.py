"""Stage 2, emergency check: fixed rules, never an LLM.

A match adds an emergency notice to the response, shown first. For the red-flag rules the suggested
speciality is Emergency Medicine (pipeline.py, decision "emergency_rule"); for suicidal intent
routing continues (Psychiatry) with the crisis message, because the hospital search should still
find mental-health care.

23 Nov 2026 (live request "commiting sucide" got no crisis message):
  * Misspellings: the rules also run on a copy of the text in which words one or two letters away
    from a suicide word are corrected ("sucide" -> suicide, "commiting" -> committing). A match on either copy counts, so the
    correction can only add a match, never remove one.
  * Acute intent ("committing", "going to", "tonight", pills, hanging ...) together with suicidal
    words is a red flag: Emergency Medicine plus the crisis message. Thoughts alone keep Psychiatry
    plus the crisis message. Pending doctor review; until then the safer side is chosen.
  * The evidence LLM also copies any words about self-harm (stage 3); add_llm_self_harm() turns a
    quote that code found in the text into the crisis message. The LLM can add the message, never
    remove one, and the rules work without it.
"""

from __future__ import annotations

import difflib
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

_SUICIDAL = (r"suicid|end(ing)?\s+(my|this)\s+life|kil+(ing)?\s+my\s*self|want\s+to\s+die|"
             r"take\s+my\s+(own\s+)?life|(harm|cut)(ting)?\s+my\s*self|self[-\s]?harm|better\s+off\s+dead|"
             r"no\s+reason\s+to\s+live|(don'?t|do\s+not)\s+want\s+to\s+(live|be\s+alive|wake\s+up)|"
             # Hindi / Hinglish (safety set S04, S05): "I want to die", "no wish to live", suicide
             r"mar\s+ja+n[ae]\s+(chaht|chah)|marna\s+chaht|jeene\s+ka\s+man+\s+nahi|khud\s?kushi|aatm\s?hatya")
# intent now or a method: with suicidal words this is an emergency, not a search for a psychiatrist
_ACUTE = (r"\bcom+it+(ing|ed)?\b|(going|about)\s+to\s+(kill|end|die|do\s+it|commit|take|jump|hang)|"
          r"gonna\s+(kill|end|die|do\s+it)|tonight|right\s+now|this\s+(evening|night)|"
          r"\bplan(ned|ning)?\b|\bpills?\b|overdose|\bhang(ing)?\b|\bjump(ing)?\b|\brope\b|poison|"
          r"\bnote\b|goodbye")

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
    ("suicidal_intent", [_SUICIDAL]),
    ("suicidal_acute", [_SUICIDAL, _ACUTE]),
    ("seizure_not_stopping",
     [r"seizure\w*\s+(not|won'?t)\s+stop|continuous\s+(fits|seizures)|status\s+epilepticus"]),
]
_COMPILED = [(name, [re.compile(p, re.I) for p in patterns]) for name, patterns in _RULES]


# keep normal routing (Psychiatry) + the crisis message; "suicidal_acute" does route to Emergency Medicine
NOT_ROUTED_TO_EMERGENCY = {"suicidal_intent", "self_harm_llm"}
CRISIS_RULES = {"suicidal_intent", "suicidal_acute", "self_harm_llm"}

# Suicide words a misspelling is corrected to ("sucide" -> suicide; 5+ letters, similarity >= 0.85).
# Only these: on all 501 gold messages, correcting other red-flag words ("eating" -> breathing,
# "bending" -> bleeding) raised false alarms, while these change nothing.
_FUZZY_WORDS = ("suicide", "suicidal", "myself", "committing")


def _correct_spelling(text: str) -> str:
    def fix(match: re.Match) -> str:
        word = match.group(0)
        low = word.lower()
        if len(low) < 5 or low in _FUZZY_WORDS:
            return word
        close = difflib.get_close_matches(low, _FUZZY_WORDS, n=1, cutoff=0.85)
        return close[0] if close else word
    return re.sub(r"[A-Za-z]+", fix, text or "")


def _message(matched: list[str]) -> str | None:
    if not matched:
        return None
    crisis = any(r in CRISIS_RULES for r in matched)
    red_flag = any(r not in NOT_ROUTED_TO_EMERGENCY for r in matched)
    if crisis and red_flag:
        return EMERGENCY_MESSAGE + " " + CRISIS_MESSAGE
    return CRISIS_MESSAGE if crisis else EMERGENCY_MESSAGE


def routes_to_emergency(emergency: dict) -> bool:
    """True when a red-flag rule (not only suicidal intent) matched."""
    return any(rule not in NOT_ROUTED_TO_EMERGENCY for rule in emergency.get("matched_rules") or [])


def check_emergency(text: str) -> dict:
    """Every rule runs on the text as written and on a spelling-corrected copy; either may match."""
    copies = [text or "", _correct_spelling(text)]
    matched = [name for name, patterns in _COMPILED
               if any(all(p.search(copy) for p in patterns) for copy in copies)]
    if not matched:
        return {"is_emergency": False, "matched_rules": [], "message": None}
    return {"is_emergency": True, "matched_rules": matched, "message": _message(matched)}


def add_llm_self_harm(emergency: dict, quote: str, text: str) -> dict:
    """The evidence LLM copied words about self-harm and code found them in the text (stage 3).
    Adds the crisis message when the rules missed it (acute wording -> Emergency Medicine too).
    Returns the same dict when there is nothing to add: the LLM never removes a match."""
    if not (quote or "").strip() or any(r in CRISIS_RULES for r in emergency.get("matched_rules") or []):
        return emergency
    matched = list(emergency.get("matched_rules") or []) + ["self_harm_llm"]
    if any(re.search(_ACUTE, copy, re.I) for copy in (text or "", _correct_spelling(text))):
        matched.append("suicidal_acute")
    return {"is_emergency": True, "matched_rules": matched, "message": _message(matched)}
