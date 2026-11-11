"""Rebuild every generated file in data/processed/ from its sources, in order.

    python -m mediroute.data_generator.rebuild                 # everything
    python -m mediroute.data_generator.rebuild --step lookup   # one step (and nothing after it)

Hand-maintained (edit these, then rebuild):
    data/processed/specialties.csv        the speciality master list
    data/processed/specialty_mapping.csv  every "X -> speciality" rule
    data/processed/cities.csv             cities and search areas
    data/processed/hospital.schema.csv    hospital table columns

Steps:
    mapping   check specialty_mapping.csv (every rule -> a name in specialties.csv, no duplicates)
    hospitals data/processed/hospitals.csv from the verified master (data/interim), the id links and
              the team 150 sheet (data/raw). The master itself comes from the slow website / NABH /
              JCI checks (README section 6.5); rerun those only when hospitals change.
    lookup    data/processed/step1_lookup.csv from ICD-10-CM + AHRQ CCSR + CGHS (data/raw) and the
              mapping, then its embedding cache in data/processed/vector_store/
    index     Step 2 search index: data/processed/vector_store/hospital_* (FAISS) from hospitals.csv
"""

from __future__ import annotations

import argparse
import time

STEPS = ["mapping", "hospitals", "lookup", "index"]


def run_mapping() -> None:
    from mediroute.data_generator.validate_specialty_mapping import main
    main()


def run_hospitals() -> None:
    from mediroute.data_generator import build_hospitals_table
    build_hospitals_table.main()


def run_lookup() -> None:
    from mediroute.specialty_routing.step1.lookup import LookupIndex, build_lookup
    entries = build_lookup()
    LookupIndex(entries).ensure_embeddings()  # cached by text hash; a changed list re-encodes
    print(f"step1_lookup.csv: {len(entries)} entries, embeddings cached")


def run_index() -> None:
    from mediroute.data_generator.build_faiss_index import build_faiss_index
    from mediroute.data_generator.build_hospital_embedding_dataset import build_hospital_embedding_dataset
    build_hospital_embedding_dataset()
    build_faiss_index()


RUNNERS = {"mapping": run_mapping, "hospitals": run_hospitals, "lookup": run_lookup, "index": run_index}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild data/processed/ from its sources")
    parser.add_argument("--step", choices=STEPS, help="run only this step")
    args = parser.parse_args()
    for step in [args.step] if args.step else STEPS:
        start = time.perf_counter()
        print(f"\n== {step} ==")
        RUNNERS[step]()
        print(f"== {step} done in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
