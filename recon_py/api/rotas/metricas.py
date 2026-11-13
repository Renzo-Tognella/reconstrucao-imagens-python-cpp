"""GET /metrics (contadores da fila) e GET /info (como o servidor foi configurado)."""
from __future__ import annotations

import platform
from dataclasses import dataclass

import scipy
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from recon_py.aplicacao.fila.fila import Fila
from recon_py.dominio.modelo import Modelo


@dataclass(frozen=True)
class DescricaoServidor:
    workers: int
    blas_threads: int
    aquecimento_s: float


def descrever_blas() -> str:
    blas = scipy.show_config(mode="dicts")["Build Dependencies"]["blas"]
    return blas["name"] if blas["version"] == "unknown" else f"{blas['name']} {blas['version']}"


def criar_rota(fila: Fila, modelos: dict[str, Modelo], descricao: DescricaoServidor) -> APIRouter:
    blas = descrever_blas()
    rota = APIRouter()

    @rota.get("/metrics")
    async def metricas() -> JSONResponse:
        return JSONResponse(fila.metricas())

    @rota.get("/info")
    async def info() -> JSONResponse:
        return JSONResponse(
            {
                "implementation": "python",
                "language_version": platform.python_version(),
                "blas": blas,
                "workers": descricao.workers,
                "blas_threads": descricao.blas_threads,
                "models": sorted(modelos),
                "aquecimento_s": descricao.aquecimento_s,
            }
        )

    return rota
