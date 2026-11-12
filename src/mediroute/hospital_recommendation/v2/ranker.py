"""Step 2 v2 ranking: eligibility -> location tiers -> capability -> criteria -> TOPSIS.

Criteria (each 0-1) and starting AHP weights, mapped from Şahin & Cezlan (2022), the expert
weights of hospital-choice criteria for health tourists (docs/reference_paper_opusjsr_2326653.pdf):

    capability  qualified personnel 0.199 + modern equipment 0.124            -> 0.378
    quality     quality of care 0.166 + accreditation 0.062 + image 0.091     -> 0.372
    evidence    recommendability 0.098                                        -> 0.114
    intl_care   language 0.056 + touristic features 0.026                     -> 0.096
    location    regional / cultural proximity 0.034                           -> 0.039
    (promotion 0.050 not used; affordability 0.095 only when a budget is given - not in this POC)
Weights are renormalised over the criteria used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from mediroute.common.locations import resolve_location
from mediroute.hospital_recommendation.specialty_filter import TEAM_LISTED, VERIFIED, SpecialtyFilter
from mediroute.hospital_recommendation.v2.capability import SPECIALITY, CapabilityResult

PAPER_WEIGHTS = {"capability": 0.199487 + 0.123654, "quality": 0.165864 + 0.061952 + 0.090537,
                 "evidence": 0.097737, "intl_care": 0.055881 + 0.026353, "location": 0.033557}
MIN_CANDIDATES = 3  # location tiers widen the search when the area has fewer eligible hospitals


def normalised(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


WEIGHTS = normalised(PAPER_WEIGHTS)


def _positive(value) -> bool:
    text = str(value or "").strip().casefold()
    return text.startswith(("accredited", "verified", "available", "yes", "certified"))


def topsis(matrix: list[list[float]], weights: list[float]) -> list[float]:
    """Closeness to the ideal solution (0-1) for each row; all criteria are benefits."""
    if not matrix:
        return []
    cols = list(zip(*matrix))
    norms = [math.sqrt(sum(x * x for x in c)) or 1.0 for c in cols]
    weighted = [[w * row[j] / norms[j] for j, w in enumerate(weights)] for row in matrix]
    best = [max(r[j] for r in weighted) for j in range(len(weights))]
    worst = [min(r[j] for r in weighted) for j in range(len(weights))]
    out = []
    for r in weighted:
        d_best, d_worst = math.dist(r, best), math.dist(r, worst)
        out.append(d_worst / (d_best + d_worst) if d_best + d_worst > 0 else 1.0)
    return out


@dataclass
class Ranked:
    hospital_id: str
    hospital_name: str
    city: str
    tier: str
    score: float
    criteria: dict[str, float]
    capability: CapabilityResult
    reasons: list[str] = field(default_factory=list)


class V2Ranker:
    def __init__(self, metadata: list[dict], capability, tiers: bool = False, weights: dict | None = None) -> None:
        self.metadata = metadata
        self.capability = capability
        self.tiers = tiers
        self.weights = normalised(weights) if weights else WEIGHTS
        self.filter = SpecialtyFilter()

    def _tier(self, h: dict, area: set[str] | None, state: str) -> str | None:
        if area is None and not state:
            return "area"  # no preference: everything is in the patient's area
        if area is not None and str(h.get("city") or "").strip() in area:
            return "area"
        if state and str(h.get("state") or "").strip().casefold() == state:
            return "area" if area is None else "state"
        return None

    def candidates(self, specialty: str, city: str, state: str) -> list[tuple[dict, str]]:
        area = resolve_location(city) if city else None
        state_cf = (state or "").casefold()
        if area is not None and not state_cf:  # the state of the chosen area, for the "same state" tier
            states = {str(h.get("state") or "").strip().casefold() for h in self.metadata
                      if str(h.get("city") or "").strip() in area}
            state_cf = next(iter(states), "") if len(states) == 1 else ""
        eligible = [h for h in self.metadata if self.filter.specialty_evidence(h, specialty)]
        found = [(h, t) for h in eligible if (t := self._tier(h, area, state_cf if area is None else "")) == "area"]
        if not self.tiers or len(found) >= MIN_CANDIDATES:
            return found
        ids = {h["hospital_id"] for h, _ in found}
        if area is not None and state_cf:
            found += [(h, "state") for h in eligible if h["hospital_id"] not in ids
                      and str(h.get("state") or "").strip().casefold() == state_cf]
            ids = {h["hospital_id"] for h, _ in found}
        if len(found) < MIN_CANDIDATES:
            found += [(h, "anywhere") for h in eligible if h["hospital_id"] not in ids]
        return found

    def criteria(self, h: dict, specialty: str, tier: str, cap: CapabilityResult) -> dict[str, float]:
        nabh, jci = _positive(h.get("nabh_status")), _positive(h.get("jci_status"))
        evidence = self.filter.specialty_evidence(h, specialty)
        return {"capability": cap.score,
                "quality": 1.0 if nabh and jci else 0.7 if nabh or jci else 0.3,
                "evidence": 1.0 if evidence == VERIFIED else 0.5 if evidence == TEAM_LISTED else 0.0,
                "intl_care": 1.0 if _positive(h.get("international_patient_service")) else 0.3,
                "location": {"area": 1.0, "state": 0.6, "anywhere": 0.3}[tier]}

    def rank(self, specialty: str, procedure: str = "", city: str = "", state: str = "", top_k: int = 5) -> list[Ranked]:
        specialty = self.filter.normalize_specialty(specialty)
        pool = self.candidates(specialty, city, state)
        rows = []
        for h, tier in pool:
            cap = self.capability.judge(procedure, h) if procedure.strip() else CapabilityResult(SPECIALITY, note="no procedure mentioned")
            rows.append((h, tier, cap, self.criteria(h, specialty, tier, cap)))
        keys = list(self.weights)
        scores = topsis([[c[k] for k in keys] for *_, c in rows], [self.weights[k] for k in keys])
        ranked = [Ranked(h["hospital_id"], h["hospital_name"], h.get("city", ""), tier, s, c, cap)
                  for (h, tier, cap, c), s in zip(rows, scores)]
        ranked.sort(key=lambda r: (-r.score, r.hospital_name))
        return ranked[:top_k]
