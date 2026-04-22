#!/usr/bin/env python3
"""
Harness canônico de validação OMR.

Roda um detector plugável (omrchecker, cpp-omr, ...) contra todos os
casos de teste encontrados em inputs/ e compara com answer-key.json.

Uso:
    python3 run_validation.py                      # detector=omrchecker, tudo
    python3 run_validation.py --detector cpp-omr
    python3 run_validation.py --subset real        # só fotos reais
    python3 run_validation.py --subset synthetic
"""

import argparse
import json
import sys
import time
from pathlib import Path

from detectors.base import Detector
from detectors.omrchecker import OmrCheckerDetector
from detectors.cpp_omr import CppOmrDetector
from detectors.cpp_stub import CppDetector


ROOT = Path(__file__).parent
INPUTS = ROOT / "inputs"


def pick_detector(name: str) -> Detector:
    if name == "omrchecker":
        return OmrCheckerDetector()
    if name == "cpp-omr":
        return CppOmrDetector()
    if name == "cpp-stub":
        return CppDetector()
    raise ValueError(f"Detector desconhecido: {name}")


def _expected_for(image: Path, key_data: dict) -> dict | None:
    """Resolve o gabarito esperado para uma imagem.

    Aceita dois formatos de answer-key.json:
      - Comum:  {"q1": "A", "q2": "B", ...}  -> mesmo gabarito para todas
      - Por folha: {"sheet-01.jpg": {"q1": "A", ...}, ...}

    Detecta automaticamente olhando se os valores do root sao dicts.
    Retorna None se o arquivo nao tem entrada (por folha).
    """
    if key_data and all(isinstance(v, dict) for v in key_data.values()):
        return key_data.get(image.name)
    return key_data


def _iter_case_dirs():
    """Descobre diretorios de casos.

    - `inputs/<variante>/` -> sinteticos e perturbed (shipped com o repo)
    - `inputs/real/<cenario>/` -> fotos reais (desce um nivel; opcional,
      nao vem no repo publico — adicione as suas proprias fotos seguindo
      o schema em CONTRACT.md para reproduzir o benchmark "real")
    """
    for d in sorted(INPUTS.iterdir()):
        if not d.is_dir():
            continue
        if d.name == "real":
            for sub in sorted(d.iterdir()):
                if sub.is_dir():
                    yield sub, True
        else:
            yield d, False


def collect_cases(subset: str | None, name_filter: str | None = None) -> list[tuple[Path, Path, Path, dict]]:
    """Retorna lista de (image, template, answer_key_path, expected_dict)."""
    cases = []
    # Extensoes aceitas — fotos reais vem em jpg, sinteticos em png.
    exts = ("*.png", "*.jpg", "*.jpeg")

    for variant_dir, is_real in _iter_case_dirs():
        template = variant_dir / "template.json"
        answer_key = variant_dir / "answer-key.json"
        if not template.exists() or not answer_key.exists():
            continue

        is_perturbed = "perturb" in variant_dir.name and not is_real
        is_synthetic = not is_real and not is_perturbed

        if subset == "real" and not is_real:
            continue
        if subset == "perturbed" and not is_perturbed:
            continue
        if subset == "synthetic" and not is_synthetic:
            continue

        key_data = json.loads(answer_key.read_text())

        images = []
        for ext in exts:
            images.extend(variant_dir.glob(ext))
        for img in sorted(images):
            if img.stem in ("sheet-blank",):
                continue
            if name_filter and name_filter not in img.name:
                continue
            expected = _expected_for(img, key_data)
            if expected is None:
                continue  # foto sem entrada no answer-key.json (por folha)
            cases.append((img, template, answer_key, expected))
    return cases


def compare(expected: dict, detected: dict) -> tuple[int, int, list[str]]:
    correct = 0
    total = len(expected)
    errors = []
    for q, exp in expected.items():
        got = detected.get(q, "")
        if got == exp:
            correct += 1
        else:
            errors.append(f"{q}: exp={exp!r} got={got!r}")
    return correct, total, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detector", default="omrchecker")
    parser.add_argument("--subset", choices=["real", "synthetic", "perturbed"])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--filter",
        help="substring aplicada ao nome do arquivo (ex: sheet-01). "
             "Util para iterar em uma foto enquanto ajusta captura/motor.",
    )
    args = parser.parse_args()

    detector = pick_detector(args.detector)
    cases = collect_cases(args.subset, args.filter)

    # Proteção contra typo: `--filter sheet-99` sem match passaria em exit 0
    # porque total_correct == total_q == 0. Em CI ou script isso mascara
    # regressao silenciosa. Se o usuario explicitamente pediu filtro e nada
    # bateu, e erro de uso, nao sucesso vazio.
    if args.filter and not cases:
        print(f"ERRO: --filter {args.filter!r} nao matcheou nenhum caso.", file=sys.stderr)
        return 2

    print(f"Detector: {detector.name}  |  Casos: {len(cases)}\n")
    print(f"{'caso':<45} {'acc':>8} {'tempo':>8} {'nota'}")
    print("-" * 90)

    total_correct = total_q = total_time = 0
    failures = []

    for image, template, _, expected in cases:
        t0 = time.perf_counter()
        try:
            detected = detector.detect(image, template)
        except NotImplementedError as e:
            print(f"SKIP: {e}")
            return 2
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"{image.parent.name+'/'+image.name:<45} {'FAIL':>8} {elapsed:>6.2f}s  {str(e)[:40]}")
            failures.append((image, str(e)))
            total_time += elapsed
            continue
        elapsed = time.perf_counter() - t0

        correct, total, errors = compare(expected, detected)
        total_correct += correct
        total_q += total
        total_time += elapsed

        acc_str = f"{correct}/{total}"
        nota = "ok" if correct == total else f"err={len(errors)}"
        print(f"{image.parent.name+'/'+image.name:<45} {acc_str:>8} {elapsed:>6.2f}s  {nota}")
        if args.verbose and errors:
            for e in errors[:5]:
                print(f"    {e}")

    print("\n=== RESUMO ===")
    pct = 100 * total_correct / total_q if total_q else 0
    print(f"Acuracia: {total_correct}/{total_q} ({pct:.1f}%)")
    print(f"Tempo total: {total_time:.1f}s  |  media: {total_time/len(cases):.2f}s/caso" if cases else "")
    if failures:
        print(f"Falhas: {len(failures)}")
    return 0 if total_correct == total_q else 1


if __name__ == "__main__":
    sys.exit(main())
