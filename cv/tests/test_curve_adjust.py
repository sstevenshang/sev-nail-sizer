"""Tests for pipeline/curve_adjust.py lookup table."""

from __future__ import annotations

import pytest

from pipeline.curve_adjust import adjust_curve
from pipeline.measure import FingerMeasurement


def _meas(width_mm: float, finger: str = "index") -> FingerMeasurement:
    return FingerMeasurement(finger=finger, width_mm=width_mm, length_mm=10.0, confidence=0.9)


PX_PER_MM = 10.0


def _finger_px(finger_width_mm: float) -> float:
    return finger_width_mm * PX_PER_MM


# ---------------------------------------------------------------------------
# Lookup table branches
# ---------------------------------------------------------------------------


def test_ratio_below_0_70_uses_1_05():
    """nail 8mm, finger 15mm → ratio 0.533 < 0.70 → factor 1.05"""
    result = adjust_curve(_meas(8.0), finger_width_px=_finger_px(15.0), px_per_mm=PX_PER_MM)
    assert result == pytest.approx(8.0 * 1.05, rel=1e-4)


def test_ratio_0_70_to_0_85_uses_1_12():
    """nail 11mm, finger 14mm → ratio 0.786 → factor 1.12"""
    result = adjust_curve(_meas(11.0), finger_width_px=_finger_px(14.0), px_per_mm=PX_PER_MM)
    assert result == pytest.approx(11.0 * 1.12, rel=1e-4)


def test_ratio_above_0_85_uses_1_18():
    """nail 13mm, finger 14mm → ratio 0.929 > 0.85 → factor 1.18"""
    result = adjust_curve(_meas(13.0), finger_width_px=_finger_px(14.0), px_per_mm=PX_PER_MM)
    assert result == pytest.approx(13.0 * 1.18, rel=1e-4)


def test_ratio_exactly_0_70_uses_1_12():
    """ratio == 0.70 is the boundary: < 0.70 is 1.05 bucket, ≥ 0.70 is 1.12 bucket"""
    result = adjust_curve(_meas(7.0), finger_width_px=_finger_px(10.0), px_per_mm=PX_PER_MM)
    assert result == pytest.approx(7.0 * 1.12, rel=1e-4)


def test_ratio_exactly_0_85_uses_1_18():
    result = adjust_curve(_meas(8.5), finger_width_px=_finger_px(10.0), px_per_mm=PX_PER_MM)
    assert result == pytest.approx(8.5 * 1.18, rel=1e-4)


# ---------------------------------------------------------------------------
# Edge / guard cases
# ---------------------------------------------------------------------------


def test_zero_finger_width_returns_original():
    m = _meas(12.0)
    result = adjust_curve(m, finger_width_px=0.0, px_per_mm=PX_PER_MM)
    assert result == m.width_mm


def test_zero_px_per_mm_returns_original():
    m = _meas(12.0)
    result = adjust_curve(m, finger_width_px=100.0, px_per_mm=0.0)
    assert result == m.width_mm


def test_zero_nail_width_returns_zero():
    m = _meas(0.0)
    result = adjust_curve(m, finger_width_px=100.0, px_per_mm=PX_PER_MM)
    assert result == 0.0


def test_all_fingers_positive_adjustment():
    """All realistic nail measurements should produce a positive adjusted value."""
    test_cases = [
        (16.2, 25.0),  # thumb
        (14.1, 22.0),  # index
        (14.8, 23.0),  # middle
        (13.2, 21.0),  # ring
        (11.0, 18.0),  # pinky
    ]
    for nail_mm, finger_mm in test_cases:
        m = _meas(nail_mm)
        result = adjust_curve(m, finger_width_px=_finger_px(finger_mm), px_per_mm=PX_PER_MM)
        assert result > nail_mm, f"Expected positive adjustment for nail={nail_mm}, finger={finger_mm}"
