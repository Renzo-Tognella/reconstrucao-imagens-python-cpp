from __future__ import annotations

import numpy as np
from scipy.linalg.blas import daxpy, ddot, dnrm2

from recon_py.dominio.algoritmos.produtos import exigir_formato, h_vezes, ht_vezes
from recon_py.dominio.algoritmos.resultado import (
    MAX_ITERACOES,
    MAX_ITERATIONS,
    TOLERANCE,
    TOLERANCIA,
    ZERO_RESIDUAL,
    Resultado,
    concluir,
    exigir_denominador,
    exigir_finito,
)


def cgne(H: np.ndarray, g: np.ndarray) -> Resultado:
    exigir_formato(H, g)
    linhas, colunas = H.shape
    f = np.zeros(colunas)
    r = g.copy()
    w = np.empty(linhas)
    z = np.empty(colunas)
    p = np.empty(colunas)
    rr = exigir_finito(ddot(r, r), "rr")
    rnorm = exigir_finito(dnrm2(r), "norma do resíduo")
    normas = [rnorm]
    ht_vezes(H, r, p)
    if rr == 0:
        return concluir(f, normas, 0, ZERO_RESIDUAL)
    for i in range(1, MAX_ITERACOES + 1):
        alpha = exigir_finito(rr / exigir_denominador(ddot(p, p), "pp"), "alpha")
        daxpy(p, f, a=alpha)
        h_vezes(H, p, w)
        daxpy(w, r, a=-alpha)
        novo = exigir_finito(dnrm2(r), "norma do resíduo")
        normas.append(novo)
        if abs(novo - rnorm) < TOLERANCIA:
            return concluir(f, normas, i, TOLERANCE)
        rnorm = novo
        rr2 = exigir_finito(ddot(r, r), "rr")
        if rr2 == 0:
            return concluir(f, normas, i, ZERO_RESIDUAL)
        beta = exigir_finito(rr2 / rr, "beta")
        ht_vezes(H, r, z)
        daxpy(p, z, a=beta)
        p, z = z, p
        rr = rr2
    return concluir(f, normas, MAX_ITERACOES, MAX_ITERATIONS)
