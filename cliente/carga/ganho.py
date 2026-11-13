"""Ganho de sinal definido no enunciado, aplicado no cliente antes do envio."""
from __future__ import annotations

import numpy as np


def fatores_ganho(S: int) -> np.ndarray:
    """γ_l = 100 + (1/20) * l * sqrt(l), para l = 1..S."""
    l = np.arange(1, S + 1, dtype=np.float64)
    return 100 + (1 / 20) * l * np.sqrt(l)


def aplicar_ganho(g: np.ndarray, S: int, N: int) -> np.ndarray:
    """Devolve uma cópia com g[c*S + (l-1)] multiplicado por γ_l (amostras agrupadas por sensor)."""
    if g.size != S * N:
        raise ValueError(f"sinal com {g.size} amostras; S*N = {S * N}")
    return (g.reshape(N, S) * fatores_ganho(S)).reshape(-1)
