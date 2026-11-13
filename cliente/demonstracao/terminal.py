"""Saída no terminal da demonstração: uma linha colorida por envio, consulta e imagem pronta, e o resumo final."""
from __future__ import annotations

import statistics
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

ESTILOS = {"negrito": "1", "fraco": "2", "vermelho": "31", "verde": "32", "amarelo": "33", "ciano": "36"}


class Pintor:
    def __init__(self, ligado: bool):
        self.ligado = ligado

    def __call__(self, texto: str, *estilos: str) -> str:
        if not self.ligado or not estilos:
            return texto
        return f"\x1b[{';'.join(ESTILOS[e] for e in estilos)}m{texto}\x1b[0m"


def cor_ativa(modo: str, fluxo: TextIO, ambiente: Mapping[str, str]) -> bool:
    if modo != "auto":
        return modo == "sim"
    eh_terminal = hasattr(fluxo, "isatty") and fluxo.isatty()
    return eh_terminal and "NO_COLOR" not in ambiente and ambiente.get("TERM", "") != "dumb"


def hora(instante: float) -> str:
    milissegundos = round(instante * 1000)
    return time.strftime("%H:%M:%S", time.localtime(milissegundos // 1000)) + f".{milissegundos % 1000:03d}"


def _segundos(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.3f} s"


def linha_envio(pedido: dict, registro: dict, pintar: Pintor) -> str:
    status = registro["status_http"]
    if status is None:
        resposta = pintar(f"sem resposta ({registro['erro']})", "vermelho")
    elif status < 300:
        resposta = pintar(f"HTTP {status}", "verde")
    else:
        resposta = pintar(f"HTTP {status} {registro['erro'] or ''}".rstrip(), "vermelho")
    return "  ".join((
        hora(registro["t_envio_wall"]), pintar("ENVIO   ", "ciano"), pedido["job_id"],
        f"t+{registro['efetivo_s']:.3f}s", f"sinal {pedido['sinal']}", f"modelo {pedido['modelo']}",
        f"ganho {'sim' if pedido['ganho'] else 'não'}", pedido["algoritmo"], resposta,
        f"{registro['duracao_post_s'] * 1000:.1f} ms"))


def linha_progresso(instante: float, rodada: int, estado: Mapping[str, int], total: int, pintar: Pintor) -> str:
    partes = [f"prontas {estado['prontas']}/{total}", f"na fila {estado['na_fila']}",
              f"reconstruindo {estado['reconstruindo']}"]
    if estado.get("falhas"):
        partes.append(pintar(f"falhas {estado['falhas']}", "vermelho"))
    if estado.get("sem_resposta"):
        partes.append(pintar(f"sem resposta {estado['sem_resposta']}", "amarelo"))
    return f"{hora(instante)}  {pintar(f'CONSULTA {rodada}', 'fraco')}  " + " · ".join(partes)


def linha_desfecho(instante: float, job_id: str, desfecho: str, job: dict | None, erro: str | None,
                   pintar: Pintor) -> str:
    if desfecho == "done":
        detalhe = (f"fila {_segundos(job.get('queue_wait_s'))} · reconstrução {_segundos(job.get('duration_s'))}"
                   f" · {job.get('iterations')} iterações ({job.get('stop_reason')})")
        rotulo = pintar("PRONTA  ", "verde", "negrito")
    elif desfecho == "failed":
        detalhe, rotulo = f"erro {erro}", pintar("FALHOU  ", "vermelho", "negrito")
    elif desfecho == "erro_download":
        detalhe, rotulo = f"download: {erro}", pintar("ERRO    ", "vermelho", "negrito")
    else:
        detalhe, rotulo = "não terminou no limite de espera", pintar("SEM FIM ", "amarelo", "negrito")
    return f"{hora(instante)}  {rotulo}  {job_id}  {detalhe}"


def linhas_resumo(cliente: str, resumo: dict, jobs_prontos: list[dict], relatorio: Path | None,
                  pintar: Pintor) -> list[str]:
    enviados = resumo["pedidos"] - resumo["nao_enviados"]
    recusados = resumo["rejeitados"] + resumo["erros_http"]
    contagem = [f"enviados {enviados}", f"concluídos {resumo['concluidos']}", f"recusados {recusados}"]
    for chave, rotulo in (("falhas", "com falha"), ("sem_conclusao", "sem conclusão"),
                          ("erros_download", "erro de download"), ("erros_transporte", "sem resposta ao envio"),
                          ("nao_enviados", "não enviados")):
        if resumo[chave]:
            contagem.append(f"{rotulo} {resumo[chave]}")
    tempos = f"tempo total do cliente {resumo['fim_wall'] - resumo['t0_wall']:.2f} s"
    filas = [j["queue_wait_s"] for j in jobs_prontos if j.get("queue_wait_s") is not None]
    duracoes = [j["duration_s"] for j in jobs_prontos if j.get("duration_s") is not None]
    if filas and duracoes:
        fila, reconstrucao = statistics.fmean(filas), statistics.fmean(duracoes)
        tempos += (f" · tempo médio por imagem {fila + reconstrucao:.3f} s"
                   f" (fila {fila:.3f} s + reconstrução {reconstrucao:.3f} s)")
    linhas = [pintar(f"RESUMO {cliente}", "negrito"), "  " + " · ".join(contagem), "  " + tempos]
    if relatorio is not None:
        linhas.append(f"  relatório: {relatorio}")
    return linhas


class Terminal:
    """Observador da carga: uma linha por evento, já descarregada, para o professor acompanhar ao vivo."""

    def __init__(self, fluxo: TextIO, pintar: Pintor):
        self.fluxo, self.pintar = fluxo, pintar
        self.prontos: list[dict] = []
        self.falhas = 0

    def escrever(self, linha: str) -> None:
        print(linha, file=self.fluxo, flush=True)

    def envio(self, pedido: dict, registro: dict) -> None:
        if registro["desfecho"] == "nao_enviado":
            self.escrever(f"{hora(time.time())}  {self.pintar('NÃO ENVIADO', 'amarelo')}  {pedido['job_id']}")
            return
        self.escrever(linha_envio(pedido, registro, self.pintar))

    def desfecho(self, job_id: str, desfecho: str, job: dict | None, erro: str | None) -> None:
        if desfecho == "done":
            self.prontos.append(job)
        elif desfecho == "failed":
            self.falhas += 1
        self.escrever(linha_desfecho(time.time(), job_id, desfecho, job, erro, self.pintar))

    def rodada(self, numero: int, ultimos: dict[str, str | None], pendentes: list[str]) -> None:
        estados = [ultimos.get(j) for j in pendentes]
        estado = {"prontas": len(self.prontos), "falhas": self.falhas, "na_fila": estados.count("queued"),
                  "reconstruindo": estados.count("running"),
                  "sem_resposta": sum(e not in ("queued", "running") for e in estados)}
        self.escrever(linha_progresso(time.time(), numero, estado, len(ultimos), self.pintar))
