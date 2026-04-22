"""Adaptador para o motor C++ via CLI.

Usa o binario `omr_cli` construido em build/ (raiz do repo). Paga o custo de
spawn de processo por folha, mas mantem a interface igual ao detector
OMRChecker — permite comparar direto no mesmo harness.

Quando o motor for integrado via FFI/JSI no mobile, esse adapter pode ser
substituido por ctypes.cdll.LoadLibrary("libomr.so") sem mudar a interface.
"""

import json
import subprocess
from pathlib import Path

from .base import Detector

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BINARY = REPO_ROOT / "build" / "omr_cli"

# mapa template OMRChecker (1-indexed, v0) -> template novo schema (v1)
def _translate_template_if_needed(template_path: Path, work_template: Path) -> None:
    """Se o template estiver no schema OMRChecker, converte para o schema do motor C++."""
    data = json.loads(template_path.read_text())
    if "blocks" in data and "fiducials" in data:
        work_template.write_text(json.dumps(data))
        return

    # schema OMRChecker: pageDimensions / bubbleDimensions / fieldBlocks
    page = data["pageDimensions"]
    bubble = data["bubbleDimensions"]
    blocks = []
    for name, block in data["fieldBlocks"].items():
        labels = block["fieldLabels"]
        # labels vem como "q1..15" — expandir
        qs = []
        for lbl in labels:
            if ".." in lbl:
                prefix = lbl.split("..")[0]
                # ex: "q1..15" -> prefix="q1", end="15"
                # extrai numero inicial de prefix
                num_start = ""
                i = len(prefix) - 1
                while i >= 0 and prefix[i].isdigit():
                    num_start = prefix[i] + num_start
                    i -= 1
                name_prefix = prefix[:i + 1]
                start = int(num_start)
                end = int(lbl.split("..")[1])
                for n in range(start, end + 1):
                    qs.append(f"{name_prefix}{n}")
            else:
                qs.append(lbl)

        # OMRChecker trata `origin` como top-left da ROI; o motor C++ trata
        # como centro da bolha. Deslocamos meia-ROI em cada eixo para alinhar
        # a semantica — sem esse shift o C++ mede fill_ratio fora do circulo
        # marcado, o que e fatal em fotos reais (marca nao-centralizada).
        ox, oy = block["origin"]
        ox_centered = ox + (bubble[0] + 1) // 2
        oy_centered = oy + (bubble[1] + 1) // 2

        blocks.append({
            "type": "mcq",
            "alternatives": ["A", "B", "C", "D", "E"][: len(_infer_alternatives(block))],
            "origin": [ox_centered, oy_centered],
            "bubble_gap": block["bubblesGap"],
            "label_gap": block["labelsGap"],
            "questions": {
                "start": int(qs[0].lstrip("q")),
                "end": int(qs[-1].lstrip("q")),
            },
        })

    # Fiduciais: convencao do template usa margem 15mm e marker 5mm,
    # entao o centro do marker fica a 17.5mm do canto da folha. Derivamos o
    # DPI efetivo do template assumindo A4 (210mm de largura) — funciona para
    # qualquer DPI que o `build_templates.py --dpi` produza, nao so 200.
    FIDUCIAL_OFFSET_MM = 17.5
    FIDUCIAL_SIZE_MM = 5.0
    A4_WIDTH_MM = 210.0
    w, h = page[0], page[1]
    dpi = w / A4_WIDTH_MM * 25.4
    FIDUCIAL_OFFSET = round(FIDUCIAL_OFFSET_MM * dpi / 25.4)
    FIDUCIAL_SIZE = round(FIDUCIAL_SIZE_MM * dpi / 25.4)
    fiducials_positions = [
        [FIDUCIAL_OFFSET, FIDUCIAL_OFFSET],               # TL
        [w - FIDUCIAL_OFFSET, FIDUCIAL_OFFSET],           # TR
        [FIDUCIAL_OFFSET, h - FIDUCIAL_OFFSET],           # BL
        [w - FIDUCIAL_OFFSET, h - FIDUCIAL_OFFSET],       # BR
    ]

    converted = {
        "version": 1,
        "id": template_path.parent.name,
        "page_dimensions": page,
        "bubble_dimensions": bubble,
        "fiducials": {
            "type": "corner_squares",
            "size_px": FIDUCIAL_SIZE,
            "positions": fiducials_positions,
        },
        "blocks": blocks,
        "thresholds": {"low": 0.25, "high": 0.60},
    }
    work_template.write_text(json.dumps(converted))


def _infer_alternatives(block):
    # Derivacao simples: QTYPE_MCQ5 -> 5; QTYPE_MCQ4 -> 4.
    ftype = block.get("fieldType", "QTYPE_MCQ5")
    if ftype.endswith("4"):
        return ["A", "B", "C", "D"]
    return ["A", "B", "C", "D", "E"]


class CppOmrDetector(Detector):
    name = "cpp-omr"

    def __init__(self, binary: Path = BINARY):
        self.binary = binary

    def detect(self, image_path: Path, template_path: Path) -> dict[str, str]:
        if not self.binary.exists():
            raise NotImplementedError(
                f"Binario nao encontrado em {self.binary}. "
                "Rode `cmake -S . -B build && cmake --build build -j` na raiz do repo"
            )

        # template precisa estar no schema v1 para o motor C++
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            work_tmpl = Path(f.name)
        _translate_template_if_needed(template_path, work_tmpl)

        try:
            res = subprocess.run(
                [str(self.binary), str(image_path), str(work_tmpl)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            work_tmpl.unlink(missing_ok=True)

        if res.returncode != 0 and not res.stdout.strip():
            raise RuntimeError(f"omr_cli falhou ({res.returncode}): {res.stderr[-300:]}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Saida nao-JSON do omr_cli: {res.stdout[:200]}")

        if data.get("status") != "ok":
            raise RuntimeError(f"motor retornou erro: {data.get('error_code')} — {data.get('error_message')}")

        out: dict[str, str] = {}
        for q, info in data.get("questions", {}).items():
            sel = info.get("selected")
            out[q] = sel if isinstance(sel, str) else ""
        return out
