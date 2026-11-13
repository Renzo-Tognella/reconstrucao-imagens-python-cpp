"""Produtos H·x e Hᵀ·x, os passos caros dos dois algoritmos."""
from __future__ import annotations

import numpy as np


def exigir_formato(H: np.ndarray, g: np.ndarray) -> None:
    # Qualquer outro formato faria a BLAS trabalhar sobre uma cópia a cada chamada, sem aviso.
    if H.ndim != 2 or not H.flags.f_contiguous or H.dtype != np.float64:
        raise ValueError("H precisa ser float64 nativo, 2D e contígua por colunas")
    if g.shape != (H.shape[0],) or g.dtype != np.float64:
        raise ValueError(f"sinal {g.dtype} com forma {g.shape}; esperado float64 nativo ({H.shape[0]},)")


# Os produtos usam np.dot, que chama a mesma cblas_dgemv, porque o wrapper dgemv do SciPy não solta
# o GIL: com ele, W threads rodariam em série. O produto domina o custo; as operações de vetor são curtas.
def h_vezes(H: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    np.dot(H, x, out=y)


def ht_vezes(H: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    np.dot(H.T, x, out=y)


def aquecer_produtos(H: np.ndarray) -> None:
    """Lê todas as páginas de H e inicializa a BLAS, para esses custos ficarem fora de `duration_s`."""
    linhas, colunas = H.shape
    np.add.reduce(H, axis=None)
    y = np.empty(linhas)
    h_vezes(H, np.ones(colunas), y)
    ht_vezes(H, y, np.empty(colunas))
