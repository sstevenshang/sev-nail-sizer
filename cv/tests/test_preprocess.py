"""Tests for pipeline/preprocess.py."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from pipeline.preprocess import (
    BLUR_THRESHOLD,
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    MAX_LONG_SIDE,
    check_blur,
    check_brightness,
    preprocess,
    resize_to_max,
)


def _encode_jpeg(bgr: np.ndarray) -> bytes:
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# resize_to_max
# ---------------------------------------------------------------------------


def test_resize_to_max_shrinks_landscape():
    img = np.zeros((1000, 3000, 3), dtype=np.uint8)
    out = resize_to_max(img, max_side=2048)
    assert max(out.shape[:2]) == 2048
    assert out.shape[0] / out.shape[1] == pytest.approx(1000 / 3000, rel=0.01)


def test_resize_to_max_shrinks_portrait():
    img = np.zeros((3000, 1000, 3), dtype=np.uint8)
    out = resize_to_max(img, max_side=2048)
    assert max(out.shape[:2]) == 2048


def test_resize_to_max_no_upscale():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    out = resize_to_max(img)
    assert out.shape == img.shape


# ---------------------------------------------------------------------------
# check_blur
# ---------------------------------------------------------------------------


def test_check_blur_sharp_image():
    # Checkerboard → high Laplacian variance
    img = np.zeros((200, 200), dtype=np.uint8)
    img[::2, ::2] = 255
    score = check_blur(img)
    assert score > BLUR_THRESHOLD


def test_check_blur_blurry_image():
    img = np.full((200, 200), 128, dtype=np.uint8)
    img = cv2.GaussianBlur(img, (101, 101), 30)
    score = check_blur(img)
    assert score < BLUR_THRESHOLD


# ---------------------------------------------------------------------------
# check_brightness
# ---------------------------------------------------------------------------


def test_check_brightness_dark():
    img = np.full((100, 100), 10, dtype=np.uint8)
    mean, level = check_brightness(img)
    assert level == "dark"
    assert mean < BRIGHTNESS_MIN


def test_check_brightness_normal():
    img = np.full((100, 100), 128, dtype=np.uint8)
    mean, level = check_brightness(img)
    assert level == "normal"


def test_check_brightness_bright():
    img = np.full((100, 100), 250, dtype=np.uint8)
    mean, level = check_brightness(img)
    assert level == "bright"
    assert mean > BRIGHTNESS_MAX


# ---------------------------------------------------------------------------
# preprocess end-to-end
# ---------------------------------------------------------------------------


def test_preprocess_returns_bgr_and_quality():
    img_rgb = np.full((480, 640, 3), 128, dtype=np.uint8)
    raw = _encode_jpeg(cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
    bgr, quality = preprocess(raw)

    assert bgr.ndim == 3
    assert bgr.shape[2] == 3
    assert quality.brightness_level == "normal"


def test_preprocess_rejects_non_image():
    with pytest.raises(Exception):
        preprocess(b"not an image")


def test_preprocess_resizes_large_image():
    large = np.zeros((4000, 4000, 3), dtype=np.uint8)
    raw = _encode_jpeg(large)
    bgr, _ = preprocess(raw)
    assert max(bgr.shape[:2]) <= MAX_LONG_SIDE
