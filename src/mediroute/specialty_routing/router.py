from __future__ import annotations

import csv
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

logger = logging.getLogger("mediroute")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(
        PROJECT_ROOT / "logs" / "mediroute.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None

try:
    from transformers import pipeline
except Exception:  # pragma: no cover
    pipeline = None


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402
TAXONOMY_DIR = PROJECT_ROOT / "data" / "medical_taxonomy"

SPECIALTY_CARE_MAP = {
    "cardiology": "Cardiac Care",
    "cardiothoracic surgery": "Cardiac Surgery Care",
    "ophthalmology": "Eye Care",
    "orthopaedics": "Musculoskeletal Care",
    "pulmonology": "Respiratory Care",
    "endocrinology": "Hormonal & Metabolic Care",
    "gastroenterology": "Digestive Care",
    "neurology": "Neurological Care",
    "dermatology": "Skin Care",
    "ent": "Ear, Nose & Throat Care",
    "emergency medicine": "Urgent Care",
    "gynecology": "Women’s Health Care",
    "obstetrics & gynecology": "Women’s Health Care",
    "urology": "Urological Care",
    "psychiatry": "Mental Health Care",
    "nephrology": "Kidney Care",
    "hematology": "Blood Care",
    "oncology": "Cancer Care",
    "pediatric cardiology": "Pediatric Cardiac Care",
    "reproductive medicine": "Fertility Care",
    "general medicine": "Primary Care",
    "primary care": "Primary Care",
    "internal medicine": "Primary Care",
}

SPECIALTY_KEYWORDS: dict[str, list[str]] = {
    "Cardiology": [
        "chest pain", "heart", "palpitations", "arrhythmia", "tachycardia",
        "shortness of breath", "blood pressure", "hypertension", "chest discomfort",
        "angina", "cardiac"
    ],
    "Ophthalmology": [
        "blurred vision", "vision", "eye pain", "red eye", "floaters",
        "eye irritation", "glaucoma", "retina", "ocular", "cataract"
    ],
    "Orthopaedics": [
        "knee pain", "back pain", "joint pain", "bone", "fracture", "ankle",
        "hip pain", "muscle pain", "shoulder pain", "spine"
    ],
    "Pulmonology": [
        "cough", "wheezing", "breathlessness", "asthma", "lung", "respiratory",
        "shortness of breath", "bronchitis"
    ],
    "Endocrinology": [
        "diabetes", "thyroid", "hormone", "insulin", "fatigue", "weight gain",
        "metabolic", "blood sugar"
    ],
    "Gastroenterology": [
        "stomach pain", "acid reflux", "indigestion", "bloating", "diarrhea",
        "liver", "gastrointestinal", "abdomen"
    ],
    "Neurology": [
        "headache", "migraine", "dizziness", "seizure", "numbness", "brain",
        "stroke", "memory loss", "tingling"
    ],
    "Dermatology": [
        "rash", "skin", "itching", "eczema", "acne", "hives", "dermatitis"
    ],
    "ENT": [
        "ear pain", "hearing loss", "nasal congestion", "sore throat", "sinus",
        "tonsils", "voice change", "ear infection"
    ],
    "Emergency Medicine": [
        "severe pain", "emergency", "trauma", "bleeding", "unconscious", "accident"
    ],
    "Obstetrics & Gynecology": [
        "pregnancy", "menstrual", "pelvic pain", "ovarian", "gyne", "fertility"
    ],
    "Urology": [
        "urinary", "kidney stones", "bladder", "prostate", "urination"
    ],
    "Psychiatry": [
        "anxiety", "depression", "panic", "sleep issues", "mental health", "stress"
    ],
    "Nephrology": [
        "kidney", "dialysis", "renal", "urine infection", "swollen feet"
    ],
    "Oncology": [
        "cancer", "tumor", "mass", "chemotherapy", "oncology", "malignancy"
    ],
    "General Medicine": [
        "fever", "fatigue", "general weakness", "illness", "routine checkup"
    ],
}


class SpecialtyRAGRouter:
    def __init__(self) -> None:
        self.project_root = PROJECT_ROOT
        self.taxonomy_dir = TAXONOMY_DIR
        self.labels = self._load_specialty_labels()
        self.semantic_model = None
        self.zero_shot_pipeline = None
        self.ollama_model = self._detect_ollama_model()

    def _detect_ollama_model(self) -> str | None:
        base_url = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434")
        preferred_models = [
            "llama3.2",
            "llama3.1",
            "mistral",
            "qwen2.5",
            "qwen2",
            "phi3",
            "deepseek-r1",
        ]

        try:
            with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except Exception:
            return None

        available = payload.get("models", []) if isinstance(payload, dict) else []
        known_names = []
        for model in available:
            name = str(model.get("name") or "").strip()
            if name:
                known_names.append(name)

        for preferred in preferred_models:
            for available_name in known_names:
                if available_name.lower().startswith(preferred.lower()):
                    return available_name

        if known_names:
            return known_names[0]

        return None

    def _build_ollama_prompt(self, query: str, candidates: list[str]) -> str:
        candidate_list = ", ".join(candidates[:12])
        return (
            "You are a clinical routing specialist. Choose the single best medical specialty "
            "for the patient query using only the supplied specialty list. "
            "Return valid JSON only with keys: relevantSpecialty, careCategory, confidence, "
            "reasoning, matched_terms. Keep confidence between 0 and 1.\n\n"
            f"Patient query: {query}\n\nAvailable specialties: {candidate_list}"
        )

    def _parse_ollama_response(self, raw_response: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not raw_response:
            return fallback

        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                return fallback
            try:
                parsed = json.loads(match.group(0))
            except Exception:
                return fallback

        specialty = str(parsed.get("relevantSpecialty") or parsed.get("specialty") or fallback["relevantSpecialty"]).strip()
        care = str(parsed.get("careCategory") or SPECIALTY_CARE_MAP.get(specialty.lower(), "Primary Care")).strip()
        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence)
        except Exception:
            confidence = fallback["confidence"]
        confidence = max(0.0, min(1.0, confidence))

        return {
            "relevantSpecialty": specialty,
            "careCategory": care,
            "confidence": round(confidence, 2),
            "reasoning": parsed.get("reasoning") or fallback["reasoning"],
            "matched_terms": parsed.get("matched_terms") or fallback["matched_terms"],
            "requires_human_review": bool(parsed.get("requires_human_review", fallback["requires_human_review"])),
        }

    def _call_ollama(self, query: str, candidates: list[str]) -> dict[str, Any] | None:
        if not self.ollama_model:
            logger.info("LLM not available: no Ollama model detected for specialty routing.")
            return None

        base_url = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434")
        prompt = self._build_ollama_prompt(query, candidates)
        logger.info("LLM call starting for specialty routing with model=%s", self.ollama_model)
        logger.info("LLM prompt: %s", prompt)

        payload = json.dumps(
            {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                json_payload = json.loads(raw)
                response_text = str(json_payload.get("response") or "")
                logger.info("LLM raw response: %s", response_text)
        except Exception as exc:
            logger.exception("LLM call failed while routing specialty for query: %s", query)
            return None

        if not response_text:
            logger.warning("LLM returned empty response for query: %s", query)
            return None

        fallback = self._rule_based_match(query)
        parsed = self._parse_ollama_response(response_text, fallback)
        logger.info("LLM final parsed output handling: %s", parsed)
        return parsed

    def _initialize_models(self) -> None:
        if SentenceTransformer is not None:
            try:
                self.semantic_model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2"
                )
            except Exception:
                self.semantic_model = None

        if pipeline is not None:
            try:
                self.zero_shot_pipeline = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                )
            except Exception:
                self.zero_shot_pipeline = None

    def _load_specialty_labels(self) -> list[str]:
        labels = []

        try:
            with (self.taxonomy_dir / "specialty_vocabulary.csv").open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    specialty = (row.get("canonical_specialty") or "").strip()
                    if specialty:
                        labels.append(specialty)
        except Exception:
            labels = sorted(SPECIALTY_KEYWORDS.keys())

        seen: set[str] = set()
        ordered: list[str] = []
        for label in labels:
            cleaned = label.strip()
            if cleaned and cleaned.lower() not in seen:
                ordered.append(cleaned)
                seen.add(cleaned.lower())

        if not ordered:
            ordered = sorted(SPECIALTY_KEYWORDS.keys())

        return ordered

    def _normalize_query(self, query: str) -> str:
        text = query or ""
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text.lower()

    def _retrieve_candidates(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        normalized = self._normalize_query(query)
        if not normalized:
            return []

        if not self.semantic_model:
            return [
                {"specialty": label, "score": 1.0}
                for label in self.labels[:top_k]
            ]

        candidate_docs = []
        for label in self.labels:
            doc_text = self._describe_specialty(label)
            candidate_docs.append({"label": label, "text": doc_text})

        embeddings = self.semantic_model.encode(
            [normalized] + [doc["text"] for doc in candidate_docs],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        query_embedding = embeddings[0]
        doc_embeddings = embeddings[1:]

        similarities = []
        for index, doc in enumerate(candidate_docs):
            score = float(
                self._cosine_similarity(query_embedding, doc_embeddings[index])
            )
            similarities.append({"specialty": doc["label"], "score": score})

        similarities.sort(key=lambda item: item["score"], reverse=True)
        return similarities[:top_k]

    @staticmethod
    def _cosine_similarity(vec_a: Any, vec_b: Any) -> float:
        a = vec_a.astype(float)
        b = vec_b.astype(float)
        denom = (sum(a * a) ** 0.5) * (sum(b * b) ** 0.5)
        if denom == 0:
            return 0.0
        return float(sum(a * b) / denom)

    def _describe_specialty(self, specialty: str) -> str:
        specialty_norm = specialty.lower()
        alias_terms = []
        for label, keywords in SPECIALTY_KEYWORDS.items():
            if specialty_norm == label.lower() or specialty_norm in label.lower():
                alias_terms.extend(keywords)
                break

        if not alias_terms:
            alias_terms = [specialty.lower()]

        return f"{specialty}. Symptoms: {', '.join(alias_terms[:6])}."

    @staticmethod
    def _keyword_matches(normalized: str, keyword: str) -> bool:
        canonical = keyword.lower().strip()
        if not canonical:
            return False
        parts = re.findall(r"[a-z0-9]+", canonical)
        if not parts:
            return canonical in normalized
        if len(parts) == 1:
            return parts[0] in normalized
        return all(part in normalized for part in parts)

    def _rule_based_match(self, query: str) -> dict[str, Any]:
        logger.info("Input received for specialty routing: %s", query)
        normalized = self._normalize_query(query)
        logger.info("Normalizing and querying specialty taxonomy for: %s", normalized)
        if not normalized:
            result = {
                "relevantSpecialty": "General Medicine",
                "careCategory": "Primary Care",
                "confidence": 0.3,
                "reasoning": ["No symptom terms were detected."],
                "matched_terms": [],
                "requires_human_review": True,
            }
            logger.info("Rule-based fallback result: %s", result)
            return result

        best_label = "General Medicine"
        best_score = 0.0
        matches: list[str] = []

        for specialty, keywords in SPECIALTY_KEYWORDS.items():
            score = 0
            matched = []
            for keyword in keywords:
                if self._keyword_matches(normalized, keyword):
                    score += 1
                    matched.append(keyword)
            if score > best_score:
                best_score = score
                best_label = specialty
                matches = matched

        if best_score == 0:
            best_label = "General Medicine"
            matches = []

        care_category = SPECIALTY_CARE_MAP.get(best_label.lower(), "Primary Care")
        result = {
            "relevantSpecialty": best_label,
            "careCategory": care_category,
            "confidence": min(0.92, 0.45 + (best_score * 0.14)),
            "reasoning": [
                f"Matched symptom keywords: {', '.join(matches[:3]) or 'general query'}"
            ],
            "matched_terms": matches[:5],
            "requires_human_review": best_score <= 1,
        }
        logger.info("Rule-based specialty match: %s", result)
        return result

    def infer(self, query: str) -> dict[str, Any]:
        logger.info("Dispatching specialty inference pipeline for query: %s", query)
        if not query or not str(query).strip():
            result = {
                "relevantSpecialty": "General Medicine",
                "careCategory": "Primary Care",
                "confidence": 0.2,
                "reasoning": ["No patient input was provided."],
                "matched_terms": [],
                "requires_human_review": True,
            }
            logger.info("Output handling for empty query: %s", result)
            return result

        rule_result = self._rule_based_match(query)

        try:
            if self.zero_shot_pipeline is None and self.semantic_model is None:
                self._initialize_models()
        except Exception:
            pass

        candidates = self._retrieve_candidates(query, top_k=5)
        labels = [item["specialty"] for item in candidates if item.get("specialty")]
        if not labels:
            labels = self.labels[:5]
        logger.info("Candidate specialties queried from taxonomy: %s", labels)

        ollama_result = self._call_ollama(query, labels)
        if ollama_result is not None:
            logger.info("Output handling: returning LLM-based specialty result: %s", ollama_result)
            return ollama_result

        if self.zero_shot_pipeline is None and self.semantic_model is None:
            logger.info("Output handling: returning rule-based fallback result: %s", rule_result)
            return rule_result

        if self.zero_shot_pipeline is None:
            logger.info("Output handling: returning rule-based fallback result: %s", rule_result)
            return rule_result

        if len(labels) < 2:
            logger.info("Output handling: returning rule-based fallback result: %s", rule_result)
            return rule_result

        try:
            result = self.zero_shot_pipeline(
                query,
                candidate_labels=labels,
                multi_label=False,
            )
            result_dict = result if isinstance(result, dict) else {}
            labels_out = result_dict.get("labels") or []
            scores_out = result_dict.get("scores") or [0.0]
            if not labels_out:
                raise ValueError("Zero-shot pipeline returned no labels")
            top_label = labels_out[0]
            top_score = float(scores_out[0])
            care_category = SPECIALTY_CARE_MAP.get(top_label.lower(), "Primary Care")
            matched_terms = []
            normalized_query = self._normalize_query(query)
            for keyword in SPECIALTY_KEYWORDS.get(top_label, []):
                if self._keyword_matches(normalized_query, keyword):
                    matched_terms.append(keyword)

            final_result = {
                "relevantSpecialty": top_label,
                "careCategory": care_category,
                "confidence": round(min(0.99, max(top_score, rule_result["confidence"])), 2),
                "reasoning": [
                    f"Matched specialty keywords: {', '.join(matched_terms[:3]) or 'retrieved specialty context'}",
                    "This routing was selected from locally retrieved specialty taxonomy evidence."
                ],
                "matched_terms": matched_terms[:5],
                "requires_human_review": top_score < 0.4,
            }
            logger.info("Output handling: returning zero-shot specialty result: %s", final_result)
            return final_result
        except Exception:
            logger.exception("Zero-shot specialty route failed; using rule-based fallback.")
            logger.info("Output handling: returning rule-based fallback result: %s", rule_result)
            return rule_result


def rule_based_specialty_inference(query: str) -> dict[str, Any]:
    return SpecialtyRAGRouter()._rule_based_match(query)


def infer_medical_context_from_query(query: str) -> dict[str, Any]:
    return SpecialtyRAGRouter().infer(query)
