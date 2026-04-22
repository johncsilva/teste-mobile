#!/usr/bin/env python3
"""
Gera versoes perturbadas (rotacao, perspectiva, ruido) da folha marcada
para testar robustez do OMRChecker.
"""

import cv2
import numpy as np
from pathlib import Path


SRC = Path("inputs/30q-5alt-2col-med/sheet-marked.png")
DST_DIR = Path("inputs/30q-5alt-2col-med-perturbed")


def rotate(img, deg):
    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))


def perspective(img, strength_px):
    (h, w) = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    s = strength_px
    dst = np.float32([[s, s], [w - s, 0], [w, h - s], [s, h]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (w, h), borderValue=(255, 255, 255))


def add_noise(img, sigma):
    noise = np.random.normal(0, sigma, img.shape).astype(np.int16)
    out = img.astype(np.int16) + noise
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    for cfg in ("template.json", "config.json"):
        src_cfg = Path("inputs/30q-5alt-2col-med") / cfg
        dst_cfg = DST_DIR / cfg
        dst_cfg.write_text(src_cfg.read_text())

    img = cv2.imread(str(SRC))

    cv2.imwrite(str(DST_DIR / "p0-reference.png"), img)
    cv2.imwrite(str(DST_DIR / "p1-rot-2deg.png"), rotate(img, 2))
    cv2.imwrite(str(DST_DIR / "p2-rot-5deg.png"), rotate(img, 5))
    cv2.imwrite(str(DST_DIR / "p3-persp-20px.png"), perspective(img, 20))
    cv2.imwrite(str(DST_DIR / "p4-persp-60px.png"), perspective(img, 60))
    cv2.imwrite(str(DST_DIR / "p5-noise-15.png"), add_noise(img, 15))
    cv2.imwrite(str(DST_DIR / "p6-noise-40.png"), add_noise(img, 40))

    print(f"Gerados 7 arquivos em {DST_DIR}")


if __name__ == "__main__":
    main()
