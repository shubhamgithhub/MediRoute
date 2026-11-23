"""Step 1 pipeline: patient text -> suggested speciality to search.

    1 read & protect      code      redact phone numbers, e-mails, IDs
    2 emergency check     code      fixed rules -> emergency notice; a red flag (chest pain with
                                    breathlessness / racing heart / dizziness, stroke signs, loss of
                                    sight, confusion, heavy bleeding...) -> Emergency Medicine
                                    ("emergency_rule", no LLM call); suicidal intent keeps routing
    3 extract evidence    LLM+code  conditions / procedures / body parts, named diagnoses, and a
                                    body-area tag per symptom; kept only if in the text
    3b body areas         code      no named diagnosis or procedure and symptoms in 2+ body areas
                                    (body_area_tags.csv, neighbour pairs in body_area_neighbours.csv)
                                    -> ask which area; "More than one / whole body" or "Other / not
                                    sure" -> General Medicine ("multi_area_general_medicine")
    4 vote                V1 lookup (keyword + meaning search, fused) and V2 LLM (speciality list)
    5 decide              code      both voters agree -> answer ("agreement");
                          LLM judge they disagree -> a guarded LLM judge picks one of the two ("judge");
                                    no LLM -> the lookup voter answers alone ("lookup_only");
                                    the patient's body-area answer fits exactly one of the
                                    disputed specialities -> that one ("patient_answer");
                                    otherwise ask (General Medicine asks once before it is accepted)
    5b clarify            code      one short form (questions already answered are not asked again);
                                    answers are added and stages 3-5 re-run; if it is still open
                                    the user picks from a short list of the candidates (with
                                    descriptions; "something else" opens the full list)
    6 output              "Suggested speciality to search: X" + evidence + disclaimer

Every stage is logged with the request id (see trace.py).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from mediroute.common.specialties import (body_area_options, body_area_specialties, care_category,
                                          count_body_areas, get_specialty, specialty_names)
from mediroute.specialty_routing.step1.evidence import EVIDENCE_PROMPT_VERSION, EvidenceExtractor
from mediroute.specialty_routing.step1.judge import JUDGE_PROMPT_VERSION, LLMJudge
from mediroute.specialty_routing.step1.lookup import LookupIndex
from mediroute.specialty_routing.step1.ollama_client import LLMCall, OllamaClient, make_llm_client
from mediroute.specialty_routing.step1.protect import redact
from mediroute.specialty_routing.step1.safety import add_llm_self_harm, check_emergency, routes_to_emergency
from mediroute.specialty_routing.step1.trace import Step1Trace, log_patient_text, text_for_log
from mediroute.specialty_routing.step1.voters import HybridLookupVoter, LLMVoter, Vote
from mediroute.utils.logging_config import get_logger

MAX_CLARIFICATION_ROUNDS = 2
CATCH_ALL = "General Medicine"  # an answer of General Medicine asks one clarification round first
# decisions that mean "a speciality was suggested" (Step 2 can run); "majority" is the old name
ROUTED_DECISIONS = {"agreement", "judge", "lookup_only", "patient_answer", "user_selected", "majority",
                    "emergency_rule", "multi_area_general_medicine"}
EMERGENCY = "Emergency Medicine"
MULTI_AREA_MIN = 2  # body areas (after neighbour pairs) that make a symptom-only message ask
MULTI_AREA_ANSWER = "More than one / whole body"
NOT_SURE = "Other / not sure"
SHORTLIST_SIZE = 4  # specialities offered when the user picks
LLM_DOWN_NOTICE = ("The AI language model is not available on this server, so this suggestion comes from "
                   "the medical lookup only and may need an extra question.")
_logger = get_logger()
DISCLAIMER = ("Hospital discovery support only. This is a suggested speciality to search, "
              "not a diagnosis or medical advice. A doctor at the hospital confirms any treatment plan.")

BODY_AREAS = body_area_options()  # the body_area rows of specialty_mapping.csv, in file order
CLARIFICATION_FIELDS = [
    {"name": "body_area", "type": "select", "options": BODY_AREAS,
     "label": "Which part of the body is the problem in?"},
    {"name": "existing_diagnosis", "type": "text",
     "label": "Do you already have a diagnosis or a report finding?",
     "placeholder": "e.g. osteoarthritis of the knee, slipped disc L4-L5"},
    {"name": "recommended_procedure", "type": "text",
     "label": "Has a doctor recommended a treatment or procedure?",
     "placeholder": "e.g. knee replacement, bypass surgery"},
]


@dataclass
class Step1Input:
    text: str = ""
    report_text: str = ""
    clarification: dict[str, str] = field(default_factory=dict)
    clarification_round: int = 0  # how many clarification forms the user has already answered
    selected_specialty: str | None = None  # set when the user picks from the list
    parent_request_id: str | None = None  # links clarification rounds of one search
    debug: bool = False


def compose_text(inp: Step1Input) -> str:
    parts = [inp.text.strip()]
    if inp.report_text.strip():
        parts.append("Report:\n" + inp.report_text.strip())
    answers = inp.clarification or {}
    labels = {"body_area": "Body area", "existing_diagnosis": "Existing diagnosis",
              "recommended_procedure": "Recommended procedure"}
    lines = [f"{labels[k]}: {str(answers[k]).strip()}" for k in labels
             if str(answers.get(k) or "").strip() and str(answers.get(k)).strip() not in (NOT_SURE, MULTI_AREA_ANSWER)]
    if lines:
        parts.append("\n".join(lines))
    return "\n\n".join(p for p in parts if p)


def _llm_event(call: LLMCall | None, prompt: str, prompt_version: str) -> dict[str, Any]:
    if call is None:
        return {}
    return {
        "prompt_version": prompt_version,
        "prompt": prompt if log_patient_text() else f"<{len(prompt)} chars>",
        "ok": call.ok, "error": call.error, "duration_ms": call.duration_ms,
        "raw_response": call.raw_response, "parsed": call.parsed, **call.details,
    }


class Step1Pipeline:
    def __init__(self, index: LookupIndex | None = None, client: OllamaClient | None = None,
                 extractor: EvidenceExtractor | None = None, llm_voter: LLMVoter | None = None,
                 judge: LLMJudge | None = None) -> None:
        self.client = client or make_llm_client()
        self.index = index or LookupIndex()
        self.extractor = extractor or EvidenceExtractor(self.client)
        self.v1 = HybridLookupVoter(self.index)
        self.v3 = llm_voter or LLMVoter(self.client)  # the LLM voter (V2 in the trace)
        self.judge = judge or LLMJudge(index=self.index)
        self.ready = threading.Event()
        # hosted LLMs answer calls concurrently: V3 runs alongside evidence + V1 + V2
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="step1-v3")

    # ------------------------------------------------------------------ startup
    def warm_up(self, logger) -> None:
        """Load everything a request needs, so the first patient doesn't wait for it.

        Running each LLM prompt once also lets Ollama cache the long, fixed part of the prompts
        (the speciality list), which cuts the first V3 call from about 30 s to about 10 s on CPU.
        """
        try:
            self.index.ensure_embeddings()
            self.index.embedding_search("knee pain", k=1)  # loads the embedding model too
            logger.info("Step 1 lookup index ready: %d entries", len(self.index.entries))
        except Exception as exc:
            logger.warning("Step 1 embedding index failed to load (%s); V2 will be unavailable", exc)
        try:
            self.client.warm_up()
            if getattr(self.client, "needs_priming", True):  # local Ollama: cache the long prompts
                self.extractor.extract("knee pain")
                self.v3.vote("knee pain")
            logger.info("Step 1 LLM warm-up done: provider=%s model=%s %s", getattr(self.client, "provider", ""),
                        self.client.model, getattr(self.client, "key_info", "") or "")
        except Exception as exc:
            logger.warning(
                "\n" + "=" * 78 + "\n"
                "  Step 1 is running WITHOUT an LLM: %s\n"
                "  The app still works: evidence comes from patient-word matches, the LLM voter\n"
                "  abstains and the medical lookup answers alone, so it may ask more clarification\n"
                "  questions. Each request logs 'LLM unavailable'.\n"
                + "=" * 78, exc)
        self.ready.set()

    def llm_status(self) -> dict[str, Any]:
        status = getattr(self.client, "status", None)
        if status is None:  # a client without status() (e.g. a test fake) is assumed to work
            return {"provider": "custom", "model": getattr(self.client, "model", ""), "available": True, "reason": ""}
        return status()

    # ------------------------------------------------------------------ request
    def analyze(self, inp: Step1Input) -> dict[str, Any]:
        trace = Step1Trace(parent_request_id=inp.parent_request_id)

        # 1. read and protect ------------------------------------------------
        raw_text = compose_text(inp)
        text, redactions = redact(raw_text)
        trace.log("input", patient_text=text_for_log(text), report_chars=len(inp.report_text or ""),
                  clarification_answers=inp.clarification or {}, clarification_round=inp.clarification_round,
                  selected_specialty=inp.selected_specialty, redactions=redactions, debug=inp.debug)

        # 2. emergency check (rules) ------------------------------------------
        emergency = check_emergency(text)
        trace.log("emergency_check", method="deterministic_rules", **emergency)

        if not text.strip() and not inp.selected_specialty:
            return self._respond(trace, inp, "clarification_required", None, emergency, [], {},
                                 reason="No patient text was provided.")

        if routes_to_emergency(emergency) and not inp.selected_specialty:
            reason = ("The message describes warning signs that need emergency care now ("
                      + ", ".join(r.replace("_", " ") for r in emergency["matched_rules"]) + ").")
            trace.log("decision", method="emergency_rule", selected_specialty=EMERGENCY,
                      matched_rules=emergency["matched_rules"], reason=reason)
            return self._respond(trace, inp, "emergency_rule", EMERGENCY, emergency, [], {}, reason=reason)

        # user picked from the list after the clarification rounds ------------
        if inp.selected_specialty:
            chosen = get_specialty(inp.selected_specialty)
            if chosen:
                trace.log("decision", method="user_selected", selected_specialty=chosen.name,
                          reason="The user chose the speciality from the list.")
                return self._respond(trace, inp, "user_selected", chosen.name, emergency, [], {},
                                     reason="Chosen by you from the speciality list.")
            trace.log("decision", method="user_selected_invalid", value=inp.selected_specialty)

        # 3. evidence (LLM, then code check) ----------------------------------
        llm = self.llm_status()
        trace.log("llm_status", **llm)
        if not llm["available"]:
            _logger.warning("Step 1 request %s: LLM unavailable (%s); using keyword evidence and the lookup voter only",
                            trace.request_id, llm["reason"])
        v3_future, v3_started_ms = None, None
        if llm["available"] and getattr(self.client, "parallel_calls", False):
            v3_started_ms = trace.elapsed_ms()
            v3_future = self._pool.submit(self.v3.vote, text)
        evidence = self.extractor.extract(text)
        trace.evidence_kept = evidence.kept
        trace.log("llm_call", stage_for="evidence_extraction",
                  **_llm_event(evidence.llm_call, self.extractor.build_prompt(text), EVIDENCE_PROMPT_VERSION))
        trace.log("evidence", method=evidence.method, kept=evidence.kept, dropped=evidence.dropped,
                  routing_phrases=evidence.routing_phrases, checks=evidence.checks)

        # 3a. safety net: self-harm words the rules missed (LLM quote, checked against the text) ------
        checked = add_llm_self_harm(emergency, evidence.self_harm, text)
        if checked is not emergency:
            newly_acute = routes_to_emergency(checked) and not routes_to_emergency(emergency)
            emergency = checked
            trace.log("emergency_check", method="llm_self_harm_quote", quote=evidence.self_harm, **emergency)
            if newly_acute:
                reason = "The message describes an intent to end life now; this needs emergency care."
                trace.log("decision", method="emergency_rule", selected_specialty=EMERGENCY,
                          matched_rules=emergency["matched_rules"], reason=reason)
                return self._respond(trace, inp, "emergency_rule", EMERGENCY, emergency, evidence.phrases, {},
                                     reason=reason)

        # 3b. body areas (code) -------------------------------------------------
        answer = str((inp.clarification or {}).get("body_area") or "").strip()
        named = evidence.named_diagnoses + evidence.kept["procedures"]
        areas = count_body_areas({a["tag"] for a in evidence.symptom_areas})
        multi = not named and areas["count"] >= MULTI_AREA_MIN
        trace.log("area_check", tags=evidence.symptom_areas, named=named, areas=areas["areas"],
                  count=areas["count"], merged=areas["merged"], threshold=MULTI_AREA_MIN, multi_area=multi,
                  body_area_answer=answer)
        if answer == MULTI_AREA_ANSWER or (multi and answer == NOT_SURE):
            listed = ", ".join(areas["areas"]) or "more than one"
            reason = (f"Your symptoms involve several parts of the body ({listed}). A general physician can "
                      "examine you, find the cause and refer you to a specialist if needed.")
            trace.log("decision", method="multi_area_general_medicine", selected_specialty=CATCH_ALL,
                      evidence=evidence.phrases, reason=reason)
            return self._respond(trace, inp, "multi_area_general_medicine", CATCH_ALL, emergency,
                                 evidence.phrases, {}, reason=reason)
        if multi and not answer:
            reason = f"Your symptoms involve several parts of the body ({', '.join(areas['areas'])})."
            question = (f"Which part troubles you most? Choose \u201c{MULTI_AREA_ANSWER}\u201d if it is really "
                        "several; a general physician is then the right first stop.")
            trace.log("decision", method="clarification_required", selected_specialty=None, reason=reason,
                      next_round=inp.clarification_round + 1, why="multi_area")
            return self._respond(trace, inp, "clarification_required", None, emergency, evidence.phrases, {},
                                 reason=reason, clarification_message=question)

        if not evidence.routing_phrases:
            return self._ask_or_offer_choice(trace, inp, emergency, evidence.phrases, votes={},
                                             reason="No condition, procedure or body part was found in the text.")

        # 4. votes ------------------------------------------------------------
        votes: dict[str, Vote] = {}
        votes["V1"] = self.v1.vote(evidence.routing_phrases)
        trace.log("vote", voter=votes["V1"].voter, method="lookup_keyword_plus_meaning", top3=votes["V1"].top3,
                  ms=votes["V1"].ms, note=votes["V1"].note, hits=votes["V1"].hits[:48],
                  details=votes["V1"].details)
        votes["V2"] = v3_future.result() if v3_future else self.v3.vote(text)
        v2_event = _llm_event(votes["V2"].llm_call, self.v3._router.build_prompt(text), self.v3.prompt_version)
        if v3_future:
            v2_event.update(parallel=True, started_t_ms=v3_started_ms)
        trace.log("llm_call", stage_for="specialty_vote", **v2_event)
        trace.log("vote", voter=votes["V2"].voter, method="llm_constrained_choice", top3=votes["V2"].top3,
                  ms=votes["V2"].ms, ok=votes["V2"].ok, note=votes["V2"].note, hits=votes["V2"].hits)

        # 5. decide -----------------------------------------------------------
        lookup, llm_pick = votes["V1"].top1, votes["V2"].top1
        tops = {"V1": lookup, "V2": llm_pick}
        trace.log("votes_summary", top1_by_voter=tops, agree=bool(lookup and lookup == llm_pick))

        chosen, method, reason, agreeing = None, None, "", []
        if lookup and llm_pick and lookup == llm_pick:
            chosen, method, agreeing = lookup, "agreement", ["V1", "V2"]
            reason = "The medical lookup and the AI model agree, and the text contains supporting evidence."
        elif lookup and llm_pick and self._answer_decides(inp, [lookup, llm_pick]):
            chosen, method = self._answer_decides(inp, [lookup, llm_pick]), "patient_answer"
            agreeing = [k for k, v in tops.items() if v == chosen]
            reason = (f"The medical lookup suggested {lookup} and the AI model {llm_pick}; your answer "
                      f"\u201c{inp.clarification.get('body_area')}\u201d fits {chosen}.")
        elif lookup and llm_pick:
            verdict = self.judge.judge(text, evidence.routing_phrases, lookup, llm_pick)
            for call, prompt in zip(verdict.calls, verdict.prompts):
                trace.log("llm_call", stage_for="judge", **_llm_event(call, prompt, JUDGE_PROMPT_VERSION))
            trace.log("judge", **verdict.trace())
            if verdict.final:
                chosen, method = verdict.final, "judge"
                agreeing = [k for k, v in tops.items() if v == chosen]
                reason = (f"The medical lookup suggested {lookup} and the AI model {llm_pick}; the AI judge chose "
                          f"{chosen} from the evidence ({verdict.reason})").rstrip(" ()") + "."
            else:
                return self._ask_or_offer_choice(
                    trace, inp, emergency, evidence.phrases, votes,
                    reason=f"The medical lookup suggested {lookup} and the AI model {llm_pick}; "
                           f"one more detail will decide between them.")
        elif votes["V2"].ok and not llm_pick and lookup and self._answer_decides(inp, [lookup]):
            chosen, method, agreeing = lookup, "patient_answer", ["V1"]
            reason = (f"The medical lookup suggested {lookup}, and your answer "
                      f"\u201c{inp.clarification.get('body_area')}\u201d fits it.")
        elif votes["V2"].ok and not llm_pick:
            # The AI read the message and judged it too vague ("Unclear"): that is real information,
            # so ask the patient rather than let the lookup guess (portal benchmark: "pain" -> Cardiology).
            return self._ask_or_offer_choice(
                trace, inp, emergency, evidence.phrases, votes,
                reason="The AI model found the message too general to choose a speciality; "
                       "one more detail will help.")
        elif lookup and not llm_pick:
            # The AI is not available (error, timeout, no key): the lookup answers alone, with a notice.
            chosen, method, agreeing = lookup, "lookup_only", ["V1"]
            reason = "Suggested by the medical lookup; the AI model was not available."
        else:
            return self._ask_or_offer_choice(trace, inp, emergency, evidence.phrases, votes,
                                             reason="The evidence did not match a speciality in the medical lookup.")

        if chosen == CATCH_ALL and inp.clarification_round == 0:
            # General Medicine is the catch-all for vague symptoms; ask once before settling on it
            return self._ask_or_offer_choice(
                trace, inp, emergency, evidence.phrases, votes,
                reason=f"The best match is {CATCH_ALL}, which usually means the message is too general. "
                       "One more detail can point to a specialist.")

        trace.log("decision", method=method, selected_specialty=chosen, agreeing_voters=agreeing,
                  evidence=evidence.phrases, reason=reason)
        return self._respond(trace, inp, method, chosen, emergency, evidence.phrases, votes,
                             reason=reason, agreeing=agreeing)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _answer_decides(inp: Step1Input, candidates: list[str]) -> str | None:
        """The one candidate that fits the patient's body-area answer, else None. Only ever picks
        among specialities the voters already suggested; it never adds a new one."""
        area = body_area_specialties((inp.clarification or {}).get("body_area", ""))
        fitting = [c for c in dict.fromkeys(candidates) if c in area]
        return fitting[0] if len(fitting) == 1 else None

    @staticmethod
    def _open_fields(inp: Step1Input) -> list[dict]:
        answered = {k for k, v in (inp.clarification or {}).items() if str(v or "").strip()}
        return [f for f in CLARIFICATION_FIELDS if f["name"] not in answered]

    def _ask_or_offer_choice(self, trace, inp, emergency, evidence, votes, reason):
        # one form, then a short list: asking the same form again gives the voters nothing new
        offer_list = (inp.clarification_round >= MAX_CLARIFICATION_ROUNDS or not self._open_fields(inp)
                      or (inp.clarification_round >= 1 and self._candidates(votes)))
        if offer_list:
            trace.log("decision", method="needs_user_choice", selected_specialty=None, reason=reason,
                      rounds_answered=inp.clarification_round)
            return self._respond(trace, inp, "needs_user_choice", None, emergency, evidence, votes, reason=reason)
        trace.log("decision", method="clarification_required", selected_specialty=None, reason=reason,
                  next_round=inp.clarification_round + 1)
        return self._respond(trace, inp, "clarification_required", None, emergency, evidence, votes, reason=reason)

    def _candidates(self, votes: dict[str, Vote]) -> list[str]:
        """Each voter's first choice, then the rest of their top 3."""
        ordered: list[str] = [v.top1 for v in votes.values() if v.top1]
        for vote in votes.values():
            ordered += [name for name, _ in vote.top3]
        return list(dict.fromkeys(ordered))

    def _shortlist(self, inp: Step1Input, votes: dict[str, Vote]) -> list[str]:
        """What the user picks from: the voters' candidates that fit the body-area answer first,
        then the other candidates, then the area's specialities (when the voters found nothing)."""
        area = body_area_specialties((inp.clarification or {}).get("body_area", ""))
        candidates = self._candidates(votes)
        ordered = [c for c in candidates if c in area] + candidates + sorted(area)
        return list(dict.fromkeys(ordered))[:SHORTLIST_SIZE]

    def _respond(self, trace: Step1Trace, inp: Step1Input, decision: str, specialty: str | None,
                 emergency: dict, evidence: list[str], votes: dict[str, Vote], reason: str,
                 agreeing: list[str] | None = None, clarification_message: str | None = None) -> dict[str, Any]:
        spec = get_specialty(specialty) if specialty else None
        clarify = decision == "clarification_required"
        choose = decision == "needs_user_choice"
        shortlist = self._shortlist(inp, votes) if decision == "needs_user_choice" else []
        llm_ok = self.llm_status()["available"]
        response: dict[str, Any] = {
            "request_id": trace.request_id,
            "parent_request_id": inp.parent_request_id,
            "decision": decision,
            "suggested_specialty": specialty,
            "suggested_specialty_label": f"Suggested speciality to search: {specialty}" if specialty else None,
            "care_category": care_category(specialty) if specialty else None,
            "in_hospital_data": bool(spec and spec.in_hospital_data),
            "evidence": evidence,
            # by kind (conditions, procedures, body_parts, keyword_matches); Step 2 uses procedures
            "evidence_detail": trace.evidence_kept,
            "reason": reason,
            "emergency": emergency["is_emergency"],
            "emergency_message": emergency["message"],
            "clarification_required": clarify,
            "clarification": {
                "round": inp.clarification_round + 1,
                "max_rounds": MAX_CLARIFICATION_ROUNDS,
                "message": clarification_message or "We need a little more information to suggest the right speciality.",
                "fields": self._open_fields(inp),
            } if clarify else None,
            "user_choice": {
                "message": ("We could not match your description to one speciality with confidence. "
                            "Please choose the speciality you are looking for. These are the closest matches; "
                            "if none fits, choose \u201csomething else\u201d to see all specialities."),
                "shortlist": [{"name": n, "description": (get_specialty(n).description if get_specialty(n) else "")}
                              for n in shortlist],
                "suggested_first": shortlist,
                "options": shortlist + [n for n in specialty_names() if n not in shortlist],
            } if choose else None,
            "disclaimer": DISCLAIMER,
            "llm_available": llm_ok,
            "notice": None if llm_ok else LLM_DOWN_NOTICE,
            "latency_ms": trace.elapsed_ms(),
            # kept for the current frontend
            "relevantSpecialty": specialty,
            "careCategory": care_category(specialty) if specialty else None,
        }
        if inp.debug:
            response["debug"] = {
                "votes": {k: {"voter": v.voter, "top3": v.top3, "ok": v.ok, "note": v.note} for k, v in votes.items()},
                "agreeing_voters": agreeing or [],
                "trace_events": [e["stage"] for e in trace.events],
            }
        trace.log("response", decision=decision, suggested_specialty=specialty, evidence=evidence,
                  emergency=emergency["is_emergency"], clarification_required=clarify,
                  user_choice_offered=choose, total_ms=trace.elapsed_ms())
        return response
