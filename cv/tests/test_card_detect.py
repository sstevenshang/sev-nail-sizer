"""Tests for pipeline/card_detect.py using synthetic card images."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from pipeline.card_detect import (
    CARD_ASPECT_RATIO,
    CARD_WIDTH_MM,
    CardResult,
    detect_card,
    order_corners,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_card_image(
    img_w: int = 800,
    img_h: int = 600,
    card_w: int = 500,
    margin: int = 0,
) -> tuple[np.ndarray, tuple]:
    """White rectangle on a dark background at credit-card aspect ratio."""
    card_h = int(round(card_w / CARD_ASPECT_RATIO))
    img = np.full((img_h, img_w, 3), 30, dtype=np.uint8)
    x1 = (img_w - card_w) // 2 + margin
    y1 = (img_h - card_h) // 2 + margin
    x2 = x1 + card_w - margin
    y2 = y1 + card_h - margin
    cv2.rectangle(img, (x1, y1), (x2, y2), (220, 220, 220), thickness=-1)
    return img, (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# order_corners
# ---------------------------------------------------------------------------


def test_order_corners_axis_aligned():
    pts = np.array([[200, 100], [100, 200], [200, 200], [100, 100]], dtype=np.float32)
    ordered = order_corners(pts)
    tl, tr, br, bl = ordered
    # top-left has smallest sum, bottom-right has largest sum
    assert tl[0] < tr[0] and tl[1] < bl[1]
    assert br[0] > bl[0] and br[1] > tr[1]


# ---------------------------------------------------------------------------
# detect_card — success cases
# ---------------------------------------------------------------------------


def test_detect_card_finds_synthetic_card():
    img, (x1, y1, x2, y2) = make_card_image()
    result = detect_card(img)

    assert result is not None, "Card not detected in a clear synthetic image"
    assert isinstance(result, CardResult)
    assert result.px_per_mm > 0
    assert 0 < result.confidence <= 1.0


def test_detect_card_px_per_mm_reasonable():
    """px_per_mm should match card_w / CARD_WIDTH_MM."""
    card_w = 500
    img, _ = make_card_image(card_w=card_w)
    result = detect_card(img)

    assert result is not None
    expected = card_w / CARD_WIDTH_MM
    assert result.px_per_mm == pytest.approx(expected, rel=0.08)


def test_detect_card_rectified_has_card_aspect_ratio():
    img, _ = make_card_image()
    result = detect_card(img)

    assert result is not None
    rh, rw = result.rectified.shape[:2]
    aspect = max(rw, rh) / min(rw, rh)
    assert abs(aspect - CARD_ASPECT_RATIO) < 0.15


def test_detect_card_confidence_high_for_clean_image():
    img, _ = make_card_image()
    result = detect_card(img)
    assert result is not None
    assert result.confidence > 0.5


# ---------------------------------------------------------------------------
# detect_card — failure cases
# ---------------------------------------------------------------------------


def test_detect_card_returns_none_for_blank_image():
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    result = detect_card(img)
    assert result is None


def test_detect_card_returns_none_for_wrong_aspect():
    """A square (1:1) shouldn't be mistaken for a credit card."""
    img = np.full((600, 800, 3), 30, dtype=np.uint8)
    # Draw a large square
    cv2.rectangle(img, (150, 100), (550, 500), (220, 220, 220), thickness=-1)
    result = detect_card(img)
    assert result is None


def test_detect_card_returns_none_for_tiny_rectangle():
    """A rectangle that is < 5% of the image area should be ignored."""
    img = np.full((600, 800, 3), 30, dtype=np.uint8)
    # Tiny rectangle: 60x38, area ≈ 2280 / 480000 ≈ 0.47%
    cv2.rectangle(img, (50, 50), (110, 88), (220, 220, 220), thickness=-1)
    result = detect_card(img)
    assert result is None
