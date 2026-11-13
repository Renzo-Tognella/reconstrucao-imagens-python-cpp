"""Só biblioteca padrão: precisa rodar antes de qualquer importação de NumPy ou SciPy."""
from __future__ import annotations

import os

VARIAVEIS_DE_THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def fixar_threads_blas(quantidade: int) -> None:
    for nome in VARIAVEIS_DE_THREADS:
        os.environ[nome] = str(quantidade)
