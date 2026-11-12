"""Ranking metrics against hand-computed values (the TAVR-in-Mumbai example in
docs/design/step2_evaluation_design.md)."""

import pytest

from mediroute.evaluation.ranking_metrics import (
    bad_at_k,
    bootstrap_ci,
    hit_at_k,
    max_precision_at_k,
    ndcg_at_k,
    paired_permutation_p,
    precision_at_k,
    recall_at_k,
)

GRADES = {"A": 3, "B": 3, "C": 2, "D": 1, "E": 0, "F": 2, "G": 0, "H": 1}
RANKED = ["B", "D", "A", "E", "C"]


def test_precision():
    assert precision_at_k(RANKED, GRADES, 3) == pytest.approx(2 / 3)
    assert precision_at_k(RANKED, GRADES, 5) == pytest.approx(3 / 5)


def test_precision_short_list_still_divides_by_k():
    assert precision_at_k(["A"], GRADES, 5) == pytest.approx(1 / 5)


def test_recall():
    assert recall_at_k(RANKED, GRADES, 3) == pytest.approx(2 / 4)
    assert recall_at_k(RANKED, GRADES, 5) == pytest.approx(3 / 4)
    assert recall_at_k(RANKED, {"X": 1}, 5) is None


def test_ndcg_matches_hand_computation():
    assert ndcg_at_k(RANKED, GRADES, 5) == pytest.approx(0.8422, abs=1e-3)
    assert ndcg_at_k(RANKED, GRADES, 3) == pytest.approx(0.8618, abs=1e-3)
    assert ndcg_at_k(["A", "B", "C", "F", "D"], GRADES, 5) == pytest.approx(1.0)
    assert ndcg_at_k(["A"], {"A": 0}, 5) is None


def test_ndcg_sees_order_precision_does_not():
    swapped = ["D", "B", "A", "E", "C"]
    assert precision_at_k(swapped, GRADES, 5) == precision_at_k(RANKED, GRADES, 5)
    assert ndcg_at_k(swapped, GRADES, 5) < ndcg_at_k(RANKED, GRADES, 5)


def test_unjudged_counts_as_zero():
    assert precision_at_k(["Z", "A"], GRADES, 2) == pytest.approx(0.5)


def test_hit_bad_max():
    assert hit_at_k(RANKED, GRADES, 3) == 1.0
    assert hit_at_k(["D", "E", "G"], GRADES, 3) == 0.0
    assert bad_at_k(["D", "E", "A"], GRADES, 3) == 1.0
    assert bad_at_k(RANKED, GRADES, 2) == 0.0
    assert bad_at_k(["Z"], GRADES, 3) == 0.0  # unjudged is not "bad"
    assert max_precision_at_k({"A": 3, "B": 2, "C": 0}, 5) == pytest.approx(0.4)


def test_bootstrap_and_permutation():
    low, high = bootstrap_ci([0.2, 0.4, 0.6, 0.8, None])
    assert 0.2 <= low <= 0.5 <= high <= 0.8
    assert paired_permutation_p([1, 1, 1, 1, 1, 1, 1, 1], [0] * 8) < 0.01
    assert paired_permutation_p([0.5, 0.4], [0.5, 0.4]) == 1.0
