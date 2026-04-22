#!/usr/bin/env python3
"""
Marca bolhas sinteticamente em cada variante, usando os templates recem-criados.
Gera sheet-marked.png em cada diretorio inputs/<variant>/ e salva o gabarito
esperado em answer-key.json.
"""

import json
from pathlib import Path

import cv2


def load_template(dir_path: Path) -> dict:
    return json.loads((dir_path / "template.json").read_text())


def parse_field_label(label: str) -> tuple[int, int]:
    """Converte 'q1..15' em (1, 15)."""
    if ".." in label:
        name, rng = label, None
        for part in label.split(".."):
            pass
        left, right = label.split("..")
        start = int(left.lstrip("q"))
        end = int(right)
        return start, end
    else:
        q = int(label.lstrip("q"))
        return q, q


def mark_sheet(variant_dir: Path) -> None:
    template = load_template(variant_dir)
    bubble_dim = template["bubbleDimensions"][0]
    blocks = template["fieldBlocks"]

    src = variant_dir / "sheet-blank.png"
    img = cv2.imread(str(src))
    answers = {}

    for _, block in blocks.items():
        origin_x, origin_y = block["origin"]
        bubbles_gap = block["bubblesGap"]
        labels_gap = block["labelsGap"]
        field_type = block["fieldType"]
        num_alt = int(field_type.replace("QTYPE_MCQ", ""))

        for fld in block["fieldLabels"]:
            start, end = parse_field_label(fld)
            for q in range(start, end + 1):
                q_idx_in_block = q - start
                alt_idx = (q - 1) % num_alt
                cx = origin_x + alt_idx * bubbles_gap + bubble_dim // 2
                cy = origin_y + q_idx_in_block * labels_gap + bubble_dim // 2
                cv2.circle(img, (cx, cy), bubble_dim // 2 - 3, (0, 0, 0), -1)
                answers[f"q{q}"] = chr(ord("A") + alt_idx)

    out_img = variant_dir / "sheet-marked.png"
    cv2.imwrite(str(out_img), img)
    (variant_dir / "answer-key.json").write_text(json.dumps(answers, indent=2))
    print(f"{variant_dir.name}: {len(answers)} questoes marcadas")


def main():
    inputs = Path("inputs")
    for d in sorted(inputs.iterdir()):
        if not d.is_dir() or "perturbed" in d.name:
            continue
        if (d / "template.json").exists() and (d / "sheet-blank.png").exists():
            mark_sheet(d)


if __name__ == "__main__":
    main()
