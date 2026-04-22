#!/usr/bin/env python3
"""
Roda OMRChecker em todas as variantes e calcula acuracia comparando
com answer-key.json gerado por mark_all.py.

Emite um resumo textual ao final.
"""

import csv
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).parent
OMR_DIR = ROOT / "OMRChecker"
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"


def run_variant(variant_dir: Path, output_dir: Path) -> tuple[float, dict | None]:
    """Roda OMRChecker na variante e retorna (tempo_s, respostas_detectadas)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # Limpa outputs antigos para resultado limpo
    for child in output_dir.iterdir():
        if child.is_dir():
            for f in child.rglob("*"):
                if f.is_file():
                    f.unlink()

    t0 = time.perf_counter()
    result = subprocess.run(
        [
            "python3",
            "main.py",
            "-i",
            str(variant_dir.resolve()),
            "-o",
            str(output_dir.resolve()),
        ],
        cwd=OMR_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"FALHOU {variant_dir.name}: {result.stderr[-500:]}")
        return elapsed, None

    # Encontra CSV em Results/
    results_csv = list((output_dir / "Results").glob("*.csv"))
    if not results_csv:
        return elapsed, None

    detected = {}
    with open(results_csv[0]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["file_id"] == "sheet-marked.png":
                detected = {k: v for k, v in row.items() if k.startswith("q")}
                break

    return elapsed, detected


def compare(expected: dict, detected: dict) -> tuple[int, int, list[str]]:
    correct = 0
    total = len(expected)
    errors = []
    for q, exp in expected.items():
        got = detected.get(q, "")
        if got == exp:
            correct += 1
        else:
            errors.append(f"{q}: esperado={exp!r} detectado={got!r}")
    return correct, total, errors


def main():
    variants = sorted(
        d for d in INPUTS.iterdir()
        if d.is_dir() and (d / "template.json").exists() and "perturbed" not in d.name
    )

    print(f"{'variante':<22} {'acc':>7} {'tempo':>8}  {'nota'}")
    print("-" * 70)

    rows = []
    for v in variants:
        exp_path = v / "answer-key.json"
        if not exp_path.exists():
            print(f"{v.name:<22} --- sem answer-key")
            continue
        expected = json.loads(exp_path.read_text())

        out_dir = OUTPUTS / v.name
        elapsed, detected = run_variant(v, out_dir)

        if detected is None:
            print(f"{v.name:<22} FAIL    {elapsed:>6.2f}s  (sem CSV)")
            rows.append((v.name, 0, len(expected), elapsed, "FAIL"))
            continue

        correct, total, errors = compare(expected, detected)
        acc = f"{correct}/{total}"
        nota = "ok" if correct == total else f"err={len(errors)}"
        print(f"{v.name:<22} {acc:>7} {elapsed:>6.2f}s  {nota}")
        if errors and len(errors) <= 3:
            for e in errors:
                print(f"    {e}")
        rows.append((v.name, correct, total, elapsed, nota))

    # Resumo
    print("\n=== RESUMO ===")
    total_correct = sum(r[1] for r in rows)
    total_questions = sum(r[2] for r in rows)
    total_time = sum(r[3] for r in rows)
    print(f"Acuracia global: {total_correct}/{total_questions} "
          f"({100*total_correct/total_questions:.1f}%)")
    print(f"Tempo total (wall, inclui overhead CLI): {total_time:.1f}s")
    print(f"Folhas: {len(rows)}")


if __name__ == "__main__":
    main()
