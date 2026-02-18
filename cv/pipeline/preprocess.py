"""Image preprocessing: EXIF orientation, resize, blur/brightness checks."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

MAX_LONG_SIDE = 2048
BLUR_THRESHOLD = 100.0
BRIGHTNESS_MIN = 40.0
BRIGHTNESS_MAX = 240.0


@dataclass
class QualityCheck:
    blur_score: float
    brightness_mean: float
    is_sharp: bool
    brightness_level: str  # "dark" | "normal" | "bright"


def auto_orient(pil_image: Image.Image) -> Image.Image:
    """Rotate image to correct orientation based on EXIF data."""
    try:
        exif_data = pil_image._getexif()  # type: ignore[attr-defined]
        if exif_data is None:
            return pil_image
        orientation_key = next(
            (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
        )
        if orientation_key is None or orientation_key not in exif_data:
            return pil_image
        orientation = exif_data[orientation_key]
        rotations = {3: 180, 6: 270, 8: 90}
        if orientation in rotations:
            pil_image = pil_image.rotate(rotations[orientation], expand=True)
    except Exception:
        pass
    return pil_image


def resize_to_max(image: np.ndarray, max_side: int = MAX_LONG_SIDE) -> np.ndarray:
    """Resize so the longest side is at most max_side, preserving aspect ratio."""
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image
    scale = max_side / longest
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def check_blur(gray: np.ndarray) -> float:
    """Return Laplacian variance — higher means sharper."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def check_brightness(gray: np.ndarray) -> Tuple[float, str]:
    """Return (mean_brightness, level_label)."""
    mean = float(gray.mean())
    if mean < BRIGHTNESS_MIN:
        level = "dark"
    elif mean > BRIGHTNESS_MAX:
        level = "bright"
    else:
        level = "normal"
    return mean, level


def preprocess(image_bytes: bytes) -> Tuple[np.ndarray, QualityCheck]:
    """
    Load bytes → auto-orient → resize → assess quality.
    Returns (bgr_image, quality_check).
    """
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pil_image = auto_orient(pil_image)
    image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    image = resize_to_max(image)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = check_blur(gray)
    brightness_mean, brightness_level = check_brightness(gray)

    quality = QualityCheck(
        blur_score=blur_score,
        brightness_mean=brightness_mean,
        is_sharp=blur_score > BLUR_THRESHOLD,
        brightness_level=brightness_level,
    )
    return image, quality
