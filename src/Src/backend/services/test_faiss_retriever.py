from src.Src.backend.services.faiss_retriever import (
    FaissHospitalRetriever,
)


retriever = FaissHospitalRetriever()

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
        hospital["semantic_rank"]
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
        hospital["semantic_score"]
    )

    print(
        "Specialties:",
        hospital[
            "verified_specialties"
        ]
    )