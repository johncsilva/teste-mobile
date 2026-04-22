#!/usr/bin/env python3
"""
Gera template.json e config.json para todas as variantes de folha,
derivando coordenadas das constantes de layout (margens, marcadores
fiduciais, dimensoes de bolha) usadas pelo gerador de folhas imprimiveis.

Uso:
    python3 build_templates.py             # gera templates para as 7 variantes
    python3 build_templates.py --dpi 200   # ajusta DPI (default 200)
"""

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


# ─── constantes (espelho do gerador PDF, em mm) ───────────────
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
MARGIN_LEFT_MM = 15.0
MARGIN_TOP_MM = 15.0
MARKER_SIZE_MM = 5.0
BUBBLE_H_SPACING_MM = 6.5
BUBBLE_V_SPACING_MM = 6.0
NUM_OFFSET_MM = 8.0
GRID_GAP_MM = 5.0  # grid_start_x = MARGIN_LEFT + MARKER_SIZE + 5mm

# draw_header consome 20.5mm (5 + 7 + 5.5 + 3)
HEADER_HEIGHT_MM = 20.5
TOP_OFFSET_MM = 3.0  # MARGIN_TOP + MARKER_SIZE + 3mm inicial
GRID_Y_OFFSET_MM = 5.0  # depois do header
LABEL_OFFSET_MM = 2.0  # y -= 2mm para linha das labels (A/B/C/D/E)


@dataclass
class Variant:
    label: str
    pdf_name: str
    num_questions: int
    num_alternatives: int
    cols: int
    bubble_radius_mm: float


VARIANTS = [
    Variant("10q-4alt-1col-med", "omr-10q-4alt-1col-med", 10, 4, 1, 2.0),
    Variant("20q-4alt-2col-med", "omr-20q-4alt-2col-med", 20, 4, 2, 2.0),
    Variant("20q-5alt-2col-med", "omr-20q-5alt-2col-med", 20, 5, 2, 2.0),
    Variant("30q-5alt-2col-lg", "omr-30q-5alt-2col-lg", 30, 5, 2, 3.0),
    Variant("30q-5alt-2col-med", "omr-30q-5alt-2col-med", 30, 5, 2, 2.0),
    Variant("30q-5alt-2col-sm", "omr-30q-5alt-2col-sm", 30, 5, 2, 1.5),
    Variant("50q-5alt-3col-med", "omr-50q-5alt-3col-med", 50, 5, 3, 2.0),
]


def mm_to_px(mm: float, dpi: int) -> float:
    """1mm = dpi / 25.4 px"""
    return mm * dpi / 25.4


def build_template(v: Variant, dpi: int) -> dict:
    """Gera template.json como dict (serializa depois)."""
    page_w = round(mm_to_px(PAGE_W_MM, dpi))
    page_h = round(mm_to_px(PAGE_H_MM, dpi))
    bubble_diameter = round(mm_to_px(v.bubble_radius_mm * 2, dpi))
    bubbles_gap_px = round(mm_to_px(BUBBLE_H_SPACING_MM, dpi))
    labels_gap_px = round(mm_to_px(BUBBLE_V_SPACING_MM, dpi))

    # Y da linha das labels (A B C D E) — não das bolhas!
    # Primeira bolha (q1) está em: y_label + BUBBLE_V_SPACING
    # Origem no topo da folha: MARGIN_TOP + MARKER_SIZE + TOP_OFFSET + HEADER + GRID_Y_OFFSET + LABEL_OFFSET
    grid_labels_y_mm = (
        MARGIN_TOP_MM
        + MARKER_SIZE_MM
        + TOP_OFFSET_MM
        + HEADER_HEIGHT_MM
        + GRID_Y_OFFSET_MM
        + LABEL_OFFSET_MM
    )
    first_bubble_center_y_mm = grid_labels_y_mm + BUBBLE_V_SPACING_MM
    first_bubble_top_left_y_mm = first_bubble_center_y_mm - v.bubble_radius_mm

    first_bubble_top_left_y = round(mm_to_px(first_bubble_top_left_y_mm, dpi))

    # X da primeira bolha por coluna
    col_width_mm = (
        PAGE_W_MM - 2 * MARGIN_LEFT_MM - 2 * MARKER_SIZE_MM - 10.0
    ) / v.cols
    grid_start_x_mm = MARGIN_LEFT_MM + MARKER_SIZE_MM + GRID_GAP_MM

    field_blocks = {}
    questions_per_col = (v.num_questions + v.cols - 1) // v.cols

    q_start = 0
    for col_idx in range(v.cols):
        col_x_mm = grid_start_x_mm + col_idx * col_width_mm
        first_bubble_center_x_mm = col_x_mm + NUM_OFFSET_MM + v.bubble_radius_mm
        first_bubble_top_left_x_mm = first_bubble_center_x_mm - v.bubble_radius_mm

        origin_x = round(mm_to_px(first_bubble_top_left_x_mm, dpi))

        q_start_in_col = q_start + 1
        q_end_in_col = min(q_start + questions_per_col, v.num_questions)

        field_blocks[f"MCQ_Col{col_idx + 1}"] = {
            "fieldType": f"QTYPE_MCQ{v.num_alternatives}",
            "origin": [origin_x, first_bubble_top_left_y],
            "fieldLabels": [f"q{q_start_in_col}..{q_end_in_col}"],
            "bubblesGap": bubbles_gap_px,
            "labelsGap": labels_gap_px,
        }

        q_start += questions_per_col

    return {
        "pageDimensions": [page_w, page_h],
        "bubbleDimensions": [bubble_diameter, bubble_diameter],
        "fieldBlocks": field_blocks,
    }


def build_config(v: Variant, dpi: int) -> dict:
    page_w = round(mm_to_px(PAGE_W_MM, dpi))
    page_h = round(mm_to_px(PAGE_H_MM, dpi))
    return {
        "dimensions": {
            "display_height": page_h,
            "display_width": page_w,
            "processing_height": page_h,
            "processing_width": page_w,
        },
        "outputs": {"show_image_level": 0},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--inputs", type=Path, default=Path("inputs"))
    args = parser.parse_args()

    for v in VARIANTS:
        dst = args.inputs / v.label
        dst.mkdir(parents=True, exist_ok=True)

        src_img = args.inputs / f"{v.pdf_name}-1.png"
        if not src_img.exists():
            print(f"ERRO: nao encontrei {src_img}, pulando {v.label}")
            continue

        dst_img = dst / "sheet-blank.png"
        if not dst_img.exists():
            shutil.copy(src_img, dst_img)

        template = build_template(v, args.dpi)
        config = build_config(v, args.dpi)

        (dst / "template.json").write_text(json.dumps(template, indent=2))
        (dst / "config.json").write_text(json.dumps(config, indent=2))

        print(
            f"{v.label}: origin_col1={template['fieldBlocks']['MCQ_Col1']['origin']} "
            f"bubble={template['bubbleDimensions']} "
            f"pageDim={template['pageDimensions']}"
        )


if __name__ == "__main__":
    main()
