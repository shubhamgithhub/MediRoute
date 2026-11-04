from mediroute.hospital_recommendation.retrieval.faiss_retriever import (
    FaissHospitalRetriever,
)

from mediroute.hospital_recommendation.retrieval.keyword_retriever import (
    KeywordHospitalRetriever,
)


def run_tests():

    print()
    print("STEP 10 — RETRIEVAL PIPELINE VALIDATION")
    print("=" * 60)

    faiss_retriever = FaissHospitalRetriever()
    keyword_retriever = KeywordHospitalRetriever()

    passed = 0
    failed = 0

    query = (
        "Cardiology coronary artery disease "
        "CABG cardiac surgery"
    )

    # -------------------------------------------------
    # T001 — FAISS returns requested top_k
    # -------------------------------------------------

    faiss_results = faiss_retriever.search(
        query=query,
        top_k=5
    )

    if len(faiss_results) == 5:
        print("T001: PASS — FAISS returned top 5")
        passed += 1
    else:
        print(
            f"T001: FAIL — FAISS returned "
            f"{len(faiss_results)} results"
        )
        failed += 1

    # -------------------------------------------------
    # T002 — FAISS hospital IDs are present
    # -------------------------------------------------

    if (
        faiss_results
        and all(
            result.get("hospital_id")
            for result in faiss_results
        )
    ):
        print(
            "T002: PASS — FAISS hospital IDs present"
        )
        passed += 1
    else:
        print(
            "T002: FAIL — missing hospital IDs"
        )
        failed += 1

    # -------------------------------------------------
    # T003 — FAISS scores are descending
    # -------------------------------------------------

    faiss_scores = [
        result["semantic_score"]
        for result in faiss_results
    ]

    if faiss_scores == sorted(
        faiss_scores,
        reverse=True
    ):
        print(
            "T003: PASS — FAISS scores descending"
        )
        passed += 1
    else:
        print(
            "T003: FAIL — FAISS score ordering"
        )
        failed += 1

    # -------------------------------------------------
    # T004 — Keyword retriever returns results
    # -------------------------------------------------

    keyword_results = keyword_retriever.search(
        query=query,
        top_k=5
    )

    if len(keyword_results) > 0:
        print(
            "T004: PASS — keyword results returned"
        )
        passed += 1
    else:
        print(
            "T004: FAIL — keyword search empty"
        )
        failed += 1

    # -------------------------------------------------
    # T005 — Keyword results contain hospital IDs
    # -------------------------------------------------

    if (
        keyword_results
        and all(
            result.get("hospital_id")
            for result in keyword_results
        )
    ):
        print(
            "T005: PASS — keyword hospital IDs present"
        )
        passed += 1
    else:
        print(
            "T005: FAIL — missing keyword IDs"
        )
        failed += 1

    # -------------------------------------------------
    # T006 — Empty query handling
    # -------------------------------------------------

    faiss_empty = faiss_retriever.search(
        query="",
        top_k=5
    )

    keyword_empty = keyword_retriever.search(
        query="",
        top_k=5
    )

    if (
        faiss_empty == []
        and keyword_empty == []
    ):
        print(
            "T006: PASS — empty queries handled"
        )
        passed += 1
    else:
        print(
            "T006: FAIL — empty query handling"
        )
        failed += 1

    # -------------------------------------------------
    # T007 — FAISS index and metadata count match
    # -------------------------------------------------

    if (
        faiss_retriever.index.ntotal
        == len(faiss_retriever.metadata)
    ):
        print(
            "T007: PASS — index and metadata aligned"
        )
        passed += 1
    else:
        print(
            "T007: FAIL — index/metadata mismatch"
        )
        failed += 1

    # -------------------------------------------------
    # T008 — Both retrievers use same metadata count
    # -------------------------------------------------

    if (
        len(faiss_retriever.metadata)
        == len(keyword_retriever.metadata)
    ):
        print(
            "T008: PASS — retrieval datasets aligned"
        )
        passed += 1
    else:
        print(
            "T008: FAIL — retrieval datasets differ"
        )
        failed += 1

    # -------------------------------------------------
    # Final summary
    # -------------------------------------------------

    total = passed + failed

    print()
    print("=" * 60)

    print(
        f"Total tests: {total}"
    )

    print(
        f"Passed: {passed}"
    )

    print(
        f"Failed: {failed}"
    )

    accuracy = (
        passed / total
        if total > 0
        else 0
    )

    print(
        f"Accuracy: {accuracy:.2%}"
    )


if __name__ == "__main__":
    run_tests()