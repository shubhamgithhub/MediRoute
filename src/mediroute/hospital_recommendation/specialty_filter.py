import csv
from pathlib import Path


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402
SPECIALTY_NORMALIZATION_FILE = (
    PROJECT_ROOT / "data" / "medical_taxonomy" / "specialty_normalization.csv"
)


class SpecialtyFilter:
    """Maps raw specialty names to MediRoute canonical specialties."""

    def __init__(self, mapping_file=None):
        self.mapping_file = Path(mapping_file) if mapping_file else SPECIALTY_NORMALIZATION_FILE
        self.raw_to_canonical = {}
        self.canonical_specialties = set()
        self._load_mapping()

    def _load_mapping(self):
        with open(self.mapping_file, "r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                raw = (row.get("raw_specialty") or "").strip()
                canonical = (row.get("canonical_specialty") or "").strip()
                if raw and canonical:
                    normalized_raw = raw.strip().casefold()
                    normalized_canonical = canonical.strip().casefold()
                    self.raw_to_canonical[normalized_raw] = canonical
                    self.canonical_specialties.add(normalized_canonical)

    def normalize_specialty(self, value):
        """Return a canonical specialty when one is known; otherwise return trimmed text."""
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        mapped = self.raw_to_canonical.get(text.casefold())
        if mapped:
            return mapped
        if text.casefold() in self.canonical_specialties:
            return text
        return text

    def filter_positions(self, metadata, canonical_specialty):
        """Return vector positions whose verified specialties match the requested specialty."""
        if not canonical_specialty or not metadata:
            return []

        requested = self.normalize_specialty(canonical_specialty)
        requested_key = requested.casefold()
        matched_positions = []

        for hospital in metadata:
            raw_specialties = hospital.get("verified_specialties")
            if raw_specialties is None:
                continue

            for raw_specialty in str(raw_specialties).split(";"):
                hospital_specialty = self.normalize_specialty(raw_specialty.strip())
                if hospital_specialty and hospital_specialty.casefold() == requested_key:
                    vector_position = hospital.get("vector_position")
                    if isinstance(vector_position, int) and 0 <= vector_position < len(metadata):
                        matched_positions.append(vector_position)
                    break

        return list(dict.fromkeys(matched_positions))
