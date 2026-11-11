"""The lookup list searched by voters V1 and V2: ICD-10-CM diagnoses + CGHS procedures + lay terms.

Generated, never edited by hand: data/processed/step1_lookup.csv is rebuilt from official sources
and the one rules table, data/processed/specialty_mapping.csv:

* ICD-10-CM 3- and 4-character codes (CDC 2026 order file, public domain). Each code's AHRQ CCSR
  category (CCSR reference file, data/raw/ccsr_v2023_1) gives the speciality through the
  mapping's ``ccsr`` rows. A header code whose sub-codes point to different specialities
  ("R07 Pain in throat and chest") is left out: its sub-codes carry the detail.
* CGHS procedures (Tier I rows of the CGHS_Data sheet): ``cghs_name`` rules first (text in the
  procedure name), then the ``cghs_label`` rule of the procedure's section.
* Lay terms: the mapping's ``lay_term`` rows (patient wording), unless the same text already
  comes from ICD-10-CM or CGHS.

Every row records its evidence type (diagnosis, symptom, status, procedure, strong or weak lay
term) and the rule that produced it, so a wrong row can be traced to one rule. Rules mapped to
NONE (lab tests, imaging, dental, abnormal findings...) produce no rows.

    python -m mediroute.specialty_routing.step1.lookup      (or the full rebuild, see README)
"""

from __future__ import annotations

import csv
import hashlib
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mediroute.common.specialties import lay_terms, mapping_rules, validate_mapping
from mediroute.utils.logging_config import get_logger
from mediroute.utils.paths import CCSR_FILE, CGHS_WORKBOOK, ICD_ORDER_FILE, STEP1_LOOKUP_FILE, VECTOR_STORE_DIR

logger = get_logger()

LOOKUP_FILE = STEP1_LOOKUP_FILE
EMBEDDING_CACHE = VECTOR_STORE_DIR / "step1_lookup_embeddings.npy"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FIELDS = ["entry_id", "source", "code", "text", "specialty", "evidence_type", "mapping_rule"]


@dataclass(frozen=True)
class LookupEntry:
    entry_id: str
    source: str  # "icd10cm", "cghs" or "lay_term"
    code: str
    text: str
    specialty: str
    evidence_type: str = "diagnosis"  # diagnosis | symptom | status | procedure | strong | weak
    mapping_rule: str = ""  # e.g. "ccsr:GEN005", "cghs_label:Nephrology", "lay_term:kidney stone"


# ---------------------------------------------------------------------------
# Building the list
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _ccsr_default_categories() -> dict[str, str]:
    """ICD-10-CM code -> its CCSR category (the outpatient default when a code has several)."""
    from openpyxl import load_workbook

    sheet = load_workbook(CCSR_FILE, read_only=True, data_only=True)["DX_to_CCSR_Mapping"]
    default: dict[str, str] = {}
    for row in list(sheet.iter_rows(values_only=True))[2:]:
        code, category, outpatient_default = row[0], row[2], row[5]
        if code and category and (outpatient_default == "Y" or code not in default):
            default[code] = category
    return default


def _icd_entries(stats: Counter) -> list[LookupEntry]:
    if not ICD_ORDER_FILE.exists():
        logger.warning("ICD-10-CM order file not found at %s; lookup list will have no diagnoses", ICD_ORDER_FILE)
        return []
    rules = {r.value: r for r in mapping_rules("ccsr")}
    default = _ccsr_default_categories()
    by_prefix: dict[str, Counter] = defaultdict(Counter)
    for code, category in default.items():
        for n in (3, 4):
            by_prefix[code[:n]][category] += 1
    entries, seen = [], set()
    with ICD_ORDER_FILE.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            code = line[6:13].strip()
            if len(code) not in (3, 4) or code[0] in "VWXY":  # external causes are not routing evidence
                continue
            description = line[77:].strip() or line[16:76].strip()
            categories = Counter({default[code]: 1}) if code in default else by_prefix.get(code, Counter())
            if not categories:
                stats["icd: no CCSR category (code newer than CCSR)"] += 1
                continue
            spec_sets = {rules[c].specialties for c in categories if c in rules}
            if len(spec_sets) != 1:
                stats["icd: header with sub-codes in different specialities"] += 1
                continue
            rule = rules[categories.most_common(1)[0][0]]
            if not rule.specialties:
                stats["icd: CCSR category maps to NONE"] += 1
                continue
            for specialty in rule.specialties:
                key = (description.lower(), specialty)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(LookupEntry(f"icd:{code}:{specialty}", "icd10cm", code, description, specialty,
                                           rule.evidence_type, f"ccsr:{rule.value}"))
            stats["icd: mapped"] += 1
    return entries


def _cghs_entries(stats: Counter) -> list[LookupEntry]:
    from openpyxl import load_workbook

    name_rules = mapping_rules("cghs_name")  # file order: specific phrases first
    label_rules = {r.value.casefold(): r for r in mapping_rules("cghs_label")}
    sheet = load_workbook(CGHS_WORKBOOK, data_only=True, read_only=True)["CGHS_Data"]
    entries, unmapped = [], set()
    for row in list(sheet.iter_rows(values_only=True))[2:]:
        if not row or not row[1] or row[7] != "Tier I":
            continue
        code, name, label = str(row[1]).strip(), re.sub(r"\s+", " ", str(row[2] or "")).strip(), str(row[6] or "").strip()
        rule = next((r for r in name_rules if r.value.lower() in name.lower()), None) or label_rules.get(label.casefold())
        if rule is None:
            unmapped.add(label)
            continue
        if not rule.specialties or not name:
            stats["cghs: rule maps to NONE"] += 1
            continue
        for specialty in rule.specialties:
            entries.append(LookupEntry(f"cghs:{code}:{specialty}", "cghs", code, name, specialty,
                                       rule.evidence_type, f"{rule.source}:{rule.value}"))
        stats["cghs: mapped"] += 1
    if unmapped:
        logger.warning("CGHS labels with no rule in specialty_mapping.csv (left out): %s", sorted(unmapped))
    return entries


def _lay_term_entries(official_texts: set[str], stats: Counter) -> list[LookupEntry]:
    """Patients' own wording ("red eyes", "kidney stone"); clinical sources say "conjunctivitis"."""
    entries = []
    for rule in lay_terms():
        term = rule.value.lower()
        if len(term) < 3:
            stats["lay: shorter than 3 letters"] += 1
            continue
        if term in official_texts:
            stats["lay: same text already from ICD/CGHS"] += 1
            continue
        for specialty in rule.specialties:
            entries.append(LookupEntry(f"lay:{specialty}:{term}", "lay_term", "", term, specialty,
                                       rule.evidence_type, f"lay_term:{rule.value}"))
        stats["lay: added"] += 1
    return entries


def build_lookup(path: Path = LOOKUP_FILE) -> list[LookupEntry]:
    problems = validate_mapping()
    if problems:
        raise ValueError("specialty_mapping.csv has problems:\n  " + "\n  ".join(problems[:20]))
    stats: Counter = Counter()
    official = _icd_entries(stats) + _cghs_entries(stats)
    entries = official + _lay_term_entries({e.text.lower() for e in official}, stats)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        for e in entries:
            writer.writerow([e.entry_id, e.source, e.code, e.text, e.specialty, e.evidence_type, e.mapping_rule])
    logger.info("Step 1 lookup list written: %d entries -> %s (%s)", len(entries), path, dict(stats))
    return entries


def load_lookup(path: Path = LOOKUP_FILE) -> list[LookupEntry]:
    if not path.exists():
        return build_lookup(path)
    return [LookupEntry(r["entry_id"], r["source"], r["code"], r["text"], r["specialty"],
                        r.get("evidence_type") or "diagnosis", r.get("mapping_rule") or "")
            for r in _read_csv(path)]


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
    print(f"{len(built)} entries {dict(Counter(e.source for e in built))} -> {LOOKUP_FILE}")
