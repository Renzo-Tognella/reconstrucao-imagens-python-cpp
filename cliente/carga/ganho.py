from __future__ import annotations

import numpy as np


def fatores_ganho(S: int) -> np.ndarray:
    l = np.arange(1, S + 1, dtype=np.float64)
    return 100 + (1 / 20) * l * np.sqrt(l)


def aplicar_ganho(g: np.ndarray, S: int, N: int) -> np.ndarray:
    if g.size != S * N:
        raise ValueError(f"sinal com {g.size} amostras; S*N = {S * N}")
    return (g.reshape(N, S) * fatores_ganho(S)).reshape(-1)
