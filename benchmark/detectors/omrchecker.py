"""Adaptador do OMRChecker para a interface Detector.

OMRChecker espera um diretorio completo (imagem + template.json + config.json).
Este adaptador monta um diretorio temporario com uma unica imagem, invoca
o CLI e parseia o CSV de saida.

NOTA: o repo publico nao inclui o clone do OMRChecker — para usar este
detector como baseline comparativo, clone manualmente em benchmark/OMRChecker/:

    git clone https://github.com/Udayraj123/OMRChecker.git benchmark/OMRChecker

Sem o clone presente, este detector falha com FileNotFoundError claro na
primeira invocacao. Os detectores `cpp_omr` e `cpp_stub` nao dependem dele.
"""

import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Detector

OMR_DIR = Path(__file__).resolve().parent.parent / "OMRChecker"


class OmrCheckerDetector(Detector):
    name = "omrchecker"

    def detect(self, image_path: Path, template_path: Path) -> dict[str, str]:
        template_dir = template_path.parent
        config_path = template_dir / "config.json"

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            shutil.copy(image_path, workdir / image_path.name)
            shutil.copy(template_path, workdir / "template.json")
            if config_path.exists():
                shutil.copy(config_path, workdir / "config.json")

            out_dir = workdir / "out"
            out_dir.mkdir()

            result = subprocess.run(
                [
                    "python3",
                    "main.py",
                    "-i",
                    str(workdir),
                    "-o",
                    str(out_dir),
                ],
                cwd=OMR_DIR,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"OMRChecker falhou ({result.returncode}): {result.stderr[-500:]}"
                )

            csvs = list((out_dir / "Results").glob("*.csv"))
            if not csvs:
                raise RuntimeError("OMRChecker nao gerou CSV de resultados")

            with open(csvs[0]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["file_id"] == image_path.name:
                        return {k: v for k, v in row.items() if k.startswith("q")}

            raise RuntimeError(f"Nao encontrei linha para {image_path.name} no CSV")
