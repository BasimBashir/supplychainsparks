import pytest

from sparks.config import RankConfig
from sparks.rank import band_for, compute_priority

CFG = RankConfig()  # defaults from settings.yaml


def test_formula_matches_spec():
    # rubric = .35*9 + .30*10 + .25*8 + .10*7 = 8.85 -> 8.85*7 = 61.95
    # corroboration: 4 sources -> min(3, 4-1)*4 = 12 ; credibility 1.0*6 = 6 ; age 0 -> 12
    p = compute_priority(9, 10, 8, 7, n_sources=4, credibility=1.0, age_hours=0.0, cfg=CFG)
    assert p == pytest.approx(91.95, abs=0.05)


def test_caps_at_100():
    p = compute_priority(10, 10, 10, 10, n_sources=10, credibility=1.0,
                         age_hours=0.0, cfg=CFG)
    assert p <= 100.0


def test_recency_halflife():
    fresh = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=0.0, cfg=CFG)
    day_old = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=24.0, cfg=CFG)
    two_day = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=48.0, cfg=CFG)
    assert fresh - day_old == pytest.approx(6.0, abs=0.01)   # half of 12
    assert day_old - two_day == pytest.approx(3.0, abs=0.01)  # half again


def test_corroboration_capped():
    three = compute_priority(5, 5, 5, 5, n_sources=4, credibility=0.5, age_hours=0, cfg=CFG)
    ten = compute_priority(5, 5, 5, 5, n_sources=10, credibility=0.5, age_hours=0, cfg=CFG)
    assert ten == pytest.approx(three, abs=0.01)  # cap = 3 extra sources


def test_bands():
    assert band_for(75.0, CFG) == "high"
    assert band_for(74.9, CFG) == "medium"
    assert band_for(50.0, CFG) == "medium"
    assert band_for(49.9, CFG) == "low"
