"""Converte o vetor reconstruído numa imagem PGM em tons de cinza."""
from __future__ import annotations

import numpy as np


def pgm(f: np.ndarray, largura: int, altura: int) -> bytes:
    absoluto = np.abs(f)
    maximo = absoluto.max()
    pixels = np.zeros_like(absoluto) if maximo == 0 else np.floor(absoluto / maximo * 255 + 0.5)
    imagem = pixels.astype(np.uint8).reshape((altura, largura), order="F")
    return f"P5\n{largura} {altura}\n255\n".encode() + imagem.tobytes()
