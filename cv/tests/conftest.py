"""Shared fixtures for all CV pipeline tests."""

from __future__ import annotations

import io
import os

import cv2
import numpy as np
import pytest
from PIL import Image

# Use mock segmentation everywhere — no Replicate API key needed
os.environ["SEV_MOCK_SEGMENTATION"] = "1"

CARD_ASPECT = 85.6 / 53.98  # ≈ 1.5857


# ---------------------------------------------------------------------------
# Image fixtures
# ---------------------------------------------------------------------------


def _make_card_bgr(img_w: int = 800, img_h: int = 600) -> tuple[np.ndarray, tuple]:
    """Dark-background image with a white credit-card-proportioned rectangle."""
    img = np.full((img_h, img_w, 3), 30, dtype=np.uint8)
    card_w = 500
    card_h = int(round(card_w / CARD_ASPECT))  # ≈ 315
    x1 = (img_w - card_w) // 2
    y1 = (img_h - card_h) // 2
    x2 = x1 + card_w
    y2 = y1 + card_h
    cv2.rectangle(img, (x1, y1), (x2, y2), (220, 220, 220), thickness=-1)
    return img, (x1, y1, x2, y2)


@pytest.fixture
def card_image() -> tuple[np.ndarray, tuple]:
    return _make_card_bgr()


@pytest.fixture
def card_image_bytes() -> bytes:
    img, _ = _make_card_bgr()
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture
def sharp_bright_image_bytes() -> bytes:
    """A plain gray image that is sharp and normally bright."""
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture
def blurry_image_bytes() -> bytes:
    """A very blurry image (low Laplacian variance)."""
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    # Extreme blur → near-zero Laplacian variance
    img = cv2.GaussianBlur(img, (151, 151), 50)
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Hand-result mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hand_result():
    from pipeline.hand_detect import HandResult

    tips = {
        "thumb":  (200, 80),
        "index":  (280, 60),
        "middle": (350, 55),
        "ring":   (420, 62),
        "pinky":  (490, 80),
    }
    return HandResult(
        landmarks=[(320, 300)] * 21,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px={f: 40.0 for f in tips},
    )


# ---------------------------------------------------------------------------
# Card-result mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_card_result():
    from pipeline.card_detect import CardResult

    corners = np.array(
        [[150, 142], [650, 142], [650, 457], [150, 457]], dtype=np.float32
    )
    return CardResult(
        corners=corners,
        px_per_mm=500 / 85.6,  # ≈ 5.84
        rectified=np.zeros((315, 500, 3), dtype=np.uint8),
        confidence=0.97,
    )


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import app as fastapi_app

    return TestClient(fastapi_app)
