from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from recon_py.api.erros import ErroHttp
from recon_py.api.rotas.consultar_pedido import exigir_tarefa
from recon_py.aplicacao.fila.fila import Fila


def _arquivo_de_resultado(fila: Fila, job_id: str, extensao: str, tipo: str) -> Response:
    status = exigir_tarefa(fila, job_id)["status"]
    if status == "failed":
        raise ErroHttp(409, "failed", "a tarefa falhou e não tem resultado")
    if status != "done":
        raise ErroHttp(409, "not_ready", f"tarefa em estado {status}")
    return FileResponse(fila.caminho_resultado(job_id, extensao), media_type=tipo)


def criar_rota(fila: Fila) -> APIRouter:
    rota = APIRouter()

    @rota.get("/jobs/{job_id}/image")
    async def obter_imagem(job_id: str) -> Response:
        return _arquivo_de_resultado(fila, job_id, "pgm", "image/x-portable-graymap")

    @rota.get("/jobs/{job_id}/vector")
    async def obter_vetor(job_id: str) -> Response:
        return _arquivo_de_resultado(fila, job_id, "f64", "application/octet-stream")

    return rota
