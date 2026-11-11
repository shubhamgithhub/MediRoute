"""Step 2 eligibility: which hospitals offer Step 1's speciality.

Hospital labels reach Step 1's 26 names through the ``hospital`` rows of data/processed/specialty_mapping.csv
(a label can map to several, e.g. Neurosciences -> Neurology + Neurosurgery; NONE = not a routing
speciality). A hospital is eligible when the speciality is either
  * verified: found on the hospital's own website (``verified_specialties``), or
  * team-listed: in the team 150 sheet only (``team_claimed_specialties``), not verified.
``specialty_evidence`` says which, so the ranking and the screen can tell them apart.
"""

from mediroute.common.specialties import hospital_label_map, specialty_names

VERIFIED, TEAM_LISTED = "website", "team list"


class SpecialtyFilter:
    """Maps raw specialty names to MediRoute canonical specialties."""

    def __init__(self, mapping=None):
        # hospital department name (casefolded) -> specialities, from specialty_mapping.csv
        self.raw_to_canonical: dict[str, set[str]] = mapping if mapping is not None else hospital_label_map()
        self.canonical_specialties = {name.casefold(): name for name in specialty_names()}

    def canonical_set(self, value) -> set[str]:
        """All Step 1 specialities a label stands for (empty for NONE or unknown)."""
        text = str(value or "").strip()
        if not text:
            return set()
        if text.casefold() in self.canonical_specialties:
            return {self.canonical_specialties[text.casefold()]}
        return set(self.raw_to_canonical.get(text.casefold(), set()))

    def normalize_specialty(self, value):
        """Return a canonical specialty when one is known; otherwise return trimmed text."""
        text = str(value or "").strip()
        names = self.canonical_set(text)
        return sorted(names)[0] if len(names) == 1 else text

    def _labels(self, hospital, column) -> set[str]:
        names: set[str] = set()
        for raw in str(hospital.get(column) or "").split(";"):
            names |= self.canonical_set(raw)
        return names

    def specialty_evidence(self, hospital, canonical_specialty):
        """'website' when verified on the hospital's site, 'team list' when only the team sheet
        lists it, None when the hospital doesn't offer it."""
        wanted = self.normalize_specialty(canonical_specialty)
        if wanted in self._labels(hospital, "verified_specialties"):
            return VERIFIED
        if wanted in self._labels(hospital, "team_claimed_specialties"):
            return TEAM_LISTED
        return None

    def filter_positions(self, metadata, canonical_specialty):
        """Return vector positions of hospitals that offer the requested specialty."""
        if not canonical_specialty or not metadata:
            return []
        matched_positions = []
        for hospital in metadata:
            if self.specialty_evidence(hospital, canonical_specialty):
                vector_position = hospital.get("vector_position")
                if isinstance(vector_position, int) and 0 <= vector_position < len(metadata):
                    matched_positions.append(vector_position)
        return list(dict.fromkeys(matched_positions))
