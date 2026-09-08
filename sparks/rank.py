"""Composite editorial priority: judge rubric + mechanical signals (spec 4.6)."""
from __future__ import annotations

import math

from sparks.config import RankConfig


def compute_priority(sc: int, saudi: int, impact: int, novelty: int,
                     n_sources: int, credibility: float, age_hours: float,
                     cfg: RankConfig) -> float:
    w = cfg.weights
    rubric = w.sc * sc + w.saudi * saudi + w.impact * impact + w.novelty * novelty  # 0-10
    priority = rubric * cfg.rubric_scale                                            # 0-70
    priority += min(max(n_sources - 1, 0), cfg.corroboration_cap) * cfg.corroboration_points
    priority += max(0.0, min(1.0, credibility)) * cfg.credibility_points
    if age_hours > 0:
        priority += cfg.recency_points * (0.5 ** (age_hours / cfg.recency_halflife_hours))
    else:
        priority += cfg.recency_points
    return round(min(100.0, priority), 1)


def band_for(priority: float, cfg: RankConfig) -> str:
    if priority >= cfg.high_band:
        return "high"
    if priority >= cfg.medium_band:
        return "medium"
    return "low"
