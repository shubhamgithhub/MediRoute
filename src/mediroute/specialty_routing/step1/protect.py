"""Stage 1, read and protect: remove contact details and ID numbers before any model sees the text.

Only identifiers with a clear shape are removed (e-mail, phone number, long ID numbers). Medical
values such as "eGFR 8", "14x9 cm" or dates are kept because they carry clinical meaning.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# a run of digits with optional separators; kept as a phone only if it has 10-15 digits
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_AADHAAR = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
_ID_NUMBER = re.compile(r"\b(?:[A-Z]{1,3}\d{6,}|\d{11,})\b")  # passport / MRN / long IDs


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return the text with identifiers replaced, and how many of each kind were removed."""
    counts = {"email": 0, "phone": 0, "id_number": 0}
    text = text or ""

    def sub_email(_m: re.Match) -> str:
        counts["email"] += 1
        return "[EMAIL]"

    def sub_phone(match: re.Match) -> str:
        digits = sum(ch.isdigit() for ch in match.group(0))
        if 10 <= digits <= 15:
            counts["phone"] += 1
            return "[PHONE]"
        return match.group(0)

    def sub_id(_m: re.Match) -> str:
        counts["id_number"] += 1
        return "[ID]"

    text = _EMAIL.sub(sub_email, text)
    text = _AADHAAR.sub(sub_id, text)
    text = _PHONE_CANDIDATE.sub(sub_phone, text)
    text = _ID_NUMBER.sub(sub_id, text)
    return text, counts
