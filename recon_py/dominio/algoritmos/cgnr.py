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


def cgnr(H: np.ndarray, g: np.ndarray) -> Resultado:
    exigir_formato(H, g)
    linhas, colunas = H.shape
    f = np.zeros(colunas)
    r = g.copy()
    w = np.empty(linhas)
    z = np.empty(colunas)
    rnorm = exigir_finito(dnrm2(r), "norma do resíduo")
    normas = [rnorm]
    ht_vezes(H, r, z)
    p = z.copy()
    zz = exigir_finito(ddot(z, z), "zz")
    if zz == 0:
        return concluir(f, normas, 0, ZERO_RESIDUAL)
    for i in range(1, MAX_ITERACOES + 1):
        h_vezes(H, p, w)
        alpha = exigir_finito(zz / exigir_denominador(ddot(w, w), "ww"), "alpha")
        daxpy(p, f, a=alpha)
        daxpy(w, r, a=-alpha)
        novo = exigir_finito(dnrm2(r), "norma do resíduo")
        normas.append(novo)
        if abs(novo - rnorm) < TOLERANCIA:
            return concluir(f, normas, i, TOLERANCE)
        rnorm = novo
        ht_vezes(H, r, z)
        zz2 = exigir_finito(ddot(z, z), "zz")
        if zz2 == 0:
            return concluir(f, normas, i, ZERO_RESIDUAL)
        beta = exigir_finito(zz2 / zz, "beta")
        daxpy(p, z, a=beta)
        p, z = z, p
        zz = zz2
    return concluir(f, normas, MAX_ITERACOES, MAX_ITERATIONS)
