from mediroute.backend.services.keyword_retriever import (
    KeywordHospitalRetriever,
)


retriever = KeywordHospitalRetriever()

results = retriever.search(
    query=(
        "Cardiology coronary artery "
        "disease CABG cardiac surgery"
    ),
    top_k=5
)


for hospital in results:

    print()

    print(
        "Rank:",
        hospital["keyword_rank"]
    )

    print(
        "Hospital:",
        hospital["hospital_name"]
    )

    print(
        "City:",
        hospital["city"]
    )

    print(
        "Score:",
        hospital["keyword_score"]
    )

    print(
        "Specialties:",
        hospital[
            "verified_specialties"
        ]
    )