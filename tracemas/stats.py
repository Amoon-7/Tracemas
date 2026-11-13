"""Small exact statistics (no SciPy dependency)."""
from __future__ import annotations

from math import comb, sqrt


def fisher_one_sided(f1: int, n1: int, f0: int, n0: int) -> float:
    """P(X >= f1): do perturbed replays flip the decision more often than baseline replays?"""
    n, k = n1 + n0, f1 + f0
    denom = comb(n, n1)
    return sum(comb(k, i) * comb(n - k, n1 - i) for i in range(f1, min(n1, k) + 1)) / denom


def wilson(f: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = f / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))
