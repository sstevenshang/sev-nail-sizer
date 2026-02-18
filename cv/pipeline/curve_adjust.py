"""Curvature adjustment: inflate nail width to account for nail arc."""

from __future__ import annotations

from .measure import FingerMeasurement


def adjust_curve(
    measurement: FingerMeasurement,
    finger_width_px: float,
    px_per_mm: float,
) -> float:
    """
    Apply a lookup-table factor based on the nail-to-finger-width ratio.

    Ratio buckets
    -------------
    < 0.70   → ×1.05  (narrow nail relative to finger)
    0.70–0.85 → ×1.12
    ≥ 0.85   → ×1.18  (wide nail relative to finger)

    Returns the curve-adjusted width in mm.
    """
    if finger_width_px <= 0 or px_per_mm <= 0 or measurement.width_mm <= 0:
        return measurement.width_mm

    finger_width_mm = finger_width_px / px_per_mm
    ratio = measurement.width_mm / finger_width_mm

    if ratio < 0.70:
        factor = 1.05
    elif ratio < 0.85:
        factor = 1.12
    else:
        factor = 1.18

    return round(measurement.width_mm * factor, 2)
