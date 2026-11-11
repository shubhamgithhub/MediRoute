"""Check data/processed/specialty_mapping.csv: every rule points to a name in specialties.csv,
no rule is listed twice, and every evidence type is allowed for its source.

    python -m mediroute.data_generator.validate_specialty_mapping
"""

from collections import Counter

from mediroute.common.specialties import load_mapping, validate_mapping
from mediroute.utils.paths import SPECIALTY_MAPPING_FILE


def main() -> None:
    rules = load_mapping()
    problems = validate_mapping()
    by_source = Counter(r.source for r in rules)
    review = Counter(r.review_status for r in rules)
    print(f"{SPECIALTY_MAPPING_FILE.name}: {len(rules)} rules {dict(by_source)}; review status {dict(review)}")
    if problems:
        raise SystemExit("Problems:\n  " + "\n  ".join(problems))
    print("valid")


if __name__ == "__main__":
    main()
