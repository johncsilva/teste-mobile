#!/usr/bin/env python3
"""
Simula o preenchimento de bolhas na folha OMR para teste.
Usa as mesmas coordenadas do template.json.
"""

import cv2
import numpy as np
from pathlib import Path


# Coordenadas do template 30q-5alt-2col-med (em px @ 200 DPI)
BUBBLE_SIZE = 32
BUBBLES_GAP = 51
LABELS_GAP = 47
COL1_ORIGIN = (260, 429)
COL2_ORIGIN = (890, 429)
QUESTIONS_PER_COL = 15


def bubble_center(col_origin, q_idx_in_col, alt_idx):
    """Retorna (cx, cy) do centro da bolha na coluna."""
    top_left_x = col_origin[0] + alt_idx * BUBBLES_GAP
    top_left_y = col_origin[1] + q_idx_in_col * LABELS_GAP
    return (top_left_x + BUBBLE_SIZE // 2, top_left_y + BUBBLE_SIZE // 2)


def mark_bubble(img, q_num_1_indexed, alt_letter):
    """Preenche a bolha da questão q com a alternativa dada (A-E)."""
    alt_idx = ord(alt_letter.upper()) - ord("A")
    if q_num_1_indexed <= QUESTIONS_PER_COL:
        col_origin = COL1_ORIGIN
        q_idx = q_num_1_indexed - 1
    else:
        col_origin = COL2_ORIGIN
        q_idx = q_num_1_indexed - QUESTIONS_PER_COL - 1

    cx, cy = bubble_center(col_origin, q_idx, alt_idx)
    cv2.circle(img, (cx, cy), BUBBLE_SIZE // 2 - 3, (0, 0, 0), thickness=-1)


def main():
    src = Path("inputs/omr-30q-5alt-2col-med-1.png")
    dst_dir = Path("inputs/30q-5alt-2col-med")
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Gabarito: Q1=A, Q2=B, ..., Q5=E, Q6=A, ... (padrão cíclico)
    # Dá 30 respostas previsíveis para validação.
    answers = {q: chr(ord("A") + (q - 1) % 5) for q in range(1, 31)}

    img = cv2.imread(str(src))
    for q, alt in answers.items():
        mark_bubble(img, q, alt)

    out_path = dst_dir / "sheet-marked.png"
    cv2.imwrite(str(out_path), img)
    print(f"Gerado: {out_path}")
    print(f"Gabarito esperado: {answers}")


if __name__ == "__main__":
    main()
