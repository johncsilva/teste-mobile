"""Stub para o futuro motor C++/opencv-mobile.

Quando o motor estiver pronto, esta classe chamara a biblioteca via ctypes
(desktop) ou via processo filho (testes).
"""

from pathlib import Path

from .base import Detector


class CppDetector(Detector):
    name = "cpp-omr"

    def __init__(self, lib_path: Path | None = None):
        self.lib_path = lib_path

    def detect(self, image_path: Path, template_path: Path) -> dict[str, str]:
        raise NotImplementedError(
            "Motor C++ ainda nao implementado. Ver CONTRACT.md"
        )
