from __future__ import annotations

import sys
import time
from typing import TextIO

ROTULOS = {"accepted": "recebido", "rejected": "recusado", "started": "iniciado", "finished": "concluído",
           "failed": "falhou"}
PARADAS = {"tolerance": "convergiu", "max_iterations": "limite"}


def _segundos(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.3f}".replace(".", ",") + " s"


def _detalhe(evento: str, corpo: dict) -> str:
    if evento == "accepted":
        ganho = "sim" if corpo.get("gain") else "não"
        return f"{corpo.get('client_id')}  {corpo.get('model')}  {str(corpo.get('algorithm', '')).upper()}  ganho {ganho}"
    if evento == "started":
        return f"esperou {_segundos(corpo.get('queue_wait_s'))} na fila"
    if evento == "finished":
        parada = PARADAS.get(corpo.get("stop_reason"), corpo.get("stop_reason"))
        return f"reconstruiu em {_segundos(corpo.get('duration_s'))}, {corpo.get('iterations')} iterações ({parada})"
    if evento == "failed":
        return f"erro: {corpo.get('error')}"
    if evento == "rejected":
        return "fila cheia, respondeu 503"
    return ""


def linha_evento(evento: str, job_id: str, corpo: dict | None, fila: int, rodando: int,
                 instante: float | None = None) -> str:
    hora = time.strftime("%H:%M:%S", time.localtime(instante if instante is not None else time.time()))
    rotulo = ROTULOS.get(evento, evento)
    return f"{hora}  {rotulo:<9}  {job_id:<17}  {_detalhe(evento, corpo or {}):<48}  fila {fila}, rodando {rodando}"


def cabecalho() -> str:
    return f"{'hora':<8}  {'evento':<9}  {'pedido':<17}  {'detalhe':<48}  estado do servidor"


def escrever(linha: str, fluxo: TextIO | None = None) -> None:
    try:
        print(linha, file=fluxo or sys.stdout, flush=True)
    except (OSError, ValueError):
        pass
