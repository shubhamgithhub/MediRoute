"""The lookup list searched by voters V1 and V2: ICD-10-CM diagnoses + CGHS procedures + lay terms.

Each entry is a description with the speciality it maps to, via doctor-reviewable tables:

* ICD-10-CM 3- and 4-character categories (CDC 2026 order file, public domain), mapped by
  ``data/medical_taxonomy/icd10_block_specialty.csv`` (narrowest matching code range wins).
* CGHS procedures (Tier I rows of the CGHS_Data sheet), mapped by
  ``cghs_label_specialty.csv`` with name overrides from ``cghs_name_overrides.csv``.
* Lay terms: the patient-language keywords of each speciality in ``specialties.csv``.

Rows mapped to ``NONE`` (lab tests, imaging, dental, symptoms of abnormal findings...) are left
out: they are not routing evidence.

Build the list (writes data/medical_taxonomy/step1_lookup.csv)::

    python -m mediroute.specialty_routing.step1.lookup
"""

from __future__ import annotations

import csv
import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mediroute.common.specialties import specialty_names
from mediroute.utils.logging_config import get_logger
from mediroute.utils.paths import GENERATOR_INPUT_DIR, RAW_DATA_DIR, TAXONOMY_DIR, VECTOR_STORE_DIR

logger = get_logger()

LOOKUP_FILE = TAXONOMY_DIR / "step1_lookup.csv"
ICD_BLOCK_FILE = TAXONOMY_DIR / "icd10_block_specialty.csv"
CGHS_LABEL_FILE = TAXONOMY_DIR / "cghs_label_specialty.csv"
CGHS_OVERRIDE_FILE = TAXONOMY_DIR / "cghs_name_overrides.csv"
ICD_ORDER_FILE = RAW_DATA_DIR / "icd10cm_2026" / "extracted" / "icd10cm-order-2026.txt"
CGHS_WORKBOOK = GENERATOR_INPUT_DIR / "Hosp_Data_Final.xlsx"
EMBEDDING_CACHE = VECTOR_STORE_DIR / "step1_lookup_embeddings.npy"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class LookupEntry:
    entry_id: str
    source: str  # "icd10cm" or "cghs"
    code: str
    text: str
    specialty: str


# ---------------------------------------------------------------------------
# Building the list
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _check_specialty(value: str, where: str) -> str:
    value = value.strip()
    if value != "NONE" and value not in set(specialty_names()):
        raise ValueError(f"{where}: '{value}' is not a canonical speciality or NONE")
    return value


def icd_specialty_for(code: str, blocks: list[dict]) -> str | None:
    """Speciality of an ICD-10-CM code from the narrowest block range that contains it."""
    category = code[:3].upper()
    candidates = [b for b in blocks if b["code_from"] <= category <= b["code_to"]]
    if not candidates:
        return None
    # narrowest range first; ranges are compared on their 3-character bounds
    best = min(candidates, key=lambda b: (_range_width(b["code_from"], b["code_to"]), b["code_from"]))
    return best["specialty"]


def _range_width(start: str, end: str) -> int:
    def as_number(code: str) -> int:
        letter = ord(code[0]) - ord("A")
        digits = int(re.sub(r"\D", "0", code[1:3]))
        return letter * 100 + digits
    return as_number(end) - as_number(start)


def _icd_entries() -> list[LookupEntry]:
    if not ICD_ORDER_FILE.exists():
        logger.warning("ICD-10-CM order file not found at %s; lookup list will be CGHS only", ICD_ORDER_FILE)
        return []
    blocks = [
        {**row, "code_from": row["code_from"].strip().upper(), "code_to": row["code_to"].strip().upper(),
         "specialty": _check_specialty(row["specialty"], f"{ICD_BLOCK_FILE.name} {row['code_from']}")}
        for row in _read_csv(ICD_BLOCK_FILE)
    ]
    entries, seen = [], set()
    with ICD_ORDER_FILE.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            code = line[6:13].strip()
            if len(code) not in (3, 4) or code[0] in "VWXY":  # external causes are not routing evidence
                continue
            description = line[77:].strip() or line[16:76].strip()
            specialty = icd_specialty_for(code, blocks)
            if not specialty or specialty == "NONE":
                continue
            key = (description.lower(), specialty)
            if key in seen:
                continue
            seen.add(key)
            entries.append(LookupEntry(f"icd:{code}", "icd10cm", code, description, specialty))
    return entries


def cghs_specialty_for(name: str, label: str, labels: dict[str, str], overrides: list[dict]) -> str | None:
    lowered = name.lower()
    for row in overrides:  # first match wins, so specific phrases come first in the file
        if row["name_contains"].strip().lower() in lowered:
            return row["specialty"]
    return labels.get(label.strip())


def _cghs_entries() -> list[LookupEntry]:
    from openpyxl import load_workbook

    labels = {row["cghs_label"].strip(): _check_specialty(row["specialty"], f"{CGHS_LABEL_FILE.name} {row['cghs_label']}")
              for row in _read_csv(CGHS_LABEL_FILE)}
    overrides = [{**row, "specialty": _check_specialty(row["specialty"], CGHS_OVERRIDE_FILE.name)}
                 for row in _read_csv(CGHS_OVERRIDE_FILE)]
    sheet = load_workbook(CGHS_WORKBOOK, data_only=True, read_only=True)["CGHS_Data"]
    entries, unmapped = [], set()
    for row in list(sheet.iter_rows(values_only=True))[2:]:
        if not row or not row[1] or row[7] != "Tier I":
            continue
        code, name, label = str(row[1]).strip(), re.sub(r"\s+", " ", str(row[2] or "")).strip(), str(row[6] or "").strip()
        specialty = cghs_specialty_for(name, label, labels, overrides)
        if specialty is None:
            unmapped.add(label)
            continue
        if specialty == "NONE" or not name:
            continue
        entries.append(LookupEntry(f"cghs:{code}", "cghs", code, name, specialty))
    if unmapped:
        logger.warning("CGHS labels with no mapping (left out): %s", sorted(unmapped))
    return entries


def _lay_term_entries() -> list[LookupEntry]:
    """Patients' own wording ("eye infection", "red eyes") from specialties.csv keywords.

    ICD-10-CM and CGHS use clinical language ("conjunctivitis", "gonococcal infection of eye"),
    so keyword search missed common lay terms; these entries give V1/V2 a direct match."""
    from mediroute.common.specialties import load_specialties

    entries, seen = [], set()
    for spec in load_specialties():
        for keyword in spec.keywords:
            key = (keyword.lower(), spec.name)
            if len(keyword) < 3 or key in seen:
                continue
            seen.add(key)
            entries.append(LookupEntry(f"lay:{spec.name}:{keyword}", "lay_term", "", keyword, spec.name))
    return entries


def build_lookup(path: Path = LOOKUP_FILE) -> list[LookupEntry]:
    entries = _icd_entries() + _cghs_entries() + _lay_term_entries()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_id", "source", "code", "text", "specialty"])
        for e in entries:
            writer.writerow([e.entry_id, e.source, e.code, e.text, e.specialty])
    logger.info("Step 1 lookup list written: %d entries -> %s", len(entries), path)
    return entries


def load_lookup(path: Path = LOOKUP_FILE) -> list[LookupEntry]:
    if not path.exists():
        return build_lookup(path)
    return [LookupEntry(r["entry_id"], r["source"], r["code"], r["text"], r["specialty"]) for r in _read_csv(path)]


# ---------------------------------------------------------------------------
# Searching the list
# ---------------------------------------------------------------------------


class LookupIndex:
    """Keyword (TF-IDF, words + character n-grams for typos) and embedding search over the list.

    The embedding model and matrix load lazily and are cached on disk, keyed by a hash of the
    entry texts, so a rebuilt lookup list invalidates the cache automatically.
    """

    def __init__(self, entries: list[LookupEntry] | None = None, encoder=None, cache: bool = True) -> None:
        self.cache = cache  # tests pass cache=False so nothing is written to data/vector_store
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.entries = entries if entries is not None else load_lookup()
        texts = [e.text for e in self.entries]
        self._word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
                                     stop_words="english", min_df=1)
        self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self._word_matrix = self._word.fit_transform(texts)
        self._char_matrix = self._char.fit_transform(texts)
        self._encoder = encoder
        self._embeddings: np.ndarray | None = None
        self._lock = threading.Lock()
        self.texts_hash = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]

    # -- V1 ---------------------------------------------------------------
    def keyword_search(self, query: str, k: int = 8) -> list[tuple[LookupEntry, float]]:
        word_scores = (self._word_matrix @ self._word.transform([query]).T).toarray().ravel()
        char_scores = (self._char_matrix @ self._char.transform([query]).T).toarray().ravel()
        scores = 0.5 * word_scores + 0.5 * char_scores
        top = np.argsort(-scores)[:k]
        return [(self.entries[i], float(scores[i])) for i in top if scores[i] > 0]

    # -- V2 ---------------------------------------------------------------
    def _get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(EMBEDDING_MODEL)
        return self._encoder

    def ensure_embeddings(self) -> None:
        with self._lock:
            if self._embeddings is not None:
                return
            cache = EMBEDDING_CACHE.with_name(f"{EMBEDDING_CACHE.stem}_{self.texts_hash}.npy")
            if self.cache and cache.exists():
                self._embeddings = np.load(cache)
                return
            logger.info("Encoding %d lookup entries for Step 1 (one-time, cached to %s)", len(self.entries), cache)
            vectors = self._get_encoder().encode([e.text for e in self.entries], batch_size=128,
                                                 normalize_embeddings=True, show_progress_bar=False)
            self._embeddings = np.asarray(vectors, dtype=np.float32)
            if self.cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.save(cache, self._embeddings)

    def embedding_search(self, query: str, k: int = 8) -> list[tuple[LookupEntry, float]]:
        self.ensure_embeddings()
        vector = self._get_encoder().encode([query], normalize_embeddings=True, show_progress_bar=False)
        scores = self._embeddings @ np.asarray(vector, dtype=np.float32).ravel()
        top = np.argsort(-scores)[:k]
        return [(self.entries[i], float(scores[i])) for i in top]


if __name__ == "__main__":
    built = build_lookup()
    by_source: dict[str, int] = {}
    for item in built:
        by_source[item.source] = by_source.get(item.source, 0) + 1
    print(f"{len(built)} entries {by_source} -> {LOOKUP_FILE}")
