"""Tests for pipeline/measure.py and pipeline/nail_segment.py (mock mode)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from pipeline.measure import FingerMeasurement, measure_all_nails, measure_nail
from pipeline.nail_segment import NailMask, segment_nails


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ellipse_mask(h: int, w: int, cx: int, cy: int, rx: int, ry: int) -> np.ndarray:
    canvas = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(canvas, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
    return canvas.astype(bool)


# ---------------------------------------------------------------------------
# measure_nail
# ---------------------------------------------------------------------------


def test_measure_nail_width_correct():
    """Ellipse with rx=30 → width ≈ 60px."""
    mask = NailMask(
        finger="index",
        mask=_ellipse_mask(200, 200, 100, 100, rx=30, ry=40),
        confidence=0.9,
    )
    result = measure_nail(mask, px_per_mm=10.0)

    assert result.finger == "index"
    # Width in mm ≈ 60/10 = 6.0, allow ±0.5mm tolerance
    assert result.width_mm == pytest.approx(6.0, abs=0.5)


def test_measure_nail_length_correct():
    """Ellipse with ry=40 → length ≈ 80px."""
    mask = NailMask(
        finger="middle",
        mask=_ellipse_mask(200, 200, 100, 100, rx=20, ry=40),
        confidence=0.85,
    )
    result = measure_nail(mask, px_per_mm=10.0)

    # Length ≈ 80/10 = 8.0mm
    assert result.length_mm == pytest.approx(8.0, abs=0.5)


def test_measure_nail_empty_mask():
    mask = NailMask(
        finger="pinky",
        mask=np.zeros((100, 100), dtype=bool),
        confidence=0.0,
    )
    result = measure_nail(mask, px_per_mm=10.0)
    assert result.width_mm == 0.0
    assert result.length_mm == 0.0
    assert result.confidence == 0.0


def test_measure_nail_zero_px_per_mm():
    mask = NailMask(
        finger="thumb",
        mask=_ellipse_mask(100, 100, 50, 50, rx=15, ry=20),
        confidence=0.8,
    )
    result = measure_nail(mask, px_per_mm=0.0)
    assert result.width_mm == 0.0


def test_measure_nail_preserves_confidence():
    mask = NailMask(
        finger="ring",
        mask=_ellipse_mask(100, 100, 50, 50, rx=10, ry=15),
        confidence=0.77,
    )
    result = measure_nail(mask, px_per_mm=5.0)
    assert result.confidence == pytest.approx(0.77)


# ---------------------------------------------------------------------------
# measure_all_nails
# ---------------------------------------------------------------------------


def test_measure_all_nails_returns_all_fingers():
    fingers = ["thumb", "index", "middle", "ring", "pinky"]
    masks = [
        NailMask(
            finger=f,
            mask=_ellipse_mask(300, 400, 200, 150, rx=15, ry=22),
            confidence=0.9,
        )
        for f in fingers
    ]
    results = measure_all_nails(masks, px_per_mm=5.84)
    assert set(results.keys()) == set(fingers)
    for f in fingers:
        assert results[f].width_mm > 0


# ---------------------------------------------------------------------------
# segment_nails (mock mode)
# ---------------------------------------------------------------------------


def test_segment_nails_mock_returns_five_masks():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    tips = {
        "thumb":  (100, 100),
        "index":  (180, 80),
        "middle": (260, 75),
        "ring":   (340, 82),
        "pinky":  (410, 100),
    }
    masks = segment_nails(img, tips, mock=True)

    assert len(masks) == 5
    fingers_returned = {m.finger for m in masks}
    assert fingers_returned == set(tips.keys())


def test_segment_nails_mock_masks_centred_at_tips():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cx, cy = 300, 200
    tips = {"index": (cx, cy)}
    masks = segment_nails(img, tips, mock=True)
    m = masks[0]

    # The centroid of the ellipse should be close to the tip
    rows, cols = np.where(m.mask)
    centroid_r = rows.mean()
    centroid_c = cols.mean()
    assert abs(centroid_r - cy) < 10
    assert abs(centroid_c - cx) < 10
