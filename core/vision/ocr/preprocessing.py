"""Image preprocessing utilities for OCR."""

import cv2
import numpy as np


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    Preprocess image to improve OCR accuracy.

    - CLAHE contrast enhancement
    - Mild sharpening
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    kernel = np.array(
        [
            [-0.5, -0.5, -0.5],
            [-0.5, 5.0, -0.5],
            [-0.5, -0.5, -0.5],
        ]
    )
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    return sharpened
