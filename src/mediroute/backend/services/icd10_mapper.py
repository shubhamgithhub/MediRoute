from pathlib import Path
import pandas as pd


from mediroute.utils.paths import PROJECT_ROOT  # noqa: E402

MAPPING_FILE = (
    PROJECT_ROOT
    / "data"
    / "medical_taxonomy"
    / "icd10_specialty_mapping.csv"
)


class ICD10Mapper:

    def __init__(self):
        self.df = self._load_mapping()

    def _load_mapping(self):
        if not MAPPING_FILE.exists():
            raise FileNotFoundError(
                f"ICD-10 mapping file not found: {MAPPING_FILE}"
            )

        df = pd.read_csv(MAPPING_FILE)

        required_columns = [
            "icd10_code",
            "icd10_title",
            "condition_alias",
            "canonical_specialty",
            "mapping_status",
        ]

        missing = [
            col for col in required_columns
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required columns: {missing}"
            )

        return df

    def find_by_condition(self, condition: str):
        if not condition:
            return {
                "matched": False,
                "reason": "Empty condition"
            }

        condition_normalized = condition.strip().casefold()

        matches = self.df[
            self.df["condition_alias"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            == condition_normalized
        ]

        if matches.empty:
            matches = self.df[
                self.df["icd10_title"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.casefold()
                == condition_normalized
            ]

        if matches.empty:
            return {
                "matched": False,
                "condition": condition,
                "reason": "No exact ICD-10 mapping found"
            }

        row = matches.iloc[0]

        return {
            "matched": True,
            "condition": condition,
            "icd10_code": row["icd10_code"],
            "icd10_title": row["icd10_title"],
            "canonical_specialty": row["canonical_specialty"],
            "secondary_specialty": (
                None
                if pd.isna(row.get("secondary_specialty"))
                else row.get("secondary_specialty")
            ),
            "mapping_status": row["mapping_status"],
        }

    def find_by_icd10_code(self, code: str):
        if not code:
            return {
                "matched": False,
                "reason": "Empty ICD-10 code"
            }

        code_normalized = code.strip().upper()

        matches = self.df[
            self.df["icd10_code"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            == code_normalized
        ]

        if matches.empty:
            return {
                "matched": False,
                "icd10_code": code,
                "reason": "ICD-10 code not found"
            }

        row = matches.iloc[0]

        return {
            "matched": True,
            "icd10_code": row["icd10_code"],
            "icd10_title": row["icd10_title"],
            "canonical_specialty": row["canonical_specialty"],
            "mapping_status": row["mapping_status"],
        }


if __name__ == "__main__":

    mapper = ICD10Mapper()

    print("\nTEST 1")
    print(
        mapper.find_by_condition(
            "heart attack"
        )
    )

    print("\nTEST 2")
    print(
        mapper.find_by_condition(
            "breast cancer"
        )
    )

    print("\nTEST 3")
    print(
        mapper.find_by_icd10_code(
            "I21"
        )
    )

    print("\nTEST 4")
    print(
        mapper.find_by_condition(
            "unknown disease"
        )
    )