"""POST /jobs: valida o pedido e o sinal e coloca a tarefa na fila. O cálculo roda no pool da fila."""
from __future__ import annotations

import re
import zlib
from collections.abc import Mapping

import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from recon_py.api.erros import ErroHttp
from recon_py.aplicacao.fila.fila import Conflito, Fila, FilaCheia
from recon_py.aplicacao.fila.tarefa import Pedido
from recon_py.dominio.algoritmos.catalogo import ALGORITMOS
from recon_py.dominio.modelo import Modelo

ID_VALIDO = re.compile(r"[A-Za-z0-9_.-]{1,128}")
GANHOS = {"0": False, "1": True}
FOLGA_DO_CORPO_BYTES = 1024 * 1024


def _exigir_id(parametros: Mapping[str, str], nome: str) -> str:
    valor = parametros.get(nome)
    if valor is None or not ID_VALIDO.fullmatch(valor):
        raise ErroHttp(400, "invalid_params", f"{nome} precisa ter 1 a 128 caracteres em [A-Za-z0-9_.-]")
    return valor


def _exigir_presente(parametros: Mapping[str, str], nome: str) -> str:
    valor = parametros.get(nome)
    if valor is None:
        raise ErroHttp(400, "invalid_params", f"{nome} ausente")
    return valor


def _ler_ganho(parametros: Mapping[str, str]) -> bool:
    ganho = GANHOS.get(parametros.get("gain", ""))
    if ganho is None:
        raise ErroHttp(400, "invalid_params", "gain precisa ser 0 ou 1")
    return ganho


def _interpretar_sinal(corpo: bytes | None, modelo: Modelo) -> np.ndarray:
    if corpo is None:
        raise ErroHttp(413, "payload_too_large", "corpo acima do limite aceito pelo servidor")
    esperado = 8 * modelo.linhas
    if len(corpo) != esperado:
        raise ErroHttp(400, "invalid_length", f"o modelo {modelo.nome} exige corpo de {esperado} bytes")
    sinal = np.frombuffer(corpo, dtype="<f8")
    if not np.isfinite(sinal).all():
        raise ErroHttp(400, "non_finite", "sinal com NaN ou infinito")
    return sinal


def montar_pedido(parametros: Mapping[str, str], corpo: bytes | None, modelos: dict[str, Modelo]) -> Pedido:
    job_id = _exigir_id(parametros, "job_id")
    client_id = _exigir_id(parametros, "client_id")
    signal_id = _exigir_id(parametros, "signal_id")
    nome_modelo = _exigir_presente(parametros, "model")
    algoritmo = _exigir_presente(parametros, "algorithm")
    ganho = _ler_ganho(parametros)
    modelo = modelos.get(nome_modelo)
    if modelo is None:
        raise ErroHttp(400, "unknown_model", f"modelo desconhecido: {nome_modelo}")
    if algoritmo not in ALGORITMOS:
        raise ErroHttp(400, "unknown_algorithm", f"algoritmo desconhecido: {algoritmo}")
    sinal = _interpretar_sinal(corpo, modelo)
    return Pedido(job_id, client_id, signal_id, nome_modelo, algoritmo, ganho, sinal, zlib.crc32(corpo))


async def _ler_corpo_limitado(request: Request, limite: int) -> bytes | None:
    """Consome o corpo inteiro, mas não guarda além do limite: devolve None se ele for maior."""
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total <= limite:
            pedacos.append(pedaco)
    return None if total > limite else b"".join(pedacos)


def criar_rota(fila: Fila, modelos: dict[str, Modelo]) -> APIRouter:
    limite_corpo = max(8 * modelo.linhas for modelo in modelos.values()) + FOLGA_DO_CORPO_BYTES
    rota = APIRouter()

    @rota.post("/jobs")
    async def enviar_tarefa(request: Request) -> JSONResponse:
        corpo = await _ler_corpo_limitado(request, limite_corpo)
        pedido = montar_pedido(request.query_params, corpo, modelos)
        try:
            nova, status = fila.submeter(pedido)
        except Conflito:
            raise ErroHttp(409, "job_conflict", "job_id já usado com corpo ou metadados diferentes") from None
        except FilaCheia:
            raise ErroHttp(503, "queue_full", "fila cheia") from None
        return JSONResponse({"job_id": pedido.job_id, "status": status}, status_code=202 if nova else 200)

    return rota
