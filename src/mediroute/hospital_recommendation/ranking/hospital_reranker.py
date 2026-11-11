"""Adds small, transparent bonuses to the semantic score; every bonus becomes a ranking reason.

Fields come from data/processed/hospitals.csv. Values use the hospital master's formats
(Accredited / Not listed, Available / Not found on website, Verified / Partially verified /
Needs verification, High / Medium / Low); the older team-sheet spellings (Verified, Yes, 2/3)
are still understood.
"""

import re

PROCEDURE_STOPWORDS = {"surgery", "surgeries", "treatment", "procedure", "procedures", "therapy", "and", "the",
                       "of", "for", "with", "total", "robotic", "minimally", "invasive", "advanced", "complex"}
# patient wording -> hospital wording that means the same procedure
PROCEDURE_SYNONYMS = {"replacement": "arthroplasty", "arthroplasty": "replacement", "bypass": "cabg",
                      "cabg": "bypass", "kidney": "renal", "renal": "kidney", "angioplasty": "pci", "pci": "angioplasty"}
EVIDENCE_LEVEL = {"high": 3, "medium": 2, "low": 1}


class HospitalReranker:
    """Adds small transparent business-rule bonuses to semantic similarity."""

    POSITIVE_VALUES = {
        "yes", "verified", "active", "accredited", "true", "certified",
        "positive", "available", "accredited by nabh", "accredited by jci",
    }

    def _is_positive(self, value):
        if value is None:
            return False
        text = str(value).strip().casefold()
        if text in {"", "no", "not claimed", "not listed", "false", "unknown", "none", "null", "na",
                    "needs verification", "not found on website", "not found in nabh directory"}:
            return False
        return (
            text in self.POSITIVE_VALUES
            or text.startswith("verified")
            or text.startswith("accredited")
            or text.endswith("verified") and not text.startswith("partially")
            or text.endswith("accredited")
        )

    def _split_values(self, value, separator=";"):
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        return [item.strip() for item in text.split(separator) if item.strip()]

    @staticmethod
    def _procedure_words(text):
        words = {w for w in re.findall(r"[a-z0-9]+", str(text).casefold()) if w not in PROCEDURE_STOPWORDS}
        return words | {PROCEDURE_SYNONYMS[w] for w in words if w in PROCEDURE_SYNONYMS}

    def _match_procedure(self, patient_procedure, hospital_procedures):
        """A hospital procedure matches when it contains all the patient's key words (or synonyms):
        'CABG' matches 'Robotic CABG', 'knee replacement' matches 'Total Knee Arthroplasty'."""
        wanted = {w for w in re.findall(r"[a-z0-9]+", patient_procedure.casefold()) if w not in PROCEDURE_STOPWORDS}
        if not wanted:
            return None
        for hospital_procedure in hospital_procedures:
            have = self._procedure_words(hospital_procedure)
            if all(w in have or PROCEDURE_SYNONYMS.get(w) in have for w in wanted):
                return hospital_procedure
        return None

    @staticmethod
    def _evidence_quality(value):
        text = str(value or "").strip().casefold()
        if text in EVIDENCE_LEVEL:
            return EVIDENCE_LEVEL[text]
        try:
            return float(text)
        except ValueError:
            return 0.0

    def rerank(self, results, patient_procedures=None, top_k=None):
        patient_procedures = [
            str(procedure).strip()
            for procedure in (patient_procedures or [])
            if str(procedure).strip()
        ]
        reranked = []

        for result in results:
            ranking_reasons = []
            bonus = 0.0

            # speciality: confirmed on the hospital's website, or only listed by the team sheet
            evidence = result.get("specialty_evidence")
            if evidence == "website":
                bonus += 0.04
                ranking_reasons.append("Speciality confirmed on the hospital's website")
            elif evidence == "team list":
                ranking_reasons.append("Speciality listed in the team's hospital sheet (not yet confirmed on the website)")

            hospital_procedures = self._split_values(result.get("procedures") or result.get("verified_procedures"))
            matched_procedures = []
            for patient_procedure in patient_procedures:
                hit = self._match_procedure(patient_procedure, hospital_procedures)
                if hit and hit not in matched_procedures:
                    matched_procedures.append(hit)
            if matched_procedures:
                bonus += min(0.08, 0.04 * len(matched_procedures))
                unverified = " (team list, not verified)" if result.get("detail_source") else ""
                ranking_reasons.append("Offers " + ", ".join(matched_procedures) + unverified)

            verification = str(result.get("verification_status") or "").strip().casefold()
            if verification == "verified":
                bonus += 0.03
                ranking_reasons.append("Hospital details verified (NABH / JCI / website)")
            elif verification == "partially verified":
                bonus += 0.015
                ranking_reasons.append("Hospital details partly verified")
            if self._is_positive(result.get("nabh_status")):
                bonus += 0.02
                ranking_reasons.append("NABH accredited")
            if self._is_positive(result.get("jci_status")):
                bonus += 0.02
                ranking_reasons.append("JCI accredited")
            if self._is_positive(result.get("international_patient_service")):
                bonus += 0.02
                ranking_reasons.append("International patient services")

            evidence_quality = self._evidence_quality(result.get("evidence_quality_score"))
            evidence_bonus = min(0.03, max(0.0, evidence_quality / 3.0) * 0.03)
            if evidence_bonus > 0:
                bonus += evidence_bonus
                if evidence_quality >= 3:
                    ranking_reasons.append("Strong evidence for the hospital's details")

            business_bonus = min(0.20, bonus)
            semantic_score = float(result["semantic_score"])
            reranked_result = dict(result)
            reranked_result["semantic_score"] = semantic_score
            reranked_result["business_bonus"] = round(business_bonus, 6)
            reranked_result["final_score"] = round(semantic_score + business_bonus, 6)
            reranked_result["matched_procedures"] = matched_procedures
            reranked_result["ranking_reasons"] = ranking_reasons or ["Semantic specialty and medical relevance"]
            reranked.append(reranked_result)

        reranked.sort(key=lambda item: item["final_score"], reverse=True)
        for final_rank, result in enumerate(reranked, start=1):
            result["final_rank"] = final_rank

        if top_k is not None:
            return reranked[:max(0, top_k)]
        return reranked
