"""Tests for shared probability helpers."""
from mlbmodel.market.probability import p_over_line_erf, p_over_line_normal


def test_p_over_line_normal_above_mean():
    p = p_over_line_normal(5.0, 6.0, 1.0)
    assert p > 0.5


def test_p_over_line_erf_half_point():
    p = p_over_line_erf(5.5, 6.0, 1.0)
    assert 0.4 < p < 0.7
