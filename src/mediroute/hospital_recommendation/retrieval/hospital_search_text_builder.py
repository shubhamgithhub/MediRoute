import pandas as pd


class HospitalSearchTextBuilder:

    def clean_value(self, value) -> str:

        if pd.isna(value):
            return ""

        return str(value).strip()

    def build_search_text(
        self,
        hospital: dict
    ) -> str:

        hospital_name = self.clean_value(
            hospital.get("hospital name")
            or hospital.get("name")
        )

        city = self.clean_value(
            hospital.get("city")
        )

        state = self.clean_value(
            hospital.get("state")
        )

        specialties = self.clean_value(
            hospital.get(
                "verified_specialties"
            )
        )

        subspecialties = self.clean_value(
            hospital.get("subspecialties")
            or hospital.get("verified_subspecialties")
        )

        procedures = self.clean_value(
            hospital.get("procedures")
            or hospital.get("verified_procedures")
        )

        facilities = self.clean_value(
            hospital.get("facilities")
            or hospital.get("verified_facilities")
        )

        international_service = self.clean_value(
            hospital.get(
                "international_patient_service"
            )
        )

        rag_evidence = self.clean_value(
            hospital.get(
                "rag_evidence_text"
            )
        )

        parts = []

        if hospital_name:
            parts.append(
                f"Hospital: {hospital_name}."
            )

        if city or state:

            location_values = [
                value
                for value in [city, state]
                if value
            ]

            parts.append(
                "Location: "
                + ", ".join(location_values)
                + "."
            )

        claimed = self.clean_value(hospital.get("team_claimed_specialties"))
        if specialties and specialties != "NA":
            parts.append(
                f"Specialties: {specialties}."
            )
        if claimed:
            parts.append(f"Also listed: {claimed.replace(';', '; ')}.")

        if subspecialties:
            parts.append(
                f"Subspecialties: {subspecialties}."
            )

        if procedures:
            parts.append(
                f"Procedures: {procedures}."
            )

        if facilities:
            parts.append(
                f"Facilities: {facilities}."
            )

        if international_service:
            parts.append(
                "International patient service: "
                f"{international_service}."
            )

        if rag_evidence:
            parts.append(
                f"Evidence: {rag_evidence}."
            )

        return " ".join(parts)