from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

TOLERANCIA = 1e-4
MAX_ITERACOES = 10

TOLERANCE = "tolerance"
MAX_ITERATIONS = "max_iterations"
ZERO_RESIDUAL = "zero_residual"


class FalhaNumerica(Exception):
    pass


@dataclass(frozen=True)
class Resultado:
    f: np.ndarray
    residual_norms: list[float]
    iterations: int
    stop_reason: str


def exigir_finito(valor: float, nome: str) -> float:
    if not math.isfinite(valor):
        raise FalhaNumerica(f"{nome} não finito: {valor}")
    return valor


def exigir_denominador(valor: float, nome: str) -> float:
    if valor == 0:
        raise FalhaNumerica(f"{nome} igual a zero")
    return exigir_finito(valor, nome)


def concluir(f: np.ndarray, normas: list[float], iteracoes: int, motivo: str) -> Resultado:
    if not np.isfinite(f).all():
        raise FalhaNumerica("imagem com valor não finito")
    return Resultado(f, normas, iteracoes, motivo)
