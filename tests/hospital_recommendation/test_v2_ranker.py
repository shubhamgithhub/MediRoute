"""Step 2 v2 proof of concept: capability methods, guards, TOPSIS and location tiers (no network)."""

import pytest

from mediroute.hospital_recommendation.v2.capability import (
    EXACT,
    RELATED,
    SPECIALITY,
    LLMCapability,
    RuleCapability,
)
from mediroute.hospital_recommendation.v2.ranker import WEIGHTS, V2Ranker, topsis
from mediroute.specialty_routing.step1.ollama_client import LLMCall

HOSPITAL = {"hospital_id": "H1", "hospital_name": "Heart Care", "procedures": "TAVR; Robotic CABG; Kidney Transplant",
            "subspecialties": "Interventional Cardiology"}


@pytest.mark.parametrize("procedure, level", [
    ("heart bypass surgery", RELATED),          # bypass <-> CABG synonym, but "heart" is not in "Robotic CABG"
    ("kidney transplant", EXACT),
    ("renal transplant", EXACT),                # renal <-> kidney
    ("valve replacement through a catheter", SPECIALITY),  # rules cannot see TAVR = valve replacement
])
def test_rules(procedure, level):
    assert RuleCapability().judge(procedure, HOSPITAL).level == level


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def generate_json(self, prompt, schema, purpose):
        return LLMCall(True, parsed=dict(self.reply), details={"cost": 0.0001})


def test_llm_exact_when_the_quoted_item_is_listed():
    llm = LLMCapability(client=FakeClient({"level": "exact", "item": "TAVR", "field": "procedures", "reason": "TAVR is it"}))
    llm.MIN_SECONDS_BETWEEN_CALLS = 0
    assert llm.judge("valve replacement through a catheter", HOSPITAL).level == EXACT


@pytest.mark.parametrize("reply", [
    {"level": "exact", "item": "Valve Replacement", "field": "procedures", "reason": ""},  # invented item
    {"level": "exact", "item": "TAVR", "field": "subspecialties", "reason": ""},          # wrong field
    {"level": "none", "item": "", "field": "", "reason": ""},
])
def test_llm_guard_falls_back_to_speciality(reply):
    llm = LLMCapability(client=FakeClient(reply))
    llm.MIN_SECONDS_BETWEEN_CALLS = 0
    assert llm.judge("valve replacement", HOSPITAL).level == SPECIALITY


def test_topsis_prefers_the_capable_hospital():
    keys = list(WEIGHTS)
    capable = [1.0, 0.7, 0.5, 0.3, 1.0]
    accredited_only = [0.3, 1.0, 1.0, 1.0, 1.0]
    scores = topsis([capable, accredited_only], [WEIGHTS[k] for k in keys])
    assert scores[0] > scores[1]


def _h(hid, city, state, spec="Cardiology"):
    return {"hospital_id": hid, "hospital_name": hid, "city": city, "state": state, "verified_specialties": spec,
            "team_claimed_specialties": "", "procedures": "", "subspecialties": "", "nabh_status": "Accredited",
            "jci_status": "", "international_patient_service": ""}


def test_location_tiers_widen_only_when_the_area_is_too_small():
    meta = [_h("A", "Pune", "Maharashtra"), _h("B", "Nagpur", "Maharashtra"), _h("C", "Nagpur", "Maharashtra"),
            _h("D", "Chennai", "Tamil Nadu")]
    strict = V2Ranker(meta, RuleCapability(), tiers=False).rank("Cardiology", city="Pune")
    assert [r.hospital_id for r in strict] == ["A"]
    tiered = V2Ranker(meta, RuleCapability(), tiers=True).rank("Cardiology", city="Pune")
    assert {r.hospital_id for r in tiered} == {"A", "B", "C"}           # same state added, not Chennai
    assert tiered[0].hospital_id == "A" and tiered[0].tier == "area"    # the local one ranks first
