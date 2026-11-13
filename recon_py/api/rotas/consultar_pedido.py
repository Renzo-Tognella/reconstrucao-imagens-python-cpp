from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from recon_py.api.erros import ErroHttp
from recon_py.aplicacao.fila.fila import Fila


def exigir_tarefa(fila: Fila, job_id: str) -> dict:
    corpo = fila.consultar(job_id)
    if corpo is None:
        raise ErroHttp(404, "not_found", f"tarefa desconhecida: {job_id}")
    return corpo


def criar_rota(fila: Fila) -> APIRouter:
    rota = APIRouter()

    @rota.get("/jobs/{job_id}")
    async def consultar_tarefa(job_id: str) -> JSONResponse:
        return JSONResponse(exigir_tarefa(fila, job_id))

    return rota
