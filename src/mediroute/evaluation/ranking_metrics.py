"""Ranking metrics for graded relevance (0-3), as used by scripts/eval_step2.py.

``ranked`` is a system's result list (hospital ids, best first). ``grades`` maps every judged
hospital for the query to its relevance (0-3, location already applied). A hospital is relevant
when its grade is >= ``RELEVANT``. Design: docs/design/step2_evaluation_design.md, section 7.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

RELEVANT = 2


def _rel(grades: Mapping[str, int], hospital_id: str) -> int:
    return int(grades.get(hospital_id, 0))  # unjudged counts as 0


def relevant_count(grades: Mapping[str, int], threshold: int = RELEVANT) -> int:
    return sum(1 for g in grades.values() if g >= threshold)


def precision_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int, threshold: int = RELEVANT) -> float:
    """Relevant hospitals in the top k, divided by k (a shorter list still divides by k)."""
    return sum(1 for h in ranked[:k] if _rel(grades, h) >= threshold) / k


def recall_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int, threshold: int = RELEVANT) -> float | None:
    """Relevant hospitals in the top k, divided by all relevant judged hospitals (None if there are none)."""
    total = relevant_count(grades, threshold)
    if total == 0:
        return None
    return sum(1 for h in ranked[:k] if _rel(grades, h) >= threshold) / total


def max_precision_at_k(grades: Mapping[str, int], k: int, threshold: int = RELEVANT) -> float:
    """Best P@k any system could reach: min(k, relevant) / k."""
    return min(k, relevant_count(grades, threshold)) / k


def _dcg(gains: Sequence[int]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float | None:
    """DCG@k / ideal DCG@k with gain 2^grade - 1; the ideal uses every judged hospital.
    None when no judged hospital has a grade above 0."""
    ideal = _dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return None
    return _dcg([_rel(grades, h) for h in ranked[:k]]) / ideal


def hit_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int, threshold: int = RELEVANT) -> float:
    """1.0 when at least one relevant hospital is in the top k."""
    return 1.0 if any(_rel(grades, h) >= threshold for h in ranked[:k]) else 0.0


def bad_at_k(ranked: Sequence[str], capability: Mapping[str, int], k: int) -> float:
    """1.0 when a top-k hospital has capability grade 0 (cannot treat this need).
    Uses capability grades (before the location rule), so it measures medical safety only.
    Unjudged hospitals are not counted as bad."""
    return 1.0 if any(h in capability and capability[h] == 0 for h in ranked[:k]) else 0.0


def mean(values: Sequence[float | None]) -> float | None:
    kept = [v for v in values if v is not None]
    return sum(kept) / len(kept) if kept else None


def bootstrap_ci(values: Sequence[float | None], resamples: int = 2000, seed: int = 0,
                 level: float = 0.95) -> tuple[float, float] | None:
    """Percentile bootstrap CI of the mean, resampling queries."""
    kept = [v for v in values if v is not None]
    if not kept:
        return None
    rng = random.Random(seed)
    n = len(kept)
    means = sorted(sum(rng.choice(kept) for _ in range(n)) / n for _ in range(resamples))
    low = means[int((1 - level) / 2 * resamples)]
    high = means[min(resamples - 1, int((1 + level) / 2 * resamples))]
    return low, high


def paired_permutation_p(a: Sequence[float | None], b: Sequence[float | None], permutations: int = 10000,
                         seed: int = 0) -> float | None:
    """Two-sided paired sign-flip test of mean(a - b) over queries where both have a value."""
    diffs = [x - y for x, y in zip(a, b) if x is not None and y is not None]
    if not diffs:
        return None
    observed = abs(sum(diffs))
    if observed == 0:
        return 1.0
    rng = random.Random(seed)
    extreme = sum(1 for _ in range(permutations)
                  if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - 1e-12)
    return (extreme + 1) / (permutations + 1)
