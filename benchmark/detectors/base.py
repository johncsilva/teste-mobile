"""Interface comum para detectores OMR.

Cada implementação (oráculo OMRChecker, futuro motor C++) herda de `Detector`
e recebe uma imagem + caminho do template, devolvendo {q1: "A", q2: "B", ...}.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class Detector(ABC):
    name: str = "base"

    @abstractmethod
    def detect(self, image_path: Path, template_path: Path) -> dict[str, str]:
        """Retorna {'q1': 'A', 'q2': 'B', ...}. Valor vazio '' para nao detectado."""
        ...
