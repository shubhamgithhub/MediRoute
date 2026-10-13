import csv
from pathlib import Path


_HOSPITALS_FILE = Path(__file__).resolve().parents[3] / "Data" / "SampleData.csv"


def load_hospitals() -> list[dict[str, str]]:
    with _HOSPITALS_FILE.open(encoding="utf-8-sig", newline="") as hospitals_file:
        return list(csv.DictReader(hospitals_file, delimiter="\t"))


def search_hospitals_by_location(location: str) -> list[dict[str, str]]:
    hospitals = load_hospitals()
    normalized_location = location.strip().casefold()
    if not normalized_location or normalized_location == "no preference":
        return hospitals

    return [
        hospital
        for hospital in hospitals
        if normalized_location in hospital["city"].casefold()
    ]
