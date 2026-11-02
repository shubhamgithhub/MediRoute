class HospitalReranker:
    """Adds small transparent business-rule bonuses to semantic similarity."""

    POSITIVE_VALUES = {
        "yes", "verified", "active", "accredited", "true",
        "positive", "available", "accredited by nabh", "accredited by jci",
    }

    def _is_positive(self, value):
        if value is None:
            return False
        text = str(value).strip().casefold()
        if text in {"", "no", "not claimed", "false", "unknown", "none", "null"}:
            return False
        return (
            text in self.POSITIVE_VALUES
            or text.startswith("verified")
            or text.startswith("accredited")
            or text.endswith("verified")
            or text.endswith("accredited")
        )

    def _split_values(self, value, separator=";"):
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        return [item.strip() for item in text.split(separator) if item.strip()]

    def rerank(self, results, patient_procedures=None, top_k=None):
        patient_procedures = [
            str(procedure).strip().casefold()
            for procedure in (patient_procedures or [])
            if str(procedure).strip()
        ]
        reranked = []

        for result in results:
            ranking_reasons = []
            matched_procedures = []
            hospital_procedures = self._split_values(result.get("verified_procedures"))

            for patient_procedure in patient_procedures:
                matched_hospital_procedure = next(
                    (
                        hospital_procedure.strip()
                        for hospital_procedure in hospital_procedures
                        if patient_procedure == hospital_procedure.strip().casefold()
                    ),
                    None,
                )
                if matched_hospital_procedure or any(
                    patient_procedure == hospital_procedure.strip().casefold()
                    for hospital_procedure in hospital_procedures
                ):
                    matched_procedures.append(matched_hospital_procedure or patient_procedure)

            procedure_bonus = min(0.08, 0.04 * len(set(matched_procedures)))
            bonus = procedure_bonus
            if matched_procedures:
                ranking_reasons.append(
                    "Matched verified patient procedures: " + ", ".join(sorted(set(matched_procedures)))
                )

            if self._is_positive(result.get("verification_status")):
                bonus += 0.03
                ranking_reasons.append("Verified hospital")
            if self._is_positive(result.get("nabh_status")):
                bonus += 0.02
                ranking_reasons.append("NABH verified/accredited")
            if self._is_positive(result.get("jci_status")):
                bonus += 0.02
                ranking_reasons.append("JCI verified/accredited")
            if self._is_positive(result.get("international_patient_service")):
                bonus += 0.02
                ranking_reasons.append("International patient services available")

            evidence_bonus = 0.0
            try:
                evidence_quality = float(result.get("evidence_quality_score"))
                if evidence_quality >= 0:
                    evidence_bonus = min(0.03, max(0.0, evidence_quality / 5.0) * 0.03)
            except (TypeError, ValueError):
                evidence_quality = 0.0
            if evidence_bonus > 0:
                bonus += evidence_bonus
                ranking_reasons.append("Strong evidence quality score")

            business_bonus = min(0.20, bonus)
            semantic_score = float(result["semantic_score"])
            final_score = semantic_score + business_bonus
            reranked_result = dict(result)
            reranked_result["semantic_score"] = semantic_score
            reranked_result["business_bonus"] = round(business_bonus, 6)
            reranked_result["final_score"] = round(final_score, 6)
            reranked_result["matched_procedures"] = sorted(
                set(matched_procedure for matched_procedure in matched_procedures if matched_procedure)
            )
            reranked_result["ranking_reasons"] = ranking_reasons or ["Semantic specialty and medical relevance"]
            reranked.append(reranked_result)

        reranked.sort(key=lambda item: item["final_score"], reverse=True)
        for final_rank, result in enumerate(reranked, start=1):
            result["final_rank"] = final_rank

        if top_k is not None:
            return reranked[:max(0, top_k)]
        return reranked
